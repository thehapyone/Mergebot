import asyncio
import re
from datetime import datetime
from pathlib import Path

from crewai import Crew
from crewai.flow.flow import Flow, and_, listen, start
from pydantic import BaseModel, Field, ValidationError

from mergebot.context.diff_compression import raw_patch_exceeds_budget
from mergebot.context.fact_pack import SECTION_TOKEN_CAPS, build_fact_pack
from mergebot.crews import (
    CodeAnalysis,
    ComplexityAnalysis,
    ImpactEvaluator,
    RiskAnalysis,
    TestAnalysis,
)
from mergebot.crews.schemas import ImpactReport, ReviewerVerdict
from mergebot.project_registry import ProjectRuntime
from mergebot.services import decision_service, pr_service
from mergebot.services.pr_service import PrFetchResult
from mergebot.services.scoring import (
    REVIEWER_WEIGHT_KEYS,
    ScoreResult,
    compute_weighted_score,
    render_recommendation,
)
from mergebot.validator.logging_config import logger
from mergebot.workspace.manager import (
    Workspace,
    WorkspaceLimits,
    WorkspaceManager,
    credential_from_runtime,
)

# File header lines in the pretty-printed PR details (patches omitted in the
# no-patch render, so every match is a real changed-file path).
_DETAILS_FILE_RE = re.compile(r"^File: (.+)$", re.MULTILINE)


def extract_pr_id(output_string):
    """
    Extracts the PR/MR ID from a GitHub or GitLab URL.
    Supports:
      - GitHub: .../pull/123
      - GitLab: .../merge_requests/123
    """
    patterns = [
        r"https?://.+/pull/(\d+)",  # GitHub PR
        r"https?://.+/merge_requests/(\d+)",  # GitLab MR
    ]
    for pattern in patterns:
        match = re.search(pattern, output_string)
        if match:
            return int(match.group(1))
    return None


class MergeBotCrews:
    """Container for lazily-instantiated crews tied to a specific project config."""

    def __init__(self, config, finding_file_checker=None):
        reviewer_kwargs = {"config": config, "finding_file_checker": finding_file_checker}
        self._crews = {
            "code_analysis": CodeAnalysis(**reviewer_kwargs).crew(),
            "complexity_assessment": ComplexityAnalysis(**reviewer_kwargs).crew(),
            "test_analysis": TestAnalysis(**reviewer_kwargs).crew(),
            "risk_analysis": RiskAnalysis(**reviewer_kwargs).crew(),
            "impact_evaluator": ImpactEvaluator(config=config).crew(),
        }

    def __getattr__(self, item: str) -> Crew:
        try:
            return self._crews[item]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(item) from exc

    def __iter__(self):
        return iter(self._crews.items())


class MergeBotState(BaseModel):
    pr_url: str = ""
    pr_id: int = None
    pr_title: str = ""
    pr_details: str = ""
    code_analysis_assessment: ReviewerVerdict | None = None
    complexity_assessment: ReviewerVerdict | None = None
    test_analysis_assessment: ReviewerVerdict | None = None
    risk_assessment: ReviewerVerdict | None = None
    score_result: ScoreResult | None = None
    impact_assessment: dict = {
        "score": "",
        "recommendation": "",
        "report": "",
    }
    final_decision: dict = Field(
        default_factory=dict, description="Final decision summary and metadata."
    )
    usage_metrics: dict = Field(
        default_factory=dict, description="Usage metrics for the crew's execution."
    )


class AnalysisResult(BaseModel):
    title: str
    id: int
    impact_score: str = Field(default="")
    recommendation: str = Field(default="")
    last_reviewed: str
    analysis_link: str
    approved: bool = Field(default=False)
    action_taken: str = Field(default="")
    usage_metrics: dict = Field(
        default_factory=dict, description="Crew usage metrics for this PR/MR"
    )


class MergeBotFlow(Flow[MergeBotState]):
    runtime: ProjectRuntime | None = None
    # Workspace/context artifacts live on the flow instance, not in the pydantic state:
    # they carry paths and (via pr_fetch) the git token, which must never be serialized.
    pr_fetch: PrFetchResult | None = None
    workspace: Workspace | None = None
    workspace_manager: WorkspaceManager | None = None
    _diff_file_names: set[str] | None = None

    def known_finding_file(self, path: str) -> bool:
        """Guardrail hook: does `path` exist in the workspace checkout or the diff?

        Crews are constructed before the workspace exists, so this resolves at
        guardrail-execution time against whatever this review actually has.
        """
        candidate = (path or "").strip().lstrip("/")
        candidate = candidate.removeprefix("./")
        if not candidate:
            return False
        workspace = self.workspace
        if workspace is not None and not workspace.degraded:
            try:
                checkout = workspace.checkout.resolve()
                resolved = (checkout / candidate).resolve()
                if resolved.is_relative_to(checkout) and resolved.exists():
                    return True
            except OSError:
                pass
        if self._diff_file_names is None:
            details = self.pr_fetch.details_no_patch if self.pr_fetch else ""
            self._diff_file_names = {match.strip() for match in _DETAILS_FILE_RE.findall(details)}
        return candidate in self._diff_file_names

    @start()
    def initialize(self):
        logger.info("Commencing and starting the MergeBot")
        if self.runtime is None:
            raise RuntimeError("MergeBotFlow runtime was not configured")
        self.crews = MergeBotCrews(
            self.runtime.config, finding_file_checker=self.known_finding_file
        )

    @listen(initialize)
    async def pr_retriever(self):
        """Fetches PR/MR details using service layer"""
        self.pr_fetch = await pr_service.get_pull_or_merge_request(self.state.pr_id, self.runtime)
        self.state.pr_details = self.pr_fetch.details

    @listen(pr_retriever)
    async def workspace_provisioner(self):
        """Provisions a shallow per-review clone. Failures degrade to diff-only."""
        try:
            pr_ref = self.pr_fetch.ref if self.pr_fetch else None
            if pr_ref is None:
                logger.warning(
                    "No typed PR metadata available; skipping workspace (diff-only review)."
                )
                return
            workspace_config = self.runtime.config.context.workspace
            self.workspace_manager = WorkspaceManager(
                WorkspaceLimits(
                    root_dir=Path(workspace_config.root_dir),
                    clone_timeout=workspace_config.clone_timeout,
                    depth=workspace_config.depth,
                    max_repo_mb=workspace_config.max_repo_mb,
                )
            )
            await self.workspace_manager.sweep_orphans()
            credential = None
            if self.pr_fetch.git_token:
                credential = credential_from_runtime(
                    self.runtime.platform_type, self.pr_fetch.git_token
                )
            self.workspace = await self.workspace_manager.provision(pr_ref, credential=credential)
        except Exception as e:
            logger.warning(f"Workspace provisioning failed; continuing diff-only: {e}")
            self.workspace = None

    @listen(workspace_provisioner)
    async def context_builder(self):
        """Builds the deterministic fact pack and appends it to the reviewer input.

        Input-side only: on any failure the pr_details blob stays exactly as today.
        The compressed diff replaces the raw patch only when the raw patch exceeds
        the fact-pack diff budget (no-information-regression rule); below that the
        full patch is kept and the pack is purely additive.
        """
        try:
            workspace = self.workspace
            if workspace is None or workspace.degraded:
                return
            if not workspace.base_present:
                logger.warning(
                    "Base commit unavailable in workspace; skipping fact pack (diff-only review)."
                )
                return
            fact_pack_config = self.runtime.config.context.fact_pack
            section_caps = {**SECTION_TOKEN_CAPS, **fact_pack_config.section_caps}
            replace_patch = raw_patch_exceeds_budget(
                self.pr_fetch.details,
                self.pr_fetch.details_no_patch,
                section_caps["compressed_diff"],
            )
            cache_dir = Path(self.runtime.config.context.workspace.root_dir) / ".symbol-cache"
            fact_pack = await asyncio.to_thread(
                build_fact_pack,
                repo=workspace.checkout,
                base=workspace.base_sha,
                cache_dir=cache_dir,
                include_compressed_diff=replace_patch,
                git_env=workspace.git_env,
                cache_key=self.runtime.project_path,
            )
            rendered = fact_pack.render(
                token_budget=fact_pack_config.token_budget,
                section_caps=section_caps,
                # When the compressed diff replaces the raw patch, it must survive
                # budget pressure — dropping it would leave reviewers with no diff.
                reserved_sections={"compressed_diff"} if replace_patch else None,
            )
            base_text = self.pr_fetch.details_no_patch if replace_patch else self.pr_fetch.details
            self.state.pr_details = f"{base_text}\n\n{rendered}"
        except Exception as e:
            logger.warning(f"Fact pack build failed; continuing diff-only: {e}")

    async def _kickoff_reviewer(self, crew: Crew, crew_name: str) -> ReviewerVerdict:
        """Run one reviewer crew and return its typed verdict."""
        output = await crew.kickoff_async(inputs={"pr_details": self.state.pr_details})
        verdict = output.pydantic
        if not isinstance(verdict, ReviewerVerdict):
            raise RuntimeError(
                f"{crew_name} did not produce a structured ReviewerVerdict "
                f"(got {type(verdict).__name__})"
            )
        return verdict

    @listen(context_builder)
    async def code_analysis_assessment(self):
        """Runs the Code Analysis Assessment on the PR details"""
        self.state.code_analysis_assessment = await self._kickoff_reviewer(
            self.crews.code_analysis, "CodeAnalysis"
        )

    @listen(context_builder)
    async def complexity_assessment(self):
        """Runs the Complexity Assessment on the PR details"""
        self.state.complexity_assessment = await self._kickoff_reviewer(
            self.crews.complexity_assessment, "ComplexityAnalysis"
        )

    @listen(context_builder)
    async def test_analysis_assessment(self):
        """Runs the Test Analysis Assessment on the PR details"""
        self.state.test_analysis_assessment = await self._kickoff_reviewer(
            self.crews.test_analysis, "TestAnalysis"
        )

    @listen(context_builder)
    async def risk_assessment(self):
        """Runs the Risk Analysis Assessment on the PR details"""
        self.state.risk_assessment = await self._kickoff_reviewer(
            self.crews.risk_analysis, "RiskAnalysis"
        )

    @listen(
        and_(
            code_analysis_assessment,
            complexity_assessment,
            test_analysis_assessment,
            risk_assessment,
        )
    )
    async def impact_evaluator(self):
        """Computes the deterministic score, then has the evaluator write the narrative.

        The score and recommendation come from `compute_weighted_score` and are
        rendered into the report header in code; the LLM cannot alter them.
        """
        verdicts = {
            "CodeAnalysis": self.state.code_analysis_assessment,
            "ComplexityAnalysis": self.state.complexity_assessment,
            "TestAnalysis": self.state.test_analysis_assessment,
            "RiskAnalysis": self.state.risk_assessment,
        }
        score_result = compute_weighted_score(verdicts, self.runtime.config.approval_policy)
        self.state.score_result = score_result

        score_str = f"{score_result.overall_score:.1f}"
        recommendation_display = render_recommendation(score_result.recommendation)
        per_reviewer_scores = ", ".join(
            f"{name}: {score_result.per_reviewer[name]} (weight {score_result.weights_used[name]})"
            for name in REVIEWER_WEIGHT_KEYS
        )
        output = await self.crews.impact_evaluator.kickoff_async(
            inputs={
                "pr_id": self.state.pr_id,
                "overall_score": score_str,
                "recommendation": recommendation_display,
                "per_reviewer_scores": per_reviewer_scores,
                "code_analysis_verdict": verdicts["CodeAnalysis"].model_dump_json(indent=2),
                "complexity_verdict": verdicts["ComplexityAnalysis"].model_dump_json(indent=2),
                "test_analysis_verdict": verdicts["TestAnalysis"].model_dump_json(indent=2),
                "risk_verdict": verdicts["RiskAnalysis"].model_dump_json(indent=2),
            }
        )
        report = output.pydantic
        if not isinstance(report, ImpactReport):
            raise RuntimeError(
                f"ImpactEvaluator did not produce a structured ImpactReport "
                f"(got {type(report).__name__})"
            )

        header = (
            f"# Impact Assessment Report for PR/MR #{self.state.pr_id}\n\n"
            f"**Overall Impact Score**: {score_str}\n\n"
            f"**Recommendation**: {recommendation_display}\n\n"
            "---\n\n"
        )
        self.state.impact_assessment = {
            "score": score_str,
            "recommendation": score_result.recommendation,
            "report": header + report.narrative_markdown.strip() + "\n",
        }

    @listen(impact_evaluator)
    async def pr_decision(self):
        """
        Finalize by delegating to the decision service to post the assessment,
        approve if applicable, and auto-merge under configured guardrails.
        """
        self.state.final_decision = await decision_service.process_decision(
            self.state.pr_id, self.state.impact_assessment, self.runtime
        )

        # Store the crew usage metrics
        self.state.usage_metrics = {
            crew_name: crew.usage_metrics.model_dump() for crew_name, crew in self.crews
        }

        logger.info("\nFinal Decision:")
        logger.info(self.state.final_decision)


async def run_flow(
    pr_url: str,
    pr_id: int | None = None,
    pr_title: str = "",
    project: str | None = None,
    runtime: ProjectRuntime | None = None,
) -> AnalysisResult:
    """
    Initiates the MergeBotFlow to process a pull request (PR) or merge request (MR) URL.

    Args:
        pr_url (str): The URL of the pull request or merge request to process.
        pr_id (int): Optional PR/MR ID to process.
        pr_title (str): Optional PR/MR title.
        project (str): The repository path.

    Returns:
        AnalysisResult: Validated analysis result for dashboard/tracking.
    """
    if runtime is None:
        raise ValueError("Project runtime must be provided to run_flow")

    pr_id_val = pr_id or extract_pr_id(pr_url)
    if not pr_id_val:
        raise Exception(f"Failed to extract PR/MR ID from URL: {pr_url}")

    # CrewAI 1.x flows seed state via kickoff inputs; constructor kwargs are
    # silently ignored (state fields would stay at their defaults).
    inital_state = {
        "pr_url": pr_url,
        "pr_id": pr_id_val,
        "pr_title": pr_title,
    }

    mergebot = MergeBotFlow()
    mergebot.runtime = runtime
    flow_id = mergebot.flow_id

    logger.info(
        f"Initiated MergeBotFlow with Flow ID: {flow_id} for project {runtime.project_path}"
    )

    try:
        await mergebot.kickoff_async(inputs=inital_state)
    finally:
        # Workspaces are per-review and must not outlive the flow, success or failure.
        if mergebot.workspace_manager and mergebot.workspace and not mergebot.workspace.degraded:
            await mergebot.workspace_manager.cleanup(mergebot.workspace)

    try:
        analysis_result = AnalysisResult(
            title=mergebot.state.pr_title,
            id=mergebot.state.pr_id,
            impact_score=mergebot.state.final_decision.get("impact_score"),
            recommendation=mergebot.state.final_decision.get("recommendation"),
            last_reviewed=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
            analysis_link=mergebot.state.final_decision.get("analysis_link"),
            approved=mergebot.state.final_decision.get("approved", False),
            action_taken=mergebot.state.final_decision.get("action_taken", ""),
            usage_metrics=mergebot.state.usage_metrics,
        )
    except ValidationError as e:
        logger.error(f"AnalysisResult validation failed: {e}")
        raise

    logger.info(f"Flow with id: {flow_id} completed successfully.")
    logger.info("Flow Usage Metrics:-----------------------------------------")
    for crew_name, usage_metrics in mergebot.state.usage_metrics.items():
        logger.info(f"{crew_name}: {usage_metrics}")
    logger.info("----------------------Flow Usage Metrics:----------------------")
    return analysis_result
