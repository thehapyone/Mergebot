"""Diff parsing and compression for the fact pack.

Graduated from `mergebot/context/prototype.py` (v0.2): changed-file/hunk parsing and
the compressed-diff section body (hunks with wide context, generated-artifact
omission, untracked-file excerpts for local runs).

Phase B no-information-regression rule: until exploration tools ship, reviewers have
no way to recover content the compressed diff drops — so the compressed diff only
replaces the raw patch in the reviewer input when the raw patch exceeds the fact-pack
diff budget (`raw_patch_exceeds_budget`); below that the full patch is kept verbatim
and the fact pack is purely additive.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from mergebot.context.symbols import is_probably_binary, read_text

DIFF_MAX_LINES = 900
UNTRACKED_EXCERPT_LINES = 220

GitRunner = Callable[[list[str]], str]


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


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def raw_patch_exceeds_budget(details: str, details_no_patch: str, cap_tokens: int) -> bool:
    """No-information-regression check: does the raw patch exceed the diff budget?

    The raw-patch size is measured as the render delta between the full PR details and
    the patch-free render, so no diff re-extraction is needed.
    """
    patch_chars = max(0, len(details) - len(details_no_patch))
    return patch_chars // 4 > cap_tokens


def parse_name_status(output: str) -> list[ChangedFile]:
    files: list[ChangedFile] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        path = parts[-1]
        files.append(ChangedFile(path=path, status=status))
    return files


def parse_hunk_ranges(diff_output: str) -> list[HunkRange]:
    ranges: list[HunkRange] = []
    current_path: str | None = None
    path_pattern = re.compile(r"^\+\+\+ b/(.+)$")
    hunk_pattern = re.compile(r"^@@ .+? \+(\d+)(?:,(\d+))? @@")

    for line in diff_output.splitlines():
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
    return ranges


def build_compressed_diff(
    git: GitRunner,
    repo: Path,
    base: str,
    changed_files: list[ChangedFile],
    omitted_diff_paths: set[str],
) -> str:
    """Build the compressed-diff section body: stat header + wide-context hunks."""
    diff = git(["diff", "--find-renames", "--find-copies", "--stat", base, "--"])
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
        diff += git(
            [
                "diff",
                "--find-renames",
                "--find-copies",
                "--unified=24",
                base,
                "--",
                *tracked_diff_paths,
            ]
        )
    elif omitted_diff_paths:
        diff += "No non-generated tracked diff remains after generated artifact summarization.\n"
    else:
        diff += git(["diff", "--find-renames", "--find-copies", "--unified=24", base, "--"])
    untracked = [item.path for item in changed_files if item.status == "??"]
    if untracked:
        diff += "\n\n# Untracked files included by local mode\n"
        for path in untracked:
            if path in omitted_diff_paths:
                continue
            abs_path = repo / path
            if abs_path.is_file() and not is_probably_binary(abs_path):
                diff += f"\n## {path}\n```text\n{read_lines(abs_path, 1, UNTRACKED_EXCERPT_LINES)}\n```\n"
    if not diff.strip():
        diff = "No git diff found for the selected base."
    return limit_lines(diff, DIFF_MAX_LINES)


def read_lines(path: Path, start: int, end: int) -> str:
    lines = read_text(path).splitlines()
    bounded_end = min(end, len(lines))
    return "\n".join(lines[max(start - 1, 0) : bounded_end])


def limit_lines(text: str, max_lines: int) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text.strip()
    return "\n".join(lines[:max_lines]).rstrip() + "\n... truncated ..."
