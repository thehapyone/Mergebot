"""Integration of the flow steps around the crews (no LLM involved).

Drives `workspace_provisioner` + `context_builder` on a real MergeBotFlow instance
(no crews, no LLM) against a file://-cloned scratch repo. The degraded cases assert
the §5 Phase B gate: on any workspace/context failure the reviewer input is
byte-identical to today's diff-only blob. The evaluator-step tests assert the
Phase A output contract: deterministic score, enum recommendation, and the
string-rendered boundary that `AnalysisResult` and the dashboard depend on.
"""

from types import SimpleNamespace

import pytest

from mergebot.crews.schemas import ImpactReport, ReviewerVerdict
from mergebot.flow import AnalysisResult, MergeBotFlow
from mergebot.services.pr_service import PrFetchResult
from mergebot.validator.config import ApprovalPolicy, ContextConfig, WorkspaceConfig
from mergebot.workspace.manager import PrRef

DETAILS = "## Pull Request Details:\nTitle: t\n  - Patch:\nsome patch body\n"
DETAILS_NO_PATCH = "## Pull Request Details:\nTitle: t\n  - Patch: omitted\n"


def make_flow(tmp_path, pr_fetch: PrFetchResult) -> MergeBotFlow:
    flow = MergeBotFlow()
    flow.runtime = SimpleNamespace(
        platform_type="github",
        project_path="acme/scratch",
        config=SimpleNamespace(
            context=ContextConfig(workspace=WorkspaceConfig(root_dir=str(tmp_path / "ws")))
        ),
    )
    flow.pr_fetch = pr_fetch
    flow.state.pr_details = pr_fetch.details
    return flow


def scratch_pr_fetch(scratch_repo, details=DETAILS, details_no_patch=DETAILS_NO_PATCH):
    return PrFetchResult(
        details=details,
        details_no_patch=details_no_patch,
        ref=PrRef(
            clone_url=f"file://{scratch_repo.path.resolve()}",
            head_sha=scratch_repo.head_sha,
            base_sha=scratch_repo.base_sha,
            pr_number=7,
        ),
        git_token="fake-token",
    )


async def run_steps_and_cleanup(flow: MergeBotFlow) -> None:
    try:
        await flow.workspace_provisioner()
        await flow.context_builder()
    finally:
        if flow.workspace_manager and flow.workspace and not flow.workspace.degraded:
            await flow.workspace_manager.cleanup(flow.workspace)


class TestEnrichedPath:
    async def test_small_patch_is_additive(self, scratch_repo, tmp_path):
        flow = make_flow(tmp_path, scratch_pr_fetch(scratch_repo))
        await run_steps_and_cleanup(flow)

        assert not flow.workspace.degraded
        # full-patch details preserved verbatim as prefix; pack appended
        assert flow.state.pr_details.startswith(DETAILS)
        assert "# Repository Context (Fact Pack)" in flow.state.pr_details
        assert "fetch_user" in flow.state.pr_details
        # additive path: the pack must not carry a compressed diff section
        assert "## compressed_diff" not in flow.state.pr_details

    async def test_oversized_patch_is_replaced_by_compressed_diff(self, scratch_repo, tmp_path):
        huge_details = DETAILS_NO_PATCH + "x" * (6000 * 4 + 100)  # patch above the diff budget
        flow = make_flow(tmp_path, scratch_pr_fetch(scratch_repo, details=huge_details))
        await run_steps_and_cleanup(flow)

        assert flow.state.pr_details.startswith(DETAILS_NO_PATCH)
        assert "x" * 200 not in flow.state.pr_details  # raw patch replaced
        assert "## compressed_diff" in flow.state.pr_details


class TestDegradedParity:
    async def test_missing_pr_ref_keeps_details_byte_identical(self, tmp_path):
        pr_fetch = PrFetchResult(details=DETAILS, details_no_patch=DETAILS_NO_PATCH, ref=None)
        flow = make_flow(tmp_path, pr_fetch)
        await run_steps_and_cleanup(flow)

        assert flow.workspace is None
        assert flow.state.pr_details == DETAILS

    async def test_forced_clone_failure_keeps_details_byte_identical(self, tmp_path):
        pr_fetch = PrFetchResult(
            details=DETAILS,
            details_no_patch=DETAILS_NO_PATCH,
            ref=PrRef(clone_url="file:///nonexistent/repo.git", head_sha="deadbeef"),
        )
        flow = make_flow(tmp_path, pr_fetch)
        await run_steps_and_cleanup(flow)

        assert flow.workspace.degraded
        assert flow.state.pr_details == DETAILS

    async def test_missing_base_keeps_details_byte_identical(self, scratch_repo, tmp_path):
        pr_fetch = scratch_pr_fetch(scratch_repo)
        pr_fetch = PrFetchResult(
            details=pr_fetch.details,
            details_no_patch=pr_fetch.details_no_patch,
            ref=PrRef(
                clone_url=pr_fetch.ref.clone_url,
                head_sha=pr_fetch.ref.head_sha,
                base_sha=None,  # no base guarantee → no pack
            ),
            git_token=pr_fetch.git_token,
        )
        flow = make_flow(tmp_path, pr_fetch)
        await run_steps_and_cleanup(flow)

        assert not flow.workspace.degraded
        assert not flow.workspace.base_present
        assert flow.state.pr_details == DETAILS

    async def test_fact_pack_crash_keeps_details_byte_identical(
        self, scratch_repo, tmp_path, monkeypatch
    ):
        flow = make_flow(tmp_path, scratch_pr_fetch(scratch_repo))
        monkeypatch.setattr(
            "mergebot.flow.build_fact_pack",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        await run_steps_and_cleanup(flow)

        assert flow.state.pr_details == DETAILS


def make_reviewer_verdicts(code=2.0, complexity=4.0, tests=6.0, risk=8.0):
    return {
        "code_analysis_assessment": ReviewerVerdict(score=code, confidence="high", summary="code"),
        "complexity_assessment": ReviewerVerdict(
            score=complexity, confidence="high", summary="complexity"
        ),
        "test_analysis_assessment": ReviewerVerdict(
            score=tests, confidence="high", summary="tests"
        ),
        "risk_assessment": ReviewerVerdict(score=risk, confidence="high", summary="risk"),
    }


class StubEvaluatorCrew:
    def __init__(self, report):
        self.report = report
        self.inputs = None

    async def kickoff_async(self, inputs):
        self.inputs = inputs
        return SimpleNamespace(pydantic=self.report)


def make_evaluator_flow(policy, report):
    flow = MergeBotFlow()
    flow.runtime = SimpleNamespace(config=SimpleNamespace(approval_policy=policy))
    flow.crews = SimpleNamespace(impact_evaluator=StubEvaluatorCrew(report))
    flow.state.pr_id = 7
    for field, verdict in make_reviewer_verdicts().items():
        setattr(flow.state, field, verdict)
    return flow


class TestImpactEvaluatorStep:
    async def test_score_is_deterministic_and_rendered_as_string(self):
        report = ImpactReport(narrative_markdown="## Summary Table\nbody", triage_level="low")
        flow = make_evaluator_flow(policy=None, report=report)
        await flow.impact_evaluator()

        # mean of 2, 4, 6, 8 under equal weights; no policy never auto-approves
        assert flow.state.score_result.overall_score == 5.0
        assessment = flow.state.impact_assessment
        assert assessment["score"] == "5.0"
        assert isinstance(assessment["score"], str)
        assert assessment["recommendation"] == "human-review"
        assert assessment["report"].startswith("# Impact Assessment Report for PR/MR #7")
        assert "**Overall Impact Score**: 5.0" in assessment["report"]
        assert "**Recommendation**: Requires human review" in assessment["report"]
        assert "## Summary Table\nbody" in assessment["report"]

        # The string-rendered score crosses the service boundary into AnalysisResult.
        AnalysisResult(
            title="t",
            id=7,
            impact_score=assessment["score"],
            recommendation="Requires human review",
            last_reviewed="2026-07-11 10:00 UTC",
            analysis_link="#",
        )

    async def test_policy_threshold_auto_approves_with_enum_value(self):
        policy = ApprovalPolicy(
            threshold=6.0,
            weights={
                "CodeAnalysis": 0.25,
                "ComplexityAnalysis": 0.25,
                "TestAnalysis": 0.25,
                "RiskAnalysis": 0.25,
            },
        )
        report = ImpactReport(narrative_markdown="body", triage_level="low")
        flow = make_evaluator_flow(policy=policy, report=report)
        await flow.impact_evaluator()

        assert flow.state.impact_assessment["recommendation"] == "auto-approve"
        assert (
            "**Recommendation**: Auto-approve and merge" in (flow.state.impact_assessment["report"])
        )
        # The evaluator LLM receives the decided values, not the policy to apply.
        inputs = flow.crews.impact_evaluator.inputs
        assert inputs["overall_score"] == "5.0"
        assert inputs["recommendation"] == "Auto-approve and merge"
        assert ReviewerVerdict.model_validate_json(inputs["code_analysis_verdict"])

    async def test_untyped_evaluator_output_raises(self):
        flow = make_evaluator_flow(policy=None, report=None)
        with pytest.raises(RuntimeError, match="ImpactReport"):
            await flow.impact_evaluator()


class TestStateSeeding:
    def test_kickoff_inputs_seed_structured_state(self):
        """run_flow seeds state via kickoff inputs — constructor kwargs are
        silently ignored by CrewAI 1.x flows (state fields keep their defaults)."""
        flow = MergeBotFlow()
        flow._initialize_state({"pr_url": "https://x/pull/5", "pr_id": 5, "pr_title": "t"})
        assert flow.state.pr_id == 5
        assert flow.state.pr_url == "https://x/pull/5"

    def test_constructor_kwargs_do_not_seed_state(self):
        flow = MergeBotFlow(pr_id=5)
        assert flow.state.pr_id is None


class TestKnownFindingFile:
    def test_diff_fallback_without_workspace(self):
        flow = MergeBotFlow()
        flow.pr_fetch = PrFetchResult(
            details="unused",
            details_no_patch=(
                "## Pull Request Details:\n"
                "## Changes:\n"
                "File: src/app.py\n"
                "  - Additions: 1\n"
                "File: tests/test_app.py\n"
            ),
            ref=None,
        )
        assert flow.known_finding_file("src/app.py")
        assert flow.known_finding_file("./tests/test_app.py")
        assert not flow.known_finding_file("ghost.py")
        assert not flow.known_finding_file("")

    def test_workspace_checkout_lookup_rejects_jail_escape(self, tmp_path):
        checkout = tmp_path / "checkout"
        (checkout / "pkg").mkdir(parents=True)
        (checkout / "pkg" / "mod.py").write_text("x = 1\n")
        secrets = tmp_path / "secrets"
        secrets.mkdir()
        (secrets / "token").write_text("secret")

        flow = MergeBotFlow()
        flow.workspace = SimpleNamespace(checkout=checkout, degraded=False)
        assert flow.known_finding_file("pkg/mod.py")
        assert not flow.known_finding_file("../secrets/token")
        assert not flow.known_finding_file("missing.py")


@pytest.fixture(autouse=True)
def _quiet_crewai_telemetry(monkeypatch):
    monkeypatch.setenv("CREWAI_DISABLE_TELEMETRY", "true")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
