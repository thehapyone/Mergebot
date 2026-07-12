"""Fact pack building and rendering: section ordering, budgets, degraded inputs."""

import os
from pathlib import Path

from mergebot.context import fact_pack as fact_pack_module
from mergebot.context.fact_pack import (
    SOURCE_GLOBS,
    FactPack,
    FactPackSection,
    _section,
    build_fact_pack,
)
from mergebot.context.symbols import SOURCE_SUFFIXES
from tests.conftest import run_git


def build_scratch_pack(scratch_repo, tmp_path, **kwargs):
    return build_fact_pack(
        repo=scratch_repo.path,
        base=scratch_repo.base_sha,
        cache_dir=tmp_path / "cache",
        include_code_review_graph=kwargs.pop("include_code_review_graph", False),
        **kwargs,
    )


class TestBuilder:
    def test_sections_and_metadata(self, scratch_repo, tmp_path):
        pack = build_scratch_pack(scratch_repo, tmp_path)
        names = [section.name for section in pack.sections]
        assert "compressed_diff" in names
        assert "touched_symbols" in names
        assert "callers_references" in names
        assert "related_tests" in names
        assert "conventions_recent_history" in names
        assert pack.metadata["base"] == scratch_repo.base_sha
        assert pack.metadata["head"] == scratch_repo.head_sha
        changed = {item["path"] for item in pack.metadata["changed_files"]}
        assert "app/service.py" in changed

    def test_touched_symbols_include_changed_function(self, scratch_repo, tmp_path):
        pack = build_scratch_pack(scratch_repo, tmp_path)
        touched = next(s for s in pack.sections if s.name == "touched_symbols")
        assert "fetch_user" in touched.content
        assert "unrelated_helper" not in touched.content

    def test_related_tests_found(self, scratch_repo, tmp_path):
        pack = build_scratch_pack(scratch_repo, tmp_path)
        related = next(s for s in pack.sections if s.name == "related_tests")
        assert "tests/test_service.py" in related.content

    def test_manifest_context_omits_lockfile_diff(self, scratch_repo, tmp_path):
        pack = build_scratch_pack(scratch_repo, tmp_path)
        manifest = next(s for s in pack.sections if s.name == "manifest_config_context")
        assert "pyproject.toml" in manifest.content
        assert pack.metadata["diff_omissions"] == ["poetry.lock"]

    def test_include_compressed_diff_false_omits_section(self, scratch_repo, tmp_path):
        pack = build_scratch_pack(scratch_repo, tmp_path, include_compressed_diff=False)
        names = [section.name for section in pack.sections]
        assert "compressed_diff" not in names
        assert pack.metadata["compressed_diff_included"] is False

    def test_symbol_cache_reuse(self, scratch_repo, tmp_path):
        build_scratch_pack(scratch_repo, tmp_path)
        pack = build_scratch_pack(scratch_repo, tmp_path)
        assert pack.metadata["cache"]["symbol_cache_hits"] > 0


class TestRender:
    def make_pack(self):
        return FactPack(
            sections=[
                _section("compressed_diff", 35, "diff body " * 50),
                _section("touched_symbols", 20, "symbols body " * 50),
                _section("callers_references", 12, "callers body " * 50),
            ]
        )

    def test_priority_order(self):
        rendered = self.make_pack().render(token_budget=12_000)
        assert rendered.index("callers_references") < rendered.index("touched_symbols")
        assert rendered.index("touched_symbols") < rendered.index("compressed_diff")

    def test_section_cap_truncates_locally(self):
        pack = FactPack(
            sections=[
                _section("callers_references", 12, "callers " * 5000),  # over its 2200 cap
                _section("compressed_diff", 35, "diff body"),
            ]
        )
        rendered = pack.render(token_budget=12_000)
        assert "token section budget" in rendered
        # a huge early section must not starve later sections
        assert "diff body" in rendered

    def test_budget_pressure_drops_lowest_priority(self):
        rendered = self.make_pack().render(token_budget=300)
        assert "callers_references" in rendered
        assert "compressed_diff" not in rendered

    def test_reserved_section_survives_budget_pressure(self):
        """When the compressed diff replaces the raw patch it must render, not drop —
        otherwise the reviewer input has neither the raw patch nor a compressed diff."""
        rendered = self.make_pack().render(token_budget=300, reserved_sections={"compressed_diff"})
        assert "compressed_diff" in rendered
        assert "diff body" in rendered

    def test_reservation_does_not_inflate_total_budget(self):
        # With ample budget, reserving changes nothing.
        plain = self.make_pack().render(token_budget=12_000)
        reserved = self.make_pack().render(
            token_budget=12_000, reserved_sections={"compressed_diff"}
        )
        assert plain == reserved

    def test_section_caps_override(self):
        pack = FactPack(sections=[_section("callers_references", 12, "callers " * 500)])
        rendered = pack.render(token_budget=12_000, section_caps={"callers_references": 50})
        assert "50 token section budget" in rendered

    def test_header_and_empty_section_placeholder(self):
        pack = FactPack(sections=[FactPackSection("touched_symbols", 20, "")])
        rendered = pack.render()
        assert rendered.startswith("# Repository Context (Fact Pack)")
        assert "_No data._" in rendered


class TestDegradedInputs:
    def test_empty_diff_repo(self, scratch_repo, tmp_path):
        pack = build_fact_pack(
            repo=scratch_repo.path,
            base="HEAD",  # no changes vs itself
            cache_dir=tmp_path / "cache",
            include_code_review_graph=False,
        )
        rendered = pack.render()
        assert "No changed hunks mapped to known symbols." in rendered

    def test_unsupported_language_falls_back_to_heuristics(self, scratch_repo, tmp_path):
        repo = scratch_repo.path
        (repo / "main.go").write_text(
            "package main\n\nfunc FetchUserRecord() int {\n\treturn 1\n}\n"
        )
        run_git(repo, "add", ".")
        run_git(repo, "commit", "-m", "add go")
        pack = build_fact_pack(
            repo=repo,
            base=scratch_repo.head_sha,
            cache_dir=tmp_path / "cache",
            include_code_review_graph=False,
        )
        touched = next(s for s in pack.sections if s.name == "touched_symbols")
        assert "FetchUserRecord" in touched.content


class TestSymlinkJail:
    """Defense in depth behind the clone's core.symlinks=false: even if a symlink
    were present in the working tree, no read may follow it outside the checkout."""

    CANARY = "SECRET-CANARY-CONTENTS-DO-NOT-LEAK"

    def _outside_secret(self, tmp_path):
        # A function so symbol extraction fires and the touched-symbol excerpt
        # read path (the primary leak vector) is exercised, not just the diff.
        secret = tmp_path / "outside" / "secret.py"
        secret.parent.mkdir(parents=True, exist_ok=True)
        secret.write_text(f"def steal_secret():\n    return '{self.CANARY}'\n", encoding="utf-8")
        return secret

    def test_changed_symlink_target_never_read(self, scratch_repo, tmp_path):
        secret = self._outside_secret(tmp_path)
        (scratch_repo.path / "leak.py").symlink_to(secret)
        run_git(scratch_repo.path, "add", "leak.py")
        run_git(scratch_repo.path, "commit", "-m", "add symlink")

        pack = build_scratch_pack(scratch_repo, tmp_path)
        rendered = pack.render()
        assert self.CANARY not in rendered
        # the symlink contributes no touched-symbol excerpt
        touched = next(s for s in pack.sections if s.name == "touched_symbols")
        assert "leak.py" not in touched.content

    def test_untracked_symlink_target_never_excerpted(self, scratch_repo, tmp_path):
        secret = self._outside_secret(tmp_path)
        # An untracked symlink in the tree feeds the compressed-diff local excerpt path.
        (scratch_repo.path / "untracked_leak.py").symlink_to(secret)

        pack = build_scratch_pack(scratch_repo, tmp_path)
        assert self.CANARY not in pack.render()


class TestGitEnvThreading:
    def test_builder_git_uses_workspace_env(self, scratch_repo, tmp_path, monkeypatch):
        """The blobless checkout lazy-fetches blobs during diff; every git call the
        builder makes must carry the workspace's authenticated env."""
        seen_envs = []
        real_run_command = fact_pack_module.run_command

        def recording_run_command(args, cwd, check=True, timeout=30, env=None):
            if args[0] == "git":
                seen_envs.append(env)
            return real_run_command(args, cwd, check=check, timeout=timeout, env=env)

        monkeypatch.setattr(fact_pack_module, "run_command", recording_run_command)
        git_env = {
            "PATH": os.environ["PATH"],
            "GIT_TERMINAL_PROMPT": "0",
            "MERGEBOT_GIT_TOKEN": "marker-token",
        }
        build_fact_pack(
            repo=scratch_repo.path,
            base=scratch_repo.base_sha,
            cache_dir=tmp_path / "cache",
            include_code_review_graph=False,
            git_env=git_env,
        )
        assert seen_envs, "expected the builder to run git"
        assert all(env is git_env for env in seen_envs)


def test_source_globs_match_symbol_suffixes():
    """Reference search and symbol extraction must agree on what counts as source."""
    assert {glob.removeprefix("*") for glob in SOURCE_GLOBS} == SOURCE_SUFFIXES


def test_build_fact_pack_smoke_render(scratch_repo, tmp_path):
    pack = build_scratch_pack(scratch_repo, tmp_path)
    rendered = pack.render()
    assert rendered.startswith("# Repository Context (Fact Pack)")
    assert str(Path(scratch_repo.path)) not in rendered.split("\n", 1)[0]
