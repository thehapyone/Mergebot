"""Diff parsing/compression and the Phase B no-information-regression budget rule."""

from mergebot.context.diff_compression import (
    build_compressed_diff,
    estimate_tokens,
    limit_lines,
    parse_hunk_ranges,
    parse_name_status,
    raw_patch_exceeds_budget,
)
from mergebot.context.fact_pack import FactPackBuilder


class TestBudgetRule:
    def test_patch_under_budget_is_additive(self):
        no_patch = "details"
        details = no_patch + "x" * (100 * 4)  # raw patch ≈ 100 tokens
        assert raw_patch_exceeds_budget(details, no_patch, cap_tokens=100) is False

    def test_patch_at_budget_edge_is_additive(self):
        no_patch = "details"
        details = no_patch + "x" * (6000 * 4)
        assert raw_patch_exceeds_budget(details, no_patch, cap_tokens=6000) is False

    def test_patch_over_budget_replaces(self):
        no_patch = "details"
        details = no_patch + "x" * (6000 * 4 + 8)
        assert raw_patch_exceeds_budget(details, no_patch, cap_tokens=6000) is True

    def test_identical_renders_never_replace(self):
        assert raw_patch_exceeds_budget("same", "same", cap_tokens=1) is False


class TestParsing:
    def test_parse_name_status(self):
        output = "M\tapp/service.py\nR100\told.py\tnew.py\nD\tgone.py\n"
        files = parse_name_status(output)
        assert [(f.status, f.path) for f in files] == [
            ("M", "app/service.py"),
            ("R100", "new.py"),
            ("D", "gone.py"),
        ]

    def test_parse_hunk_ranges_includes_deletion_only_hunks(self):
        diff = (
            "--- a/tests/test_service.py\n"
            "+++ b/tests/test_service.py\n"
            "@@ -5,3 +4,0 @@ def test_obsolete():\n"
            "-def test_obsolete():\n"
            "-    assert True\n"
            "-\n"
            "--- a/app/service.py\n"
            "+++ b/app/service.py\n"
            "@@ -2,1 +2,2 @@\n"
            "+    if user_id is None:\n"
        )
        ranges = parse_hunk_ranges(diff)
        deletion_only = [r for r in ranges if r.path == "tests/test_service.py"]
        assert len(deletion_only) == 1  # deletion-only hunk survives for test files
        assert deletion_only[0].start == 4
        assert deletion_only[0].end == 4

    def test_limit_lines_truncation_marker(self):
        text = "\n".join(f"line{i}" for i in range(20))
        limited = limit_lines(text, 5)
        assert limited.endswith("... truncated ...")
        assert "line4" in limited
        assert "line6" not in limited
        assert limit_lines("short", 5) == "short"

    def test_estimate_tokens(self):
        assert estimate_tokens("") == 1
        assert estimate_tokens("x" * 400) == 100


class TestCompressedDiff:
    def test_content_from_scratch_repo(self, scratch_repo):
        builder = FactPackBuilder(
            repo=scratch_repo.path,
            base=scratch_repo.base_sha,
            cache_dir=scratch_repo.path.parent / "cache",
            include_code_review_graph=False,
        )
        content = build_compressed_diff(
            git=lambda args: builder._git(args, check=False),
            repo=scratch_repo.path,
            base=scratch_repo.base_sha,
            changed_files=builder._changed_files(),
            omitted_diff_paths={"poetry.lock"},
        )
        assert "app/service.py" in content
        assert "user_id required" in content  # hunk content present
        assert "Generated artifact raw diff omitted" in content
        assert "# lock v2" not in content  # omitted generated diff
        # deletion-only change in the test file still visible
        assert "test_obsolete" in content
