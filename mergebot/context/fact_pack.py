"""Deterministic fact-pack builder for context-aware reviews.

Deterministic by design — no LLM involvement — which makes the reviewer-independence
guarantee structural: every reviewer receives the identical, opinion-free evidence base.

Section sources: code-review-graph structural facts (assessment fields stripped),
CRG/lexical test-coverage reconciliation, manifest/config candidates, ripgrep
callers/references, related tests, touched-symbol excerpts, compressed diff, and
recent path history. `repo_map_lite` stays dropped (proposal §6).
"""

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mergebot.context import crg, diff_compression, tests_locator
from mergebot.context.crg import run_command
from mergebot.context.diff_compression import ChangedFile, HunkRange, estimate_tokens
from mergebot.context.symbols import (
    SOURCE_SUFFIXES,
    Symbol,
    SymbolCache,
    is_probably_binary,
    is_source_path,
    read_text,
    symbol_with_path,
)

DEFAULT_TOKEN_BUDGET = 12_000
MAX_DEFINITION_LINES = 140
MAX_TOUCHED_SYMBOLS = 14
MAX_REFERENCES_PER_SYMBOL = 12
MAX_REFERENCE_SYMBOLS = 12
MAX_TEST_MATCHES = 24
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
# Derived from the symbol extractor's suffix set so reference search and symbol
# extraction always agree on what counts as source.
SOURCE_GLOBS = [f"*{suffix}" for suffix in sorted(SOURCE_SUFFIXES)]
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


@dataclass
class FactPack:
    sections: list[FactPackSection]
    metadata: dict[str, Any] = field(default_factory=dict)

    def render(
        self,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
        section_caps: dict[str, int] | None = None,
        reserved_sections: set[str] | None = None,
    ) -> str:
        """Render sections in priority order with per-section truncation.

        `reserved_sections` names sections whose budget (up to their cap) is set
        aside before higher-priority sections spend the global budget — used for
        the compressed diff when it replaces the raw patch, where dropping the
        section would be an information regression rather than a trim.
        """
        caps = section_caps or SECTION_TOKEN_CAPS
        reserved = reserved_sections or set()
        lines = [
            "# Repository Context (Fact Pack)",
            "",
            "_Deterministic repository facts gathered from a checkout of this PR/MR;"
            " evidence only, no assessments._",
            "",
            "## Metadata",
            _format_json(self.metadata),
            "",
        ]
        used = estimate_tokens("\n".join(lines))

        reservations: dict[str, int] = {}
        for section in self.sections:
            if section.name in reserved:
                block_tokens = estimate_tokens(f"## {section.name}\n\n{section.content}\n")
                reservations[section.name] = min(
                    block_tokens, _section_token_cap(section.name, token_budget, caps)
                )
        used += sum(reservations.values())

        for section in sorted(self.sections, key=lambda item: (item.priority, item.name)):
            header = f"## {section.name}"
            body = section.content.strip() or "_No data._"
            block = f"{header}\n\n{body}\n"
            block_tokens = estimate_tokens(block)
            reservation = reservations.pop(section.name, 0)
            remaining = token_budget - used + reservation
            if remaining <= 0:
                if not reservations:
                    break
                continue  # skip this section but keep going for reserved ones

            section_budget = min(remaining, _section_token_cap(section.name, token_budget, caps))
            if block_tokens <= section_budget:
                lines.append(block)
                used += block_tokens - reservation
                continue

            available = max(section_budget - estimate_tokens(header) - 20, 0)
            if available <= 0:
                used -= reservation
                continue
            char_budget = available * 4
            truncated = body[:char_budget].rstrip()
            block = (
                f"{header}\n\n{truncated}\n\n"
                f"_Section truncated to fit its {section_budget} token section budget._\n"
            )
            lines.append(block)
            used += estimate_tokens(block) - reservation

        return "\n".join(lines).rstrip() + "\n"


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


class FactPackBuilder:
    def __init__(
        self,
        repo: Path,
        base: str,
        cache_dir: Path,
        include_code_review_graph: bool = True,
        include_compressed_diff: bool = True,
        git_env: dict[str, str] | None = None,
        cache_key: str | None = None,
    ) -> None:
        """Args worth noting:

        git_env: the workspace's authenticated git env. The checkout is a blobless
            partial clone, so `git diff` against the base commit can lazy-fetch
            blobs over the network mid-build and must be able to authenticate.
        cache_key: stable project identity for the symbol cache (defaults to the
            repo path — callers reviewing per-review temp checkouts must pass the
            project path or the cache never hits).
        """
        self.repo = repo.resolve()
        self.base = base
        self.git_env = git_env
        self.cache = SymbolCache(cache_dir.expanduser(), cache_key or str(self.repo))
        self.include_code_review_graph = include_code_review_graph
        self.include_compressed_diff = include_compressed_diff
        self.cache_hits = 0
        self.cache_misses = 0
        self._untracked: list[str] | None = None

    def build(self) -> FactPack:
        changed_files = self._changed_files()
        hunk_ranges = self._hunk_ranges()
        symbols_by_file = self._symbols_for_changed_files(changed_files)
        touched = self._touched_symbols(hunk_ranges, symbols_by_file)
        crg_report = self._code_review_graph_run() if self.include_code_review_graph else None
        report_json = crg_report.report_json if crg_report else None
        crg_signals = crg.crg_symbol_signals(report_json, self.repo) if crg_report else []
        touched = crg.rank_symbols_by_crg(touched, crg_signals)
        manifest_context = self._manifest_config_context(changed_files)
        test_coverage_section = (
            self._test_coverage_graph_section(report_json) if crg_report else None
        )

        sections = [
            *([_section("code_review_graph", 5, crg_report.content)] if crg_report else []),
            *([test_coverage_section] if test_coverage_section else []),
            *([manifest_context.section] if manifest_context else []),
            *(
                [
                    self._compressed_diff_section(
                        changed_files,
                        set(manifest_context.omitted_diff_paths) if manifest_context else set(),
                    )
                ]
                if self.include_compressed_diff
                else []
            ),
            self._touched_symbols_section(touched, crg_signals),
            self._references_section(touched, crg_signals),
            self._related_tests_section(changed_files, touched),
            self._conventions_history_section(changed_files),
        ]

        return FactPack(
            sections=sections,
            metadata={
                "base": self.base,
                "head": self._git(["rev-parse", "HEAD"]).strip(),
                "changed_files": [item.__dict__ for item in changed_files],
                "context_sections": [
                    *(["code_review_graph"] if crg_report else []),
                    *(["test_coverage_graph"] if test_coverage_section else []),
                    *(["manifest_config_context"] if manifest_context else []),
                ],
                "diff_omissions": sorted(
                    manifest_context.omitted_diff_paths if manifest_context else ()
                ),
                "compressed_diff_included": self.include_compressed_diff,
                "cache": {
                    "symbol_cache_hits": self.cache_hits,
                    "symbol_cache_misses": self.cache_misses,
                },
            },
        )

    def _changed_files(self) -> list[ChangedFile]:
        output = self._git(["diff", "--name-status", "--find-renames", self.base, "--"])
        files = diff_compression.parse_name_status(output)
        for path in self._untracked_files():
            files.append(ChangedFile(path=path, status="??"))
        return sorted(files, key=lambda item: item.path)

    def _hunk_ranges(self) -> list[HunkRange]:
        output = self._git(["diff", "--unified=0", "--find-renames", self.base, "--"])
        ranges = diff_compression.parse_hunk_ranges(output)
        for path in self._untracked_files():
            abs_path = self.repo / path
            if abs_path.is_file() and not is_probably_binary(abs_path):
                line_count = len(read_text(abs_path).splitlines())
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
            if not path.is_file() or is_probably_binary(path) or not is_source_path(path):
                continue
            cached, was_hit = self.cache.get_or_parse(path)
            self.cache_hits += int(was_hit)
            self.cache_misses += int(not was_hit)
            symbols[changed.path] = [symbol_with_path(symbol, changed.path) for symbol in cached]
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
        content = diff_compression.build_compressed_diff(
            git=lambda args: self._git(args, check=False),
            repo=self.repo,
            base=self.base,
            changed_files=changed_files,
            omitted_diff_paths=omitted_diff_paths,
        )
        return _section("compressed_diff", 35, content)

    def _touched_symbols_section(
        self, touched: list[Symbol], crg_signals: list[crg.CrgSymbolSignal]
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
            crg_line = crg.format_symbol_crg_signal(symbol, crg_signals)
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
        self, touched: list[Symbol], crg_signals: list[crg.CrgSymbolSignal]
    ) -> FactPackSection:
        reference_symbols = crg.symbols_for_reference_search(
            touched, crg_signals, MAX_REFERENCE_SYMBOLS
        )
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
            matches = self._rg_word(name, max_results=MAX_REFERENCES_PER_SYMBOL, source_only=True)
            if not matches:
                blocks.append(f"### `{name}`\nNo lexical references found by ripgrep.")
                continue
            blocks.append(f"### `{name}`\n" + "\n".join(f"- `{match}`" for match in matches))
        return _section("callers_references", 12, "\n\n".join(blocks))

    def _related_tests_section(
        self, changed_files: list[ChangedFile], touched: list[Symbol]
    ) -> FactPackSection:
        tracked_files = self._git(["ls-files"]).splitlines()
        candidates = tests_locator.conventional_test_candidates(
            tracked_files, [item.path for item in changed_files]
        )

        matches = []
        for name in sorted(set(_unique_symbol_names(touched))):
            for match in self._rg_word(name, glob="*test*", max_results=MAX_TEST_MATCHES):
                if tests_locator.looks_like_test_path(match.split(":", 1)[0]):
                    matches.append(match)

        content = [
            "Conventional test path candidates:",
            *(f"- `{path}`" for path in candidates[:MAX_TEST_MATCHES]),
            "",
            "Test-file lexical references:",
            *(f"- `{match}`" for match in sorted(set(matches))[:MAX_TEST_MATCHES]),
        ]
        if len(content) <= 4:
            content.append("_No related tests found by heuristics._")
        return _section("related_tests", 14, "\n".join(content))

    def _test_coverage_graph_section(
        self,
        report_json: dict[str, Any] | None,
    ) -> FactPackSection | None:
        if report_json is None:
            return None

        without_test_edge = crg.crg_list(report_json, "test_gaps")
        if not without_test_edge:
            return None

        no_lexical_refs: list[str] = []
        lexical_disagreements: list[tuple[str, list[str]]] = []
        for item in sorted(without_test_edge, key=crg.crg_item_structural_sort_key):
            formatted = crg.format_crg_test_edge_item(item, self.repo)
            refs = self._test_reference_matches(crg.crg_item_symbol_name(item))
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
                    *[f"- {item}" for item in no_lexical_refs[: crg.MAX_CRG_ITEMS]],
                ]
            )
            if len(no_lexical_refs) > crg.MAX_CRG_ITEMS:
                lines.append(
                    f"- ... {len(no_lexical_refs) - crg.MAX_CRG_ITEMS} more symbols omitted"
                )

        if lexical_disagreements:
            if lines:
                lines.append("")
            lines.append(
                "Changed symbols where CRG has no recorded test edge but lexical "
                "test references were found:"
            )
            for formatted, refs in lexical_disagreements[: crg.MAX_CRG_ITEMS]:
                ref_list = "; ".join(f"`{ref}`" for ref in refs[:3])
                suffix = ""
                if len(refs) > 3:
                    suffix = f"; ... {len(refs) - 3} more"
                lines.append(f"- {formatted}; lexical refs: {ref_list}{suffix}")
            if len(lexical_disagreements) > crg.MAX_CRG_ITEMS:
                lines.append(
                    f"- ... {len(lexical_disagreements) - crg.MAX_CRG_ITEMS} more symbols omitted"
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
            if tests_locator.looks_like_test_path(match.split(":", 1)[0]):
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
            change for path in manifest_paths for change in self._manifest_field_changes(path)
        ]
        omitted_paths = tuple(
            path for path in generated_paths if _has_nearby_manifest_config(path, manifest_paths)
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

    def _manifest_reference_lines(self, field_changes: list[ManifestFieldChange]) -> list[str]:
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

    def _code_review_graph_run(self) -> crg.CrgReport | None:
        untracked = [
            path
            for path in self._untracked_files()
            if _should_expose_untracked_to_crg(self.repo / path)
        ]
        # No git_env here: CRG runs credential-scrubbed (see crg.run_code_review_graph);
        # the builder's own diffs have already cached the base blobs it needs.
        return crg.run_code_review_graph(
            repo=self.repo,
            base=self.base,
            data_dir=self.cache.cache_dir / "code-review-graph",
            untracked_files=untracked,
        )

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
        result = run_command(args, cwd=self.repo, check=False)
        if result.returncode not in {0, 1}:
            return []
        return result.stdout.splitlines()[:max_results]

    def _git(self, args: list[str], check: bool = True) -> str:
        # Runs with the workspace's authenticated env: blobless-clone lazy fetches
        # triggered by diff/log/show must be able to reach the remote.
        result = run_command(["git", *args], cwd=self.repo, check=check, env=self.git_env)
        return result.stdout

    def _untracked_files(self) -> list[str]:
        if self._untracked is None:
            output = self._git(["ls-files", "--others", "--exclude-standard"], check=False)
            self._untracked = sorted(line for line in output.splitlines() if line.strip())
        return self._untracked


def build_fact_pack(
    repo: Path,
    base: str,
    cache_dir: Path,
    include_code_review_graph: bool = True,
    include_compressed_diff: bool = True,
    git_env: dict[str, str] | None = None,
    cache_key: str | None = None,
) -> FactPack:
    return FactPackBuilder(
        repo=repo,
        base=base,
        cache_dir=cache_dir,
        include_code_review_graph=include_code_review_graph,
        include_compressed_diff=include_compressed_diff,
        git_env=git_env,
        cache_key=cache_key,
    ).build()


# -- helpers ---------------------------------------------------------------------


def _section(name: str, priority: int, content: str) -> FactPackSection:
    return FactPackSection(name=name, priority=priority, content=content)


def _section_token_cap(section_name: str, token_budget: int, caps: dict[str, int]) -> int:
    configured = caps.get(section_name, token_budget)
    return min(configured, token_budget)


def _format_json(data: dict[str, Any]) -> str:
    return "```json\n" + json.dumps(data, indent=2, sort_keys=True) + "\n```"


def _read_line_excerpt(path: Path, start: int, end: int) -> tuple[str, int]:
    lines = read_text(path).splitlines()
    bounded_end = min(end, start + MAX_DEFINITION_LINES - 1, len(lines))
    source = "\n".join(lines[max(start - 1, 0) : bounded_end])
    omitted = max(0, min(end, len(lines)) - bounded_end)
    return source, omitted


def _looks_like_manifest_config(path: str) -> bool:
    candidate = Path(path)
    if _looks_like_generated_file(path):
        return False
    return candidate.suffix in MANIFEST_CONFIG_SUFFIXES or candidate.name in MANIFEST_CONFIG_NAMES


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
    for change in changes[: crg.MAX_CRG_ITEMS]:
        lines.append(
            f"- `{change.path}` `{change.key}`: "
            f"`{change.old_value or '<absent>'}` -> `{change.new_value or '<absent>'}`"
        )
    if len(changes) > crg.MAX_CRG_ITEMS:
        lines.append(f"- ... {len(changes) - crg.MAX_CRG_ITEMS} more field changes omitted")
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


def _should_expose_untracked_to_crg(path: Path) -> bool:
    if not path.is_file() or is_probably_binary(path):
        return False
    return (
        is_source_path(path)
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
    return name in NOISY_REFERENCE_LEAVES or (name.startswith("__") and name.endswith("__"))
