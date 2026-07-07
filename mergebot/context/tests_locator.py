"""Test-file heuristics for the fact pack.

Conventional test-path detection and stem-based candidate matching. Lexical (ripgrep)
test references are searched by the fact-pack builder and filtered through
`looks_like_test_path`.
"""

from pathlib import Path


def looks_like_test_path(path: str) -> bool:
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


def conventional_test_candidates(tracked_files: list[str], changed_paths: list[str]) -> list[str]:
    """Test files whose stem matches a changed file's stem (test_foo / foo_test ↔ foo)."""
    test_files = [path for path in tracked_files if looks_like_test_path(path)]
    changed_stems = {Path(path).stem for path in changed_paths}
    return sorted(
        path
        for path in test_files
        if Path(path).stem.replace("test_", "").replace("_test", "") in changed_stems
    )
