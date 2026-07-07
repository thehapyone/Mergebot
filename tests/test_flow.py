"""Integration of the new flow steps: enrichment, replacement, and degraded parity.

Drives `workspace_provisioner` + `context_builder` on a real MergeBotFlow instance
(no crews, no LLM) against a file://-cloned scratch repo. The degraded cases assert
the §5 Phase B gate: on any workspace/context failure the reviewer input is
byte-identical to today's diff-only blob.
"""

from types import SimpleNamespace

import pytest

from mergebot.flow import MergeBotFlow
from mergebot.services.pr_service import PrFetchResult
from mergebot.validator.config import ContextConfig, WorkspaceConfig
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


@pytest.fixture(autouse=True)
def _quiet_crewai_telemetry(monkeypatch):
    monkeypatch.setenv("CREWAI_DISABLE_TELEMETRY", "true")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
