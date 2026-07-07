"""code-review-graph (CRG) subprocess adapter for the fact pack.

Graduated from `mergebot/context/prototype.py` (v0.2). CRG is optional: when the
binary is not on PATH the adapter returns None and the fact pack simply omits the
graph sections. CRG *assessment* outputs (risk_score, review_priorities) are never
rendered into the shared fact pack — reviewer independence is a hard constraint —
but may be used internally for selection/ordering.

This module also hosts `run_command`/`CommandError`, the deterministic subprocess
helper shared by the context builder (git, ripgrep, CRG).
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mergebot.context.diff_compression import limit_lines
from mergebot.context.symbols import Symbol

MAX_CRG_ITEMS = 10
CRG_TIMEOUT_SECONDS = 120


class CommandError(RuntimeError):
    """Raised when a deterministic repository command fails."""


def run_command(
    args: list[str],
    cwd: Path,
    check: bool = True,
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        stdin=subprocess.DEVNULL,
        env=env,
    )
    if check and result.returncode != 0:
        raise CommandError(f"{' '.join(args)} failed: {result.stderr.strip()}")
    return result


@dataclass(frozen=True)
class CrgReport:
    """One CRG run: the assessment-neutral section body plus the raw parsed JSON.

    `report_json` stays internal to the builder (ranking, reconciliation); only
    `content` — which strips risk/priority text — may enter the shared fact pack.
    """

    content: str
    report_json: dict[str, Any] | None


@dataclass(frozen=True)
class CrgSymbolSignal:
    path: str
    name: str
    line_start: int | None
    line_end: int | None
    risk_score: float
    rank: int


def run_code_review_graph(
    repo: Path,
    base: str,
    data_dir: Path,
    untracked_files: list[str],
) -> CrgReport | None:
    """Run CRG build + detect-changes; returns None when CRG is not installed.

    CRG is a third-party binary parsing attacker-controlled repo content, so it runs
    with a credential-scrubbed environment — the workspace git credential must never
    be reachable from it. It does not need one: the fact-pack builder's own diffs run
    first and locally cache the base blobs a blobless clone would otherwise lazy-fetch.
    GIT_TERMINAL_PROMPT=0 makes any residual fetch fail fast (degrading the section)
    instead of hanging.
    """
    if not shutil.which("code-review-graph"):
        return None

    data_dir.mkdir(parents=True, exist_ok=True)
    crg_env, index_path = _crg_env_with_untracked(repo, untracked_files)
    crg_env["CRG_LEIDEN_SEED"] = "42"
    try:
        build = run_command(
            ["code-review-graph", "build", "--repo", str(repo), "--data-dir", str(data_dir)],
            cwd=repo,
            check=False,
            timeout=CRG_TIMEOUT_SECONDS,
            env=crg_env,
        )
        report = run_command(
            ["code-review-graph", "detect-changes", "--repo", str(repo), "--base", base],
            cwd=repo,
            check=False,
            timeout=CRG_TIMEOUT_SECONDS,
            env=crg_env,
        )
    finally:
        if index_path:
            index_path.unlink(missing_ok=True)

    report_json = _extract_json_object(report.stdout + report.stderr)
    content = [
        f"Local untracked files exposed to CRG via temporary index: {len(untracked_files)}",
        *(f"- `{path}`" for path in untracked_files),
        f"Build exit code: `{build.returncode}`",
        f"Detect-changes exit code: `{report.returncode}`",
        "CRG Leiden seed pinned to `42` when igraph-based community detection is available.",
        "",
        "### detect-changes",
        _format_crg_report(report_json, report.stdout + report.stderr, repo),
    ]
    return CrgReport(content="\n".join(content), report_json=report_json)


# Env vars whose names contain any of these are stripped from the CRG subprocess env.
_SECRET_ENV_MARKERS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSPHRASE",
    "API_KEY",
    "PRIVATE_KEY",
    "CREDENTIAL",
)
_SECRET_ENV_NAMES = {"GIT_ASKPASS", "MERGEBOT_GIT_USERNAME"}


def scrubbed_env() -> dict[str, str]:
    """A copy of os.environ with credential material removed, safe for CRG."""
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in _SECRET_ENV_NAMES
        and not any(marker in name.upper() for marker in _SECRET_ENV_MARKERS)
    }
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _crg_env_with_untracked(repo: Path, untracked: list[str]) -> tuple[dict[str, str], Path | None]:
    env = scrubbed_env()
    if not untracked:
        return env, None

    fd, index_name = tempfile.mkstemp(prefix="mergebot-crg-index-")
    os.close(fd)
    index_path = Path(index_name)
    index_path.unlink(missing_ok=True)

    crg_env = {**env, "GIT_INDEX_FILE": str(index_path)}
    run_command(["git", "read-tree", "HEAD"], cwd=repo, env=crg_env)
    run_command(["git", "add", "-N", "--", *untracked], cwd=repo, env=crg_env)
    return crg_env, index_path


# -- report formatting (assessment-neutral) -----------------------------------------


def _extract_json_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"{", text):
        try:
            payload, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _format_crg_report(report_json: dict[str, Any] | None, raw_text: str, repo: Path) -> str:
    if report_json is None:
        return (
            "CRG did not emit parseable JSON. Raw output is withheld from the shared "
            "fact pack to avoid leaking assessment text.\n\n"
            "```text\n" + limit_lines(_assessment_neutral_crg_lines(raw_text), 80) + "\n```"
        )

    changed_functions = crg_list(report_json, "changed_functions")
    affected_flows = crg_list(report_json, "affected_flows")

    lines = [
        "#### structural counts",
        f"- changed_symbols: `{len(changed_functions)}`",
        f"- affected_flows: `{len(affected_flows)}`",
        "",
        "#### changed symbol locations",
        *_format_crg_structural_items(changed_functions, repo),
        "",
        "#### affected flows",
        *_format_crg_structural_items(affected_flows, repo),
        "",
        "_CRG risk and priority scores are not rendered into this shared fact pack._",
    ]
    return "\n".join(lines)


def _assessment_neutral_crg_lines(raw_text: str) -> str:
    blocked_terms = ("risk", "priority", "test_gap", "test gap", "untested", "score")
    lines = []
    for line in raw_text.splitlines():
        lower = line.lower()
        if any(term in lower for term in blocked_terms):
            continue
        lines.append(line)
    return "\n".join(lines)


def _format_crg_structural_items(items: list[dict[str, Any]], repo: Path) -> list[str]:
    if not items:
        return ["_None reported._"]
    return [
        _format_crg_structural_item(item, repo)
        for item in sorted(items, key=crg_item_structural_sort_key)[:MAX_CRG_ITEMS]
    ]


def _format_crg_structural_item(item: dict[str, Any], repo: Path) -> str:
    name = item.get("qualified_name") or item.get("name") or "unknown"
    file_path = item.get("file_path") or item.get("file")
    location = format_crg_location(file_path, item.get("line_start"), item.get("line_end"), repo)
    return f"- `{_short_crg_name(str(name))}` {location}".rstrip()


def crg_item_structural_sort_key(item: dict[str, Any]) -> tuple[str, int, str]:
    file_path = item.get("file_path") or item.get("file")
    return (
        str(file_path or ""),
        _optional_int(item.get("line_start")) or 0,
        str(item.get("qualified_name") or item.get("name") or ""),
    )


def format_crg_location(file_path: Any, line_start: Any, line_end: Any, repo: Path) -> str:
    if not isinstance(file_path, str) or not file_path:
        return ""
    location = relative_to_repo(file_path, repo)
    if line_start is None:
        return f"`{location}`"
    end = line_end if line_end is not None else line_start
    return f"`{location}:{line_start}-{end}`"


def format_crg_test_edge_item(item: dict[str, Any], repo: Path) -> str:
    name = item.get("qualified_name") or item.get("name") or "unknown"
    file_path = item.get("file_path") or item.get("file")
    location = format_crg_location(
        relative_to_repo(file_path, repo) if isinstance(file_path, str) else file_path,
        item.get("line_start"),
        item.get("line_end"),
        repo,
    )
    return f"`{_short_crg_name(str(name))}` {location}".rstrip()


def _short_crg_name(name: str) -> str:
    if "::" in name:
        return name.rsplit("::", maxsplit=1)[-1]
    return name


def relative_to_repo(path: str, repo: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        return path
    try:
        return str(candidate.resolve().relative_to(repo.resolve()))
    except ValueError:
        return path


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# -- report JSON access --------------------------------------------------------------


def crg_list(report_json: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = report_json.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def crg_item_symbol_name(item: dict[str, Any]) -> str:
    qualified_name = item.get("qualified_name")
    if isinstance(qualified_name, str) and "::" in qualified_name:
        return qualified_name.rsplit("::", maxsplit=1)[-1]
    name = item.get("name")
    if not isinstance(name, str):
        return ""
    parent = item.get("parent_name")
    if isinstance(parent, str) and parent and not name.startswith(f"{parent}."):
        return f"{parent}.{name}"
    return name


def _crg_item_risk_score(item: dict[str, Any]) -> float:
    try:
        return float(item.get("risk_score") or 0)
    except (TypeError, ValueError):
        return 0.0


# -- symbol signals (internal ranking only — never rendered) --------------------------


def crg_symbol_signals(report_json: dict[str, Any] | None, repo: Path) -> list[CrgSymbolSignal]:
    if report_json is None:
        return []

    signals: list[CrgSymbolSignal] = []
    seen: set[tuple[str, str, int | None]] = set()

    def add_signal(item: dict[str, Any]) -> None:
        signal = _crg_item_to_symbol_signal(item, repo=repo, rank=len(signals))
        if signal is None:
            return
        key = (signal.path, signal.name, signal.line_start)
        if key in seen:
            return
        seen.add(key)
        signals.append(signal)

    # Priority-first ordering is encoded in rank: review_priorities items are added
    # before changed_functions, so they always sort ahead of graph-only matches.
    for item in crg_list(report_json, "review_priorities"):
        add_signal(item)
    for item in sorted(
        crg_list(report_json, "changed_functions"),
        key=_crg_item_risk_score,
        reverse=True,
    ):
        add_signal(item)
    return signals


def _crg_item_to_symbol_signal(
    item: dict[str, Any],
    repo: Path,
    rank: int,
) -> CrgSymbolSignal | None:
    file_path = item.get("file_path") or item.get("file")
    if not isinstance(file_path, str) or not file_path:
        return None
    name = crg_item_symbol_name(item)
    if not name:
        return None
    return CrgSymbolSignal(
        path=relative_to_repo(file_path, repo),
        name=name,
        line_start=_optional_int(item.get("line_start")),
        line_end=_optional_int(item.get("line_end")),
        risk_score=_crg_item_risk_score(item),
        rank=rank,
    )


def rank_symbols_by_crg(symbols: list[Symbol], crg_signals: list[CrgSymbolSignal]) -> list[Symbol]:
    if not crg_signals:
        return symbols
    return sorted(
        symbols,
        key=lambda symbol: (
            _crg_sort_key(symbol, crg_signals),
            symbol.path,
            symbol.start_line,
            symbol.name,
        ),
    )


def _crg_sort_key(symbol: Symbol, crg_signals: list[CrgSymbolSignal]) -> tuple[int, float, int]:
    signal = best_crg_signal(symbol, crg_signals)
    if signal is None:
        return (len(crg_signals) + 1, 0, symbol.start_line)
    return (signal.rank, -signal.risk_score, symbol.start_line)


def symbols_for_reference_search(
    touched: list[Symbol], crg_signals: list[CrgSymbolSignal], max_symbols: int
) -> list[Symbol]:
    if not crg_signals:
        return touched[:max_symbols]
    matched = [symbol for symbol in touched if best_crg_signal(symbol, crg_signals)]
    return (matched or touched)[:max_symbols]


def format_symbol_crg_signal(symbol: Symbol, crg_signals: list[CrgSymbolSignal]) -> str:
    signal = best_crg_signal(symbol, crg_signals)
    if signal is None:
        return ""
    location = ""
    if signal.line_start is not None:
        signal_end = signal.line_end if signal.line_end is not None else signal.line_start
        location = f" at lines {signal.line_start}-{signal_end}"
    return f"- crg: `matched changed symbol{location}`"


def best_crg_signal(symbol: Symbol, crg_signals: list[CrgSymbolSignal]) -> CrgSymbolSignal | None:
    matches = [
        (quality, signal)
        for signal in crg_signals
        if (quality := _crg_signal_match_quality(signal, symbol)) is not None
    ]
    if not matches:
        return None
    return min(matches, key=lambda item: (item[0], item[1].rank, -item[1].risk_score))[1]


def _crg_signal_match_quality(signal: CrgSymbolSignal, symbol: Symbol) -> int | None:
    if signal.path != symbol.path:
        return None
    if _symbol_names_match(signal.name, symbol.name):
        return 0
    if _line_ranges_overlap(
        symbol.start_line,
        symbol.end_line,
        signal.line_start,
        signal.line_end,
    ):
        return 1
    return None


def _symbol_names_match(crg_name: str, symbol_name: str) -> bool:
    crg_leaf = crg_name.rsplit(".", maxsplit=1)[-1]
    symbol_leaf = symbol_name.rsplit(".", maxsplit=1)[-1]
    return (
        crg_name == symbol_name
        or crg_leaf == symbol_leaf
        or crg_name.endswith(f".{symbol_name}")
        or symbol_name.endswith(f".{crg_name}")
    )


def _line_ranges_overlap(
    symbol_start: int,
    symbol_end: int,
    signal_start: int | None,
    signal_end: int | None,
) -> bool:
    if signal_start is None:
        return False
    bounded_signal_end = signal_end if signal_end is not None else signal_start
    return symbol_start <= bounded_signal_end and symbol_end >= signal_start
