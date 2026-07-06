"""Deterministic fact-pack prototype for Mergebot.

This module is intentionally standalone: it does not alter the production flow and
only reads the target repository. It is a proving ground for the proposed context
builder shape before we commit to the full workspace/reviewer integration.
"""
import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROTOTYPE_VERSION = "0.2"
DEFAULT_TOKEN_BUDGET = 12_000
MAX_DEFINITION_LINES = 140
MAX_TOUCHED_SYMBOLS = 14
MAX_REFERENCES_PER_SYMBOL = 12
MAX_REFERENCE_SYMBOLS = 12
MAX_TEST_MATCHES = 24
MAX_CRG_ITEMS = 10
MAX_MANIFEST_REFERENCES = 8
NOISY_REFERENCE_LEAVES = {
    "init",
    "main",
    "run",
    "setup",
    "start",
    "stop",
    "test",
    "__call__",
    "__enter__",
    "__exit__",
    "__init__",
    "__repr__",
    "__str__",
}
SECTION_TOKEN_CAPS = {
    "code_review_graph": 1_600,
    "test_coverage_graph": 1_600,
    "manifest_config_context": 1_000,
    "callers_references": 2_200,
    "related_tests": 1_600,
    "touched_symbols": 4_200,
    "compressed_diff": 6_000,
    "conventions_recent_history": 1_200,
}
SOURCE_GLOBS = [
    "*.py",
    "*.js",
    "*.jsx",
    "*.ts",
    "*.tsx",
    "*.go",
    "*.rs",
    "*.java",
    "*.rb",
    "*.php",
    "*.cs",
    "*.cpp",
    "*.c",
    "*.h",
    "*.hpp",
    "*.swift",
    "*.scala",
    "*.sh",
]
CRG_CANDIDATE_SUFFIXES = {
    ".md",
    ".rst",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
}
CRG_CANDIDATE_FILENAMES = {
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "Makefile",
}
LOCKFILE_EXACT_NAMES = {
    ".terraform.lock.hcl",
    "bun.lock",
    "bun.lockb",
    "Cargo.lock",
    "composer.lock",
    "deno.lock",
    "Gemfile.lock",
    "go.sum",
    "gradle.lockfile",
    "package-lock.json",
    "packages.lock.json",
    "Pipfile.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "yarn.lock",
}
MANIFEST_CONFIG_SUFFIXES = {
    ".toml",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".gradle",
    ".kts",
    ".props",
    ".targets",
    ".csproj",
    ".fsproj",
    ".vbproj",
    ".sln",
    ".mod",
}
MANIFEST_CONFIG_NAMES = {
    "Gemfile",
    "Makefile",
    "Dockerfile",
}


@dataclass(frozen=True)
class FactPackSection:
    name: str
    priority: int
    content: str
    token_estimate: int


@dataclass
class FactPack:
    sections: list[FactPackSection]
    degraded: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def render(self, token_budget: int = DEFAULT_TOKEN_BUDGET) -> str:
        """Render sections in priority order with per-section truncation."""
        lines = [
            "# Mergebot Prototype Fact Pack",
            "",
            "## Metadata",
            _format_json(self.metadata),
            "",
        ]
        used = _estimate_tokens("\n".join(lines))

        for section in sorted(self.sections, key=lambda item: (item.priority, item.name)):
            header = f"## {section.name}"
            body = section.content.strip() or "_No data._"
            block = f"{header}\n\n{body}\n"
            block_tokens = _estimate_tokens(block)
            remaining = token_budget - used
            if remaining <= 0:
                break

            section_budget = min(remaining, _section_token_cap(section.name, token_budget))
            if block_tokens <= section_budget:
                lines.append(block)
                used += block_tokens
                continue

            available = max(section_budget - _estimate_tokens(header) - 20, 0)
            if available <= 0:
                continue
            char_budget = available * 4
            truncated = body[:char_budget].rstrip()
            block = (
                f"{header}\n\n{truncated}\n\n"
                f"_Section truncated to fit its {section_budget} token section budget._\n"
            )
            lines.append(block)
            used += _estimate_tokens(block)

        return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str


@dataclass(frozen=True)
class HunkRange:
    path: str
    start: int
    end: int
    whole_file: bool = False


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    path: str
    start_line: int
    end_line: int
    signature: str


@dataclass(frozen=True)
class CodeReviewGraphRun:
    section: FactPackSection
    report_json: dict[str, Any] | None


@dataclass(frozen=True)
class CrgSymbolSignal:
    path: str
    name: str
    line_start: int | None
    line_end: int | None
    risk_score: float
    rank: int
    from_review_priorities: bool


@dataclass(frozen=True)
class ManifestConfigContext:
    section: FactPackSection
    omitted_diff_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ManifestFieldChange:
    path: str
    key: str
    old_value: str | None
    new_value: str | None


class CommandError(RuntimeError):
    """Raised when a deterministic repository command fails."""


class FactPackBuilder:
    def __init__(
        self,
        repo: Path,
        base: str,
        cache_dir: Path,
        include_code_review_graph: bool = False,
    ) -> None:
        self.repo = repo.resolve()
        self.base = base
        self.cache = SymbolCache(cache_dir.expanduser(), self.repo)
        self.include_code_review_graph = include_code_review_graph
        self.cache_hits = 0
        self.cache_misses = 0

    def build(self) -> FactPack:
        changed_files = self._changed_files()
        hunk_ranges = self._hunk_ranges()
        symbols_by_file = self._symbols_for_changed_files(changed_files)
        touched = self._touched_symbols(hunk_ranges, symbols_by_file)
        crg_run = self._code_review_graph_run() if self.include_code_review_graph else None
        crg_signals = _crg_symbol_signals(crg_run.report_json, self.repo) if crg_run else []
        touched = _rank_symbols_by_crg(touched, crg_signals)
        manifest_context = self._manifest_config_context(changed_files)
        test_coverage_section = (
            self._test_coverage_graph_section(crg_run.report_json) if crg_run else None
        )

        sections = [
            *([crg_run.section] if crg_run else []),
            *([test_coverage_section] if test_coverage_section else []),
            *([manifest_context.section] if manifest_context else []),
            self._compressed_diff_section(
                changed_files,
                set(manifest_context.omitted_diff_paths) if manifest_context else set(),
            ),
            self._touched_symbols_section(touched, crg_signals),
            self._references_section(touched, crg_signals),
            self._related_tests_section(changed_files, touched),
            self._conventions_history_section(changed_files),
        ]

        return FactPack(
            sections=sections,
            metadata={
                "prototype_version": PROTOTYPE_VERSION,
                "repo": str(self.repo),
                "base": self.base,
                "head": self._git(["rev-parse", "HEAD"]).strip(),
                "changed_files": [item.__dict__ for item in changed_files],
                "context_sections": [
                    *(["code_review_graph"] if crg_run else []),
                    *(["test_coverage_graph"] if test_coverage_section else []),
                    *(["manifest_config_context"] if manifest_context else []),
                ],
                "diff_omissions": sorted(
                    manifest_context.omitted_diff_paths if manifest_context else ()
                ),
                "degraded": False,
                "cache": {
                    "symbol_cache_hits": self.cache_hits,
                    "symbol_cache_misses": self.cache_misses,
                    "cache_dir": str(self.cache.cache_dir),
                },
            },
        )

    def _changed_files(self) -> list[ChangedFile]:
        output = self._git(["diff", "--name-status", "--find-renames", self.base, "--"])
        files: list[ChangedFile] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            status = parts[0]
            path = parts[-1]
            files.append(ChangedFile(path=path, status=status))
        for path in self._untracked_files():
            files.append(ChangedFile(path=path, status="??"))
        return sorted(files, key=lambda item: item.path)

    def _hunk_ranges(self) -> list[HunkRange]:
        output = self._git(["diff", "--unified=0", "--find-renames", self.base, "--"])
        ranges: list[HunkRange] = []
        current_path: str | None = None
        path_pattern = re.compile(r"^\+\+\+ b/(.+)$")
        hunk_pattern = re.compile(r"^@@ .+? \+(\d+)(?:,(\d+))? @@")

        for line in output.splitlines():
            path_match = path_pattern.match(line)
            if path_match:
                current_path = path_match.group(1)
                continue
            hunk_match = hunk_pattern.match(line)
            if hunk_match and current_path:
                start = int(hunk_match.group(1))
                count = int(hunk_match.group(2) or "1")
                end = start if count == 0 else start + count - 1
                ranges.append(HunkRange(path=current_path, start=start, end=end))
        for path in self._untracked_files():
            abs_path = self.repo / path
            if abs_path.is_file() and not _is_probably_binary(abs_path):
                line_count = len(_read_text(abs_path).splitlines())
                ranges.append(
                    HunkRange(path=path, start=1, end=max(1, line_count), whole_file=True)
                )
        return ranges

    def _symbols_for_changed_files(
        self, changed_files: list[ChangedFile]
    ) -> dict[str, list[Symbol]]:
        symbols: dict[str, list[Symbol]] = {}
        for changed in changed_files:
            if changed.status.startswith("D"):
                continue
            path = self.repo / changed.path
            if not path.is_file() or _is_probably_binary(path) or not _is_source_path(path):
                continue
            cached, was_hit = self.cache.get_or_parse(path)
            self.cache_hits += int(was_hit)
            self.cache_misses += int(not was_hit)
            symbols[changed.path] = [_symbol_with_path(symbol, changed.path) for symbol in cached]
        return symbols

    @staticmethod
    def _touched_symbols(
        hunk_ranges: list[HunkRange], symbols_by_file: dict[str, list[Symbol]]
    ) -> list[Symbol]:
        selected: dict[tuple[str, str, int], Symbol] = {}
        for hunk in hunk_ranges:
            symbols = symbols_by_file.get(hunk.path, [])
            containing = [
                symbol
                for symbol in symbols
                if symbol.start_line <= hunk.end and symbol.end_line >= hunk.start
            ]
            if not containing:
                continue
            if hunk.whole_file:
                for symbol in containing:
                    selected[(symbol.path, symbol.name, symbol.start_line)] = symbol
                continue
            best = sorted(
                containing,
                key=lambda symbol: (
                    symbol.end_line - symbol.start_line,
                    symbol.start_line,
                    symbol.name,
                ),
            )[0]
            selected[(best.path, best.name, best.start_line)] = best
        return sorted(selected.values(), key=lambda item: (item.path, item.start_line, item.name))

    def _compressed_diff_section(
        self, changed_files: list[ChangedFile], omitted_diff_paths: set[str]
    ) -> FactPackSection:
        diff = self._git(["diff", "--find-renames", "--find-copies", "--stat", self.base, "--"])
        diff += "\n\n"
        if omitted_diff_paths:
            omitted = ", ".join(f"`{path}`" for path in sorted(omitted_diff_paths))
            diff += (
                "Generated artifact raw diff omitted because a nearby manifest/config candidate "
                f"change is listed in manifest_config_context: {omitted}\n\n"
            )
        tracked_diff_paths = [
            item.path
            for item in changed_files
            if item.status != "??" and item.path not in omitted_diff_paths
        ]
        if tracked_diff_paths:
            diff += self._git(
                [
                    "diff",
                    "--find-renames",
                    "--find-copies",
                    "--unified=24",
                    self.base,
                    "--",
                    *tracked_diff_paths,
                ]
            )
        elif omitted_diff_paths:
            diff += "No non-generated tracked diff remains after generated artifact summarization.\n"
        else:
            diff += self._git(
                ["diff", "--find-renames", "--find-copies", "--unified=24", self.base, "--"]
            )
        untracked = [item.path for item in changed_files if item.status == "??"]
        if untracked:
            diff += "\n\n# Untracked files included by local prototype mode\n"
            for path in untracked:
                if path in omitted_diff_paths:
                    continue
                abs_path = self.repo / path
                if abs_path.is_file() and not _is_probably_binary(abs_path):
                    diff += f"\n## {path}\n```text\n{_read_lines(abs_path, 1, 220)}\n```\n"
        if not diff.strip():
            diff = "No git diff found for the selected base."
        content = _limit_lines(diff, 900)
        return _section("compressed_diff", 35, content)

    def _touched_symbols_section(
        self, touched: list[Symbol], crg_signals: list[CrgSymbolSignal]
    ) -> FactPackSection:
        if not touched:
            return _section("touched_symbols", 20, "No changed hunks mapped to known symbols.")

        blocks = []
        visible = touched[:MAX_TOUCHED_SYMBOLS]
        if crg_signals:
            blocks.append(
                "_Ordered by CRG-guided relevance first, then by deterministic path order._"
            )
        if len(touched) > MAX_TOUCHED_SYMBOLS:
            blocks.append(
                f"_Showing {MAX_TOUCHED_SYMBOLS} of {len(touched)} touched symbols. "
                "The full source still appears in `compressed_diff` for new files._"
            )
        for symbol in visible:
            source, omitted_lines = _read_line_excerpt(
                self.repo / symbol.path,
                symbol.start_line,
                symbol.end_line,
            )
            crg_line = _format_symbol_crg_signal(symbol, crg_signals)
            excerpt_line = ""
            if omitted_lines:
                excerpt_line = (
                    f"- excerpt: `{symbol.start_line}-"
                    f"{symbol.start_line + MAX_DEFINITION_LINES - 1}` "
                    f"({omitted_lines} lines omitted)\n"
                )
            blocks.append(
                f"### {symbol.kind}: {symbol.name}\n"
                f"- path: `{symbol.path}`\n"
                f"- lines: {symbol.start_line}-{symbol.end_line}\n"
                f"- signature: `{symbol.signature}`\n"
                f"{excerpt_line}"
                f"{crg_line}\n\n"
                f"```text\n{source}\n```"
            )
        return _section("touched_symbols", 20, "\n\n".join(blocks))

    def _references_section(
        self, touched: list[Symbol], crg_signals: list[CrgSymbolSignal]
    ) -> FactPackSection:
        reference_symbols = _symbols_for_reference_search(touched, crg_signals)
        names = _unique_symbol_names_in_order(reference_symbols)
        if not names:
            return _section("callers_references", 30, "No touched symbols to search for.")

        blocks = []
        if crg_signals and len(reference_symbols) < len(touched):
            blocks.append(
                f"_Reference search pruned to {len(reference_symbols)} CRG-selected touched "
                f"symbols out of {len(touched)}._"
            )
        for name in names:
            matches = self._rg_word(
                name, max_results=MAX_REFERENCES_PER_SYMBOL, source_only=True
            )
            if not matches:
                blocks.append(f"### `{name}`\nNo lexical references found by ripgrep.")
                continue
            blocks.append(f"### `{name}`\n" + "\n".join(f"- `{match}`" for match in matches))
        return _section("callers_references", 12, "\n\n".join(blocks))

    def _related_tests_section(
        self, changed_files: list[ChangedFile], touched: list[Symbol]
    ) -> FactPackSection:
        test_files = self._git(["ls-files"]).splitlines()
        test_files = [path for path in test_files if _looks_like_test_path(path)]
        changed_stems = {Path(item.path).stem for item in changed_files}
        symbol_names = set(_unique_symbol_names(touched))

        candidates = sorted(
            path
            for path in test_files
            if Path(path).stem.replace("test_", "").replace("_test", "") in changed_stems
        )

        matches = []
        for name in sorted(symbol_names):
            for match in self._rg_word(name, glob="*test*", max_results=MAX_TEST_MATCHES):
                if _looks_like_test_path(match.split(":", 1)[0]):
                    matches.append(match)

        content = [
            "Conventional test path candidates:",
            *(f"- `{path}`" for path in candidates[:MAX_TEST_MATCHES]),
            "",
            "Test-file lexical references:",
            *(f"- `{match}`" for match in sorted(set(matches))[:MAX_TEST_MATCHES]),
        ]
        if len(content) <= 4:
            content.append("_No related tests found by prototype heuristics._")
        return _section("related_tests", 14, "\n".join(content))

    def _test_coverage_graph_section(
        self,
        report_json: dict[str, Any] | None,
    ) -> FactPackSection | None:
        if report_json is None:
            return None

        without_test_edge = _crg_list(report_json, "test_gaps")
        if not without_test_edge:
            return None

        no_lexical_refs: list[str] = []
        lexical_disagreements: list[tuple[str, list[str]]] = []
        for item in sorted(without_test_edge, key=_crg_item_structural_sort_key):
            formatted = _format_crg_test_edge_item(item, self.repo)
            refs = self._test_reference_matches(_crg_item_symbol_name(item))
            if refs:
                lexical_disagreements.append((formatted, refs))
            else:
                no_lexical_refs.append(formatted)

        lines = []
        if no_lexical_refs:
            lines.extend(
                [
                    "Changed symbols with no recorded CRG test edge and no lexical "
                    "test references found:",
                    *[f"- {item}" for item in no_lexical_refs[:MAX_CRG_ITEMS]],
                ]
            )
            if len(no_lexical_refs) > MAX_CRG_ITEMS:
                lines.append(f"- ... {len(no_lexical_refs) - MAX_CRG_ITEMS} more symbols omitted")

        if lexical_disagreements:
            if lines:
                lines.append("")
            lines.append(
                "Changed symbols where CRG has no recorded test edge but lexical "
                "test references were found:"
            )
            for formatted, refs in lexical_disagreements[:MAX_CRG_ITEMS]:
                ref_list = "; ".join(f"`{ref}`" for ref in refs[:3])
                suffix = ""
                if len(refs) > 3:
                    suffix = f"; ... {len(refs) - 3} more"
                lines.append(f"- {formatted}; lexical refs: {ref_list}{suffix}")
            if len(lexical_disagreements) > MAX_CRG_ITEMS:
                lines.append(
                    f"- ... {len(lexical_disagreements) - MAX_CRG_ITEMS} more symbols omitted"
                )

        lines.extend(
            [
                "",
                "_CRG test-edge data is reconciled with lexical test references; "
                "disagreements should be treated as graph-resolution evidence, not "
                "coverage evidence._",
            ]
        )
        return _section("test_coverage_graph", 6, "\n".join(lines))

    def _test_reference_matches(self, symbol_name: str) -> list[str]:
        leaf = symbol_name.rsplit(".", maxsplit=1)[-1]
        if len(leaf) < 3 or _is_noisy_reference_leaf(leaf):
            return []
        matches = []
        for match in self._rg_word(leaf, glob="*test*", max_results=MAX_TEST_MATCHES):
            if _looks_like_test_path(match.split(":", 1)[0]):
                matches.append(match)
        return sorted(set(matches))[:MAX_TEST_MATCHES]

    def _conventions_history_section(self, changed_files: list[ChangedFile]) -> FactPackSection:
        history_blocks = []
        for changed in changed_files[:12]:
            log = self._git(
                ["log", "--oneline", "-n", "5", "--", changed.path],
                check=False,
            ).strip()
            if log:
                history_blocks.append(f"### `{changed.path}`\n```text\n{log}\n```")

        content = "\n\n".join(["## Recent path history", *history_blocks])
        return _section("conventions_recent_history", 60, content)

    def _manifest_config_context(
        self, changed_files: list[ChangedFile]
    ) -> ManifestConfigContext | None:
        changed_paths = {item.path for item in changed_files}
        manifest_paths = sorted(path for path in changed_paths if _looks_like_manifest_config(path))
        generated_paths = sorted(path for path in changed_paths if _looks_like_generated_file(path))
        if not manifest_paths and not generated_paths:
            return None

        field_changes = [
            change
            for path in manifest_paths
            for change in self._manifest_field_changes(path)
        ]
        omitted_paths = tuple(
            path
            for path in generated_paths
            if _has_nearby_manifest_config(path, manifest_paths)
        )
        lines = [
            "This section is ecosystem-neutral and evidence-only: it lists human-edited "
            "manifest/config candidates and generated lock/artifact files without assigning "
            "a global PR profile.",
            "",
            "### changed manifest/config candidates",
            *_format_manifest_paths(manifest_paths),
            "",
            "### generated artifacts",
            *_format_generated_paths(generated_paths, omitted_paths),
            "",
            "### manifest field changes",
            *_format_manifest_field_changes(field_changes),
            "",
            "### relevant repo references",
            *self._manifest_reference_lines(field_changes),
        ]
        return ManifestConfigContext(
            section=_section("manifest_config_context", 8, "\n".join(lines).rstrip()),
            omitted_diff_paths=omitted_paths,
        )

    def _manifest_field_changes(self, path: str) -> list[ManifestFieldChange]:
        diff = self._git(["diff", "--unified=0", self.base, "--", path], check=False)
        removed: dict[str, list[str]] = {}
        added: dict[str, list[str]] = {}
        for line in diff.splitlines():
            if not line.startswith(("-", "+")) or line.startswith(("---", "+++")):
                continue
            parsed = _parse_manifest_assignment(line[1:])
            if parsed is None:
                continue
            key, value = parsed
            target = removed if line.startswith("-") else added
            target.setdefault(key, []).append(value)

        changes = []
        for key in sorted(set(removed) | set(added)):
            old_values = removed.get(key) or [None]
            new_values = added.get(key) or [None]
            for index in range(max(len(old_values), len(new_values))):
                old_value = old_values[index] if index < len(old_values) else None
                new_value = new_values[index] if index < len(new_values) else None
                if old_value == new_value:
                    continue
                changes.append(
                    ManifestFieldChange(
                        path=path,
                        key=key,
                        old_value=old_value,
                        new_value=new_value,
                    )
                )
        return changes

    def _manifest_reference_lines(
        self, field_changes: list[ManifestFieldChange]
    ) -> list[str]:
        search_terms = _manifest_reference_terms(field_changes)
        if not search_terms:
            return ["_No manifest field names to search._"]
        lines = []
        for term in search_terms:
            matches = self._rg_word(term, max_results=MAX_MANIFEST_REFERENCES)
            lines.append(f"#### `{term}`")
            if matches:
                lines.extend(f"- `{match}`" for match in matches)
            else:
                lines.append("_No non-generated references found._")
        return lines

    def _code_review_graph_run(self) -> CodeReviewGraphRun:
        if not shutil.which("code-review-graph"):
            return CodeReviewGraphRun(
                section=_section(
                    "code_review_graph",
                    5,
                    "`code-review-graph` is not installed on PATH; skipped optional section.",
                ),
                report_json=None,
            )

        data_dir = self.cache.cache_dir / "code-review-graph"
        data_dir.mkdir(parents=True, exist_ok=True)
        crg_env, index_path, indexed_untracked = self._crg_env_with_untracked()
        crg_env["CRG_LEIDEN_SEED"] = "42"
        try:
            build = _run(
                [
                    "code-review-graph",
                    "build",
                    "--repo",
                    str(self.repo),
                    "--data-dir",
                    str(data_dir),
                ],
                cwd=self.repo,
                check=False,
                timeout=120,
                env=crg_env,
            )
            report = _run(
                [
                    "code-review-graph",
                    "detect-changes",
                    "--repo",
                    str(self.repo),
                    "--base",
                    self.base,
                ],
                cwd=self.repo,
                check=False,
                timeout=120,
                env=crg_env,
            )
        finally:
            if index_path:
                index_path.unlink(missing_ok=True)

        report_json = _extract_json_object(report.stdout + report.stderr)
        content = [
            f"Graph data dir: `{data_dir}`",
            f"Local untracked files exposed to CRG via temporary index: {len(indexed_untracked)}",
            *(f"- `{path}`" for path in indexed_untracked),
            f"Build exit code: `{build.returncode}`",
            f"Detect-changes exit code: `{report.returncode}`",
            "CRG Leiden seed pinned to `42` when igraph-based community detection is available.",
            "",
            "### detect-changes",
            _format_crg_report(report_json, report.stdout + report.stderr),
        ]
        return CodeReviewGraphRun(
            section=_section("code_review_graph", 5, "\n".join(content)),
            report_json=report_json,
        )

    def _crg_env_with_untracked(self) -> tuple[dict[str, str], Path | None, list[str]]:
        env = os.environ.copy()
        untracked = [
            path
            for path in self._untracked_files()
            if _should_expose_untracked_to_crg(self.repo / path)
        ]
        if not untracked:
            return env, None, []

        fd, index_name = tempfile.mkstemp(prefix="mergebot-crg-index-")
        os.close(fd)
        index_path = Path(index_name)
        index_path.unlink(missing_ok=True)

        crg_env = {**env, "GIT_INDEX_FILE": str(index_path)}
        _run(["git", "read-tree", "HEAD"], cwd=self.repo, env=crg_env)
        _run(["git", "add", "-N", "--", *untracked], cwd=self.repo, env=crg_env)
        return crg_env, index_path, untracked

    def _rg_word(
        self,
        word: str,
        glob: str | None = None,
        max_results: int = 50,
        source_only: bool = False,
    ) -> list[str]:
        if not shutil.which("rg") or len(word) < 3:
            return []
        args = [
            "rg",
            "--line-number",
            "--column",
            "--no-heading",
            "--word-regexp",
            "--glob",
            "!.git/**",
            "--glob",
            "!.venv/**",
            "--glob",
            "!venv/**",
            "--glob",
            "!.code-review-graph/**",
            "--glob",
            "!site/**",
            "--glob",
            "!**/demo/**",
        ]
        for artifact_glob in _generated_artifact_exclude_globs():
            args.extend(["--glob", artifact_glob])
        if glob:
            args.extend(["--glob", glob])
        if source_only:
            for source_glob in SOURCE_GLOBS:
                args.extend(["--glob", source_glob])
        args.append(word)
        result = _run(args, cwd=self.repo, check=False)
        if result.returncode not in {0, 1}:
            return []
        return result.stdout.splitlines()[:max_results]

    def _git(self, args: list[str], check: bool = True) -> str:
        result = _run(["git", *args], cwd=self.repo, check=check)
        return result.stdout

    def _git_file_at_base(self, path: str) -> str | None:
        result = _run(["git", "show", f"{self.base}:{path}"], cwd=self.repo, check=False)
        if result.returncode != 0:
            return None
        return result.stdout

    def _untracked_files(self) -> list[str]:
        output = self._git(["ls-files", "--others", "--exclude-standard"], check=False)
        return sorted(line for line in output.splitlines() if line.strip())


class SymbolCache:
    def __init__(self, cache_dir: Path, repo: Path) -> None:
        repo_key = hashlib.sha256(str(repo).encode()).hexdigest()[:16]
        self.cache_dir = cache_dir / repo_key
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_or_parse(self, path: Path) -> tuple[list[Symbol], bool]:
        digest = _file_sha256(path)
        cache_path = self.cache_dir / f"{digest}.json"
        if cache_path.exists():
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if payload.get("version") == PROTOTYPE_VERSION:
                return [_symbol_from_dict(item) for item in payload["symbols"]], True

        symbols = extract_symbols(path)
        cache_path.write_text(
            json.dumps(
                {
                    "version": PROTOTYPE_VERSION,
                    "path": str(path),
                    "symbols": [symbol.__dict__ for symbol in symbols],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return symbols, False


def extract_symbols(path: Path) -> list[Symbol]:
    text = _read_text(path)
    rel_path = _safe_relative(path)
    if path.suffix == ".py":
        return _extract_python_symbols(text, rel_path)
    return _extract_heuristic_symbols(text, rel_path)


def _extract_python_symbols(text: str, rel_path: str) -> list[Symbol]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _extract_heuristic_symbols(text, rel_path)

    symbols = []
    parents: list[str] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.ClassDef):
            name = ".".join([*parents, node.name])
            symbols.append(_python_symbol(node, rel_path, name, "class", text))
            parents.append(node.name)
            for child in node.body:
                visit(child)
            parents.pop()
            return
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            name = ".".join([*parents, node.name])
            symbols.append(_python_symbol(node, rel_path, name, "function", text))
            parents.append(node.name)
            for child in node.body:
                visit(child)
            parents.pop()
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return sorted(symbols, key=lambda item: (item.start_line, item.name))


def _python_symbol(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    rel_path: str,
    name: str,
    kind: str,
    text: str,
) -> Symbol:
    end_line = getattr(node, "end_lineno", node.lineno)
    lines = text.splitlines()
    signature = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else name
    return Symbol(
        name=name,
        kind=kind,
        path=rel_path,
        start_line=node.lineno,
        end_line=end_line,
        signature=signature,
    )


def _extract_heuristic_symbols(text: str, rel_path: str) -> list[Symbol]:
    patterns = [
        (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"), "function"),
        (re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)"), "class"),
        (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*="), "function"),
        (re.compile(r"^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_]\w*)"), "function"),
        (re.compile(r"^\s*(?:pub\s+)?fn\s+([A-Za-z_]\w*)"), "function"),
        (re.compile(r"^\s*(?:public|private|protected)?\s*class\s+([A-Za-z_]\w*)"), "class"),
        (re.compile(r"^\s*def\s+([A-Za-z_]\w*)"), "function"),
    ]
    lines = text.splitlines()
    starts: list[tuple[int, str, str, str]] = []
    for index, line in enumerate(lines, start=1):
        for pattern, kind in patterns:
            match = pattern.match(line)
            if match:
                starts.append((index, match.group(1), kind, line.strip()))
                break

    symbols = []
    for offset, (start, name, kind, signature) in enumerate(starts):
        end = starts[offset + 1][0] - 1 if offset + 1 < len(starts) else len(lines)
        symbols.append(
            Symbol(
                name=name,
                kind=kind,
                path=rel_path,
                start_line=start,
                end_line=max(start, end),
                signature=signature,
            )
        )
    return symbols


def _run(
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


def _section(name: str, priority: int, content: str) -> FactPackSection:
    return FactPackSection(
        name=name,
        priority=priority,
        content=content,
        token_estimate=_estimate_tokens(content),
    )


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _section_token_cap(section_name: str, token_budget: int) -> int:
    configured = SECTION_TOKEN_CAPS.get(section_name, token_budget)
    return min(configured, token_budget)


def _format_json(data: dict[str, Any]) -> str:
    return "```json\n" + json.dumps(data, indent=2, sort_keys=True) + "\n```"


def _looks_like_manifest_config(path: str) -> bool:
    candidate = Path(path)
    if _looks_like_generated_file(path):
        return False
    return (
        candidate.suffix in MANIFEST_CONFIG_SUFFIXES
        or candidate.name in MANIFEST_CONFIG_NAMES
    )


def _looks_like_generated_file(path: str) -> bool:
    name = Path(path).name
    lower_name = name.lower()
    exact_names = {item.lower() for item in LOCKFILE_EXACT_NAMES}
    return lower_name in exact_names or Path(lower_name).suffix == ".lock"


def _has_nearby_manifest_config(generated_path: str, manifest_paths: list[str]) -> bool:
    generated_parent = Path(generated_path).parent
    return any(Path(manifest_path).parent == generated_parent for manifest_path in manifest_paths)


def _parse_manifest_assignment(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", "//", "/*", "*")):
        return None
    for pattern in (
        r'^["\']?([A-Za-z0-9_.@/-]+)["\']?\s*[:=]\s*(.+?)(?:,)?$',
        r'^<[^>]*\b(?:Include|Update|Name)=["\']([^"\']+)["\'][^>]*\bVersion=["\']([^"\']+)["\']',
    ):
        match = re.match(pattern, stripped)
        if match:
            return match.group(1), match.group(2).strip()
    return None


def _format_manifest_paths(paths: list[str]) -> list[str]:
    if not paths:
        return ["_No human-edited manifest/config candidates changed._"]
    return [f"- `{path}`" for path in paths]


def _format_generated_paths(paths: list[str], omitted_paths: tuple[str, ...]) -> list[str]:
    if not paths:
        return ["_No generated lock/artifact files changed._"]
    omitted = set(omitted_paths)
    lines = []
    for path in paths:
        action = "raw diff omitted; nearby manifest/config candidate changed"
        if path not in omitted:
            action = "raw diff retained; no nearby manifest/config candidate explains it"
        lines.append(f"- `{path}`: {action}")
    return lines


def _format_manifest_field_changes(changes: list[ManifestFieldChange]) -> list[str]:
    if not changes:
        return ["_No simple key/value field changes detected; inspect manifest diff._"]
    lines = []
    for change in changes[:MAX_CRG_ITEMS]:
        lines.append(
            f"- `{change.path}` `{change.key}`: "
            f"`{change.old_value or '<absent>'}` -> `{change.new_value or '<absent>'}`"
        )
    if len(changes) > MAX_CRG_ITEMS:
        lines.append(f"- ... {len(changes) - MAX_CRG_ITEMS} more field changes omitted")
    return lines


def _manifest_reference_terms(changes: list[ManifestFieldChange]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for change in changes:
        if len(change.key) < 3 or change.key in seen:
            continue
        seen.add(change.key)
        terms.append(change.key)
        if len(terms) >= MAX_MANIFEST_REFERENCES:
            break
    return terms


def _generated_artifact_exclude_globs() -> list[str]:
    globs = ["!**/*.lock"]
    exact_names = sorted({item.lower() for item in LOCKFILE_EXACT_NAMES})
    for name in exact_names:
        globs.append(f"!**/{name}")
    return globs


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


def _format_crg_report(report_json: dict[str, Any] | None, raw_text: str) -> str:
    if report_json is None:
        return (
            "CRG did not emit parseable JSON. Raw output is withheld from the shared "
            "fact pack to avoid leaking assessment text.\n\n"
            "```text\n"
            + _limit_lines(_assessment_neutral_crg_lines(raw_text), 80)
            + "\n```"
        )

    changed_functions = _crg_list(report_json, "changed_functions")
    affected_flows = _crg_list(report_json, "affected_flows")

    lines = [
        "#### structural counts",
        f"- changed_symbols: `{len(changed_functions)}`",
        f"- affected_flows: `{len(affected_flows)}`",
        "",
        "#### changed symbol locations",
        *_format_crg_structural_items(changed_functions),
        "",
        "#### affected flows",
        *_format_crg_structural_items(affected_flows),
        "",
        "_CRG risk and priority scores are not rendered into this shared fact pack._",
    ]
    return "\n".join(lines)


def _format_crg_test_edge_item(item: dict[str, Any], repo: Path) -> str:
    name = item.get("qualified_name") or item.get("name") or "unknown"
    file_path = item.get("file_path") or item.get("file")
    location = _format_crg_location(
        _relative_to_repo(file_path, repo) if isinstance(file_path, str) else file_path,
        item.get("line_start"),
        item.get("line_end"),
    )
    return f"`{_short_crg_name(str(name))}` {location}".rstrip()


def _assessment_neutral_crg_lines(raw_text: str) -> str:
    blocked_terms = ("risk", "priority", "test_gap", "test gap", "untested", "score")
    lines = []
    for line in raw_text.splitlines():
        lower = line.lower()
        if any(term in lower for term in blocked_terms):
            continue
        lines.append(line)
    return "\n".join(lines)


def _crg_list(report_json: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = report_json.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _crg_review_priorities(report_json: dict[str, Any]) -> list[dict[str, Any]]:
    priorities = _crg_list(report_json, "review_priorities")
    if priorities:
        return priorities[:MAX_CRG_ITEMS]
    return sorted(
        _crg_list(report_json, "changed_functions"),
        key=_crg_item_risk_score,
        reverse=True,
    )[:MAX_CRG_ITEMS]


def _crg_symbol_signals(
    report_json: dict[str, Any] | None, repo: Path
) -> list[CrgSymbolSignal]:
    if report_json is None:
        return []

    signals: list[CrgSymbolSignal] = []
    seen: set[tuple[str, str, int | None]] = set()

    def add_signal(item: dict[str, Any], from_review_priorities: bool) -> None:
        signal = _crg_item_to_symbol_signal(
            item,
            repo=repo,
            rank=len(signals),
            from_review_priorities=from_review_priorities,
        )
        if signal is None:
            return
        key = (signal.path, signal.name, signal.line_start)
        if key in seen:
            return
        seen.add(key)
        signals.append(signal)

    for item in _crg_list(report_json, "review_priorities"):
        add_signal(item, from_review_priorities=True)
    for item in sorted(
        _crg_list(report_json, "changed_functions"),
        key=_crg_item_risk_score,
        reverse=True,
    ):
        add_signal(item, from_review_priorities=False)
    return signals


def _crg_item_to_symbol_signal(
    item: dict[str, Any],
    repo: Path,
    rank: int,
    from_review_priorities: bool,
) -> CrgSymbolSignal | None:
    file_path = item.get("file_path") or item.get("file")
    if not isinstance(file_path, str) or not file_path:
        return None
    name = _crg_item_symbol_name(item)
    if not name:
        return None
    return CrgSymbolSignal(
        path=_relative_to_repo(file_path, repo),
        name=name,
        line_start=_optional_int(item.get("line_start")),
        line_end=_optional_int(item.get("line_end")),
        risk_score=_crg_item_risk_score(item),
        rank=rank,
        from_review_priorities=from_review_priorities,
    )


def _crg_item_symbol_name(item: dict[str, Any]) -> str:
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


def _rank_symbols_by_crg(
    symbols: list[Symbol], crg_signals: list[CrgSymbolSignal]
) -> list[Symbol]:
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


def _crg_sort_key(
    symbol: Symbol, crg_signals: list[CrgSymbolSignal]
) -> tuple[int, float, int]:
    signal = _best_crg_signal(symbol, crg_signals)
    if signal is None:
        return (len(crg_signals) + 1, 0, symbol.start_line)
    return (signal.rank, -signal.risk_score, symbol.start_line)


def _symbols_for_reference_search(
    touched: list[Symbol], crg_signals: list[CrgSymbolSignal]
) -> list[Symbol]:
    if not crg_signals:
        return touched[:MAX_REFERENCE_SYMBOLS]
    matched = [symbol for symbol in touched if _best_crg_signal(symbol, crg_signals)]
    return (matched or touched)[:MAX_REFERENCE_SYMBOLS]


def _format_symbol_crg_signal(symbol: Symbol, crg_signals: list[CrgSymbolSignal]) -> str:
    signal = _best_crg_signal(symbol, crg_signals)
    if signal is None:
        return ""
    location = ""
    if signal.line_start is not None:
        signal_end = signal.line_end if signal.line_end is not None else signal.line_start
        location = f" at lines {signal.line_start}-{signal_end}"
    return f"- crg: `matched changed symbol{location}`"


def _best_crg_signal(
    symbol: Symbol, crg_signals: list[CrgSymbolSignal]
) -> CrgSymbolSignal | None:
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


def _format_crg_structural_items(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["_None reported._"]
    return [
        _format_crg_structural_item(item)
        for item in sorted(items, key=_crg_item_structural_sort_key)[:MAX_CRG_ITEMS]
    ]


def _format_crg_structural_item(item: dict[str, Any]) -> str:
    name = item.get("qualified_name") or item.get("name") or "unknown"
    file_path = item.get("file_path") or item.get("file")
    location = _format_crg_location(file_path, item.get("line_start"), item.get("line_end"))
    return f"- `{_short_crg_name(str(name))}` {location}".rstrip()


def _crg_item_structural_sort_key(item: dict[str, Any]) -> tuple[str, int, str]:
    file_path = item.get("file_path") or item.get("file")
    return (
        str(file_path or ""),
        _optional_int(item.get("line_start")) or 0,
        str(item.get("qualified_name") or item.get("name") or ""),
    )


def _format_crg_location(file_path: Any, line_start: Any, line_end: Any) -> str:
    if not isinstance(file_path, str) or not file_path:
        return ""
    location = _display_path(file_path)
    if line_start is None:
        return f"`{location}`"
    end = line_end if line_end is not None else line_start
    return f"`{location}:{line_start}-{end}`"


def _short_crg_name(name: str) -> str:
    if "::" in name:
        return name.rsplit("::", maxsplit=1)[-1]
    return name


def _display_path(path: str) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return path


def _relative_to_repo(path: str, repo: Path) -> str:
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


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_lines(path: Path, start: int, end: int) -> str:
    lines = _read_text(path).splitlines()
    bounded_end = min(end, len(lines))
    return "\n".join(lines[max(start - 1, 0) : bounded_end])


def _read_line_excerpt(path: Path, start: int, end: int) -> tuple[str, int]:
    lines = _read_text(path).splitlines()
    bounded_end = min(end, start + MAX_DEFINITION_LINES - 1, len(lines))
    source = "\n".join(lines[max(start - 1, 0) : bounded_end])
    omitted = max(0, min(end, len(lines)) - bounded_end)
    return source, omitted


def _limit_lines(text: str, max_lines: int) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text.strip()
    return "\n".join(lines[:max_lines]).rstrip() + "\n... truncated ..."


def _safe_relative(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return path.name


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_probably_binary(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:2048]
    except OSError:
        return True
    return b"\0" in sample


def _looks_like_test_path(path: str) -> bool:
    lower = path.lower()
    name = Path(lower).name
    return (
        "/test/" in lower
        or "/tests/" in lower
        or name.startswith("test_")
        or name.endswith("_test.py")
        or ".test." in name
        or ".spec." in name
        or name.endswith("_spec.rb")
    )


def _is_source_path(path: Path) -> bool:
    return path.suffix.lower() in {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".kts",
        ".rb",
        ".php",
        ".cs",
        ".cpp",
        ".cc",
        ".c",
        ".h",
        ".hpp",
        ".swift",
        ".scala",
        ".sh",
        ".bash",
        ".zsh",
    }


def _should_expose_untracked_to_crg(path: Path) -> bool:
    if not path.is_file() or _is_probably_binary(path):
        return False
    return (
        _is_source_path(path)
        or path.suffix.lower() in CRG_CANDIDATE_SUFFIXES
        or path.name in CRG_CANDIDATE_FILENAMES
    )


def _unique_symbol_names(symbols: list[Symbol]) -> list[str]:
    names: set[str] = set()
    for symbol in symbols:
        name = symbol.name.split(".")[-1]
        if _is_noisy_reference_leaf(name):
            continue
        names.add(name)
    return sorted(name for name in names if len(name) >= 3)


def _unique_symbol_names_in_order(symbols: list[Symbol]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        name = symbol.name.split(".")[-1]
        if len(name) < 3 or name in seen or _is_noisy_reference_leaf(name):
            continue
        seen.add(name)
        names.append(name)
    return names


def _is_noisy_reference_leaf(name: str) -> bool:
    return name in NOISY_REFERENCE_LEAVES or (
        name.startswith("__") and name.endswith("__")
    )


def _symbol_from_dict(data: dict[str, Any]) -> Symbol:
    return Symbol(
        name=data["name"],
        kind=data["kind"],
        path=data["path"],
        start_line=int(data["start_line"]),
        end_line=int(data["end_line"]),
        signature=data["signature"],
    )


def _symbol_with_path(symbol: Symbol, path: str) -> Symbol:
    return Symbol(
        name=symbol.name,
        kind=symbol.kind,
        path=path,
        start_line=symbol.start_line,
        end_line=symbol.end_line,
        signature=symbol.signature,
    )


def build_fact_pack(
    repo: Path,
    base: str,
    cache_dir: Path,
    include_code_review_graph: bool = False,
) -> FactPack:
    return FactPackBuilder(
        repo=repo,
        base=base,
        cache_dir=cache_dir,
        include_code_review_graph=include_code_review_graph,
    ).build()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a prototype Mergebot fact pack.")
    parser.add_argument("--repo", default=".", help="Repository root to inspect.")
    parser.add_argument("--base", default="HEAD~1", help="Git ref to diff against.")
    parser.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    parser.add_argument(
        "--cache-dir",
        default="~/.cache/mergebot/fact-pack",
        help="Persistent symbol cache directory.",
    )
    parser.add_argument("--output", help="Write rendered fact pack to this path.")
    parser.add_argument(
        "--include-code-review-graph",
        action="store_true",
        help="Optionally run code-review-graph if installed.",
    )
    args = parser.parse_args(argv)

    fact_pack = build_fact_pack(
        repo=Path(args.repo),
        base=args.base,
        cache_dir=Path(args.cache_dir),
        include_code_review_graph=args.include_code_review_graph,
    )
    rendered = fact_pack.render(token_budget=args.token_budget)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
