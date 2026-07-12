"""CRG env scrubbing, test-gap reconciliation, and assessment stripping."""

from mergebot.context import crg
from mergebot.context.crg import scrubbed_env
from mergebot.context.fact_pack import FactPackBuilder


class TestScrubbedEnv:
    def test_credential_material_is_stripped(self, monkeypatch):
        """CRG is a third-party binary parsing untrusted repo content: the git
        credential (and any other secret) must never reach its environment."""
        monkeypatch.setenv("MERGEBOT_GIT_TOKEN", "git-cred")
        monkeypatch.setenv("MERGEBOT_GIT_USERNAME", "x-access-token")
        monkeypatch.setenv("GIT_ASKPASS", "/ws/secrets/askpass.sh")
        monkeypatch.setenv("GITHUB_TOKEN", "platform-cred")
        monkeypatch.setenv("GITLAB_PERSONAL_ACCESS_TOKEN", "platform-cred")
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "pem")
        monkeypatch.setenv("OPENAI_API_KEY", "llm-cred")
        monkeypatch.setenv("SOME_WEBHOOK_SECRET", "hook-cred")
        monkeypatch.setenv("PATH", "/usr/bin:/bin")

        env = scrubbed_env()

        for name in (
            "MERGEBOT_GIT_TOKEN",
            "MERGEBOT_GIT_USERNAME",
            "GIT_ASKPASS",
            "GITHUB_TOKEN",
            "GITLAB_PERSONAL_ACCESS_TOKEN",
            "GITHUB_APP_PRIVATE_KEY",
            "OPENAI_API_KEY",
            "SOME_WEBHOOK_SECRET",
        ):
            assert name not in env
        assert env["PATH"] == "/usr/bin:/bin"
        # a missing credential must fail fast, never hang a headless container
        assert env["GIT_TERMINAL_PROMPT"] == "0"


def make_builder(scratch_repo, tmp_path) -> FactPackBuilder:
    return FactPackBuilder(
        repo=scratch_repo.path,
        base=scratch_repo.base_sha,
        cache_dir=tmp_path / "cache",
        include_code_review_graph=False,
    )


class TestReconciliation:
    def test_gaps_split_by_lexical_evidence(self, scratch_repo, tmp_path, monkeypatch):
        builder = make_builder(scratch_repo, tmp_path)
        report_json = {
            "test_gaps": [
                {"name": "fetch_user", "file_path": "app/service.py", "line_start": 1},
                {"name": "orphan_symbol", "file_path": "app/service.py", "line_start": 9},
            ]
        }
        # Deterministic lexical evidence: only fetch_user is referenced from a test file.
        monkeypatch.setattr(
            builder,
            "_rg_word",
            lambda word, **kwargs: (
                ["tests/test_service.py:3:5:def test_fetch_user():"] if word == "fetch_user" else []
            ),
        )
        section = builder._test_coverage_graph_section(report_json)
        content = section.content
        no_refs_block, refs_block = content.split(
            "Changed symbols where CRG has no recorded test edge but lexical"
        )
        assert "orphan_symbol" in no_refs_block
        assert "fetch_user" in refs_block
        assert "tests/test_service.py" in refs_block
        # reconciliation disclaimer: disagreement is graph-resolution, not coverage, evidence
        assert "not \ncoverage evidence" in content or "not coverage evidence" in content.replace(
            "\n", " "
        )

    def test_no_gaps_yields_no_section(self, scratch_repo, tmp_path):
        builder = make_builder(scratch_repo, tmp_path)
        assert builder._test_coverage_graph_section({"test_gaps": []}) is None
        assert builder._test_coverage_graph_section(None) is None

    def test_noisy_leaf_symbols_skip_lexical_search(self, scratch_repo, tmp_path):
        builder = make_builder(scratch_repo, tmp_path)
        assert builder._test_reference_matches("Service.__init__") == []
        assert builder._test_reference_matches("run") == []


class TestAssessmentStripping:
    def test_risk_fields_never_rendered(self, scratch_repo):
        report_json = {
            "changed_functions": [
                {
                    "name": "fetch_user",
                    "file_path": "app/service.py",
                    "line_start": 1,
                    "line_end": 5,
                    "risk_score": 9.7,
                }
            ],
            "review_priorities": [{"name": "fetch_user", "rank": 1}],
        }
        content = crg._format_crg_report(report_json, raw_text="", repo=scratch_repo.path)
        assert "9.7" not in content
        assert "risk_score" not in content
        assert "review_priorities" not in content
        assert "not rendered into this shared fact pack" in content

    def test_unparseable_output_is_filtered(self, scratch_repo):
        raw = (
            "changed: fetch_user\n"
            "risk_score: 9.7\n"
            "review priority: HIGH\n"
            "untested code detected\n"
            "plain structural line\n"
        )
        content = crg._format_crg_report(None, raw_text=raw, repo=scratch_repo.path)
        assert "9.7" not in content
        assert "priority" not in content.split("withheld")[1]
        assert "untested" not in content.split("withheld")[1]
        assert "plain structural line" in content

    def test_signals_used_internally_for_ordering_only(self, scratch_repo, tmp_path):
        """risk_score may order symbols but never surfaces in the section text."""
        builder = make_builder(scratch_repo, tmp_path)
        report_json = {
            "changed_functions": [
                {
                    "name": "fetch_user",
                    "file_path": "app/service.py",
                    "line_start": 1,
                    "line_end": 5,
                    "risk_score": 8.2,
                }
            ]
        }
        signals = crg.crg_symbol_signals(report_json, scratch_repo.path)
        assert signals and signals[0].risk_score == 8.2
        changed_files = builder._changed_files()
        hunks = builder._hunk_ranges()
        symbols = builder._symbols_for_changed_files(changed_files)
        touched = builder._touched_symbols(hunks, symbols)
        section = builder._touched_symbols_section(
            crg.rank_symbols_by_crg(touched, signals), signals
        )
        assert "8.2" not in section.content
        assert "risk" not in section.content.lower()
        assert "crg: `matched changed symbol" in section.content
