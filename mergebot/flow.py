import re
from datetime import datetime

from crewai import Crew
from crewai.flow.flow import Flow, and_, listen, start
from crewai.utilities.events.event_listener import EventListener
from pydantic import BaseModel, Field, ValidationError

from mergebot.crews import (
    CodeAnalysis,
    ComplexityAnalysis,
    ImpactEvaluator,
    PRProcessor,
    MergeFinalizationCrew,
    RiskAnalysis,
    TestAnalysis,
)
from mergebot.utils import get_platform_type
from mergebot.validator.config import get_runtime_config, runtime_config
from mergebot.validator.logging_config import logger


# TODO: This is a temporary fix for this issue https://github.com/crewAIInc/crewAI/issues/3136
def cleanup_crewai_live_console():
    """
    Cleans up the CrewAI live console formatter if it exists.
    This is useful to stop the live console output after the flow execution.
    """
    el = getattr(EventListener, "_instance", None)
    live = getattr(getattr(el, "formatter", None), "_live", None)
    if live:
        logger.info("Stopping live console formatter...")
        el.formatter._live.stop()
        el.formatter._live = None
        logger.info("Live console formatter stopped.")


def extract_url_from_text(text: str) -> str:
    """
    Extracts the first URL found in a text string, even if it is enclosed in markdown format.
    Returns the URL if found, else an empty string.
    """
    match = re.search(r"https?://[^\s)\]]+", text)
    return match.group(0) if match else "N/A"


def extract_assessment(impact_assessment: str) -> dict:
    """
    Extracts assessment metrics from the impact assessment string:
     - Overall Impact Score
     - Recommendation
     - Report

    Args:
        impact_assessment (str): The impact assessment details.

    Returns:
        dict: A dictionary containing extracted metrics: score, recommendation, and full report.
    """
    # Flexible patterns: allows asterisks (markdown bold/italic) or none, preserves robustness
    patterns = {
        "score": r"^\s*\*+?\s*Overall Impact Score\s*\*+?\s*:\s*(.+)$",
        "recommendation": r"^\s*\*+?\s*Recommendation\s*\*+?\s*:\s*(.+)$",
    }
    extracted_metrics = {
        key: re.search(pattern, impact_assessment, re.MULTILINE | re.IGNORECASE)
        for key, pattern in patterns.items()
    }
    return {
        "score": (
            extracted_metrics["score"].group(1).strip()
            if extracted_metrics["score"]
            else "N/A"
        ),
        "recommendation": (
            extracted_metrics["recommendation"].group(1).strip()
            if extracted_metrics["recommendation"]
            else ""
        ),
        "report": impact_assessment.strip(),
    }


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



sample_report="""
```markdown
# Impact Assessment Report for PR/MR #214

**Overall Impact Score**: 2.6

**Recommendation**: Auto-approve and merge

---

## Summary Table

| Assessment Agent             | Score | Key Findings                                                             | Suggested Actions                                              |
|------------------------------|-------|--------------------------------------------------------------------------|---------------------------------------------------------------|
| Code Analysis Agent          | 3.0   | Only library version bump (Google.Protobuf). Tests pass; no code change. | Monitor post-merge for protobuf anomalies; review release notes|
| Complexity Assessment Agent  | 1.0   | Minimal—single-line dependency update. No new logic or complexity added. | No action required beyond standard dependence maintenance      |
| Test Coverage Agent          | 1.0   | No effect on tests/coverage. All relevant tests pass.                    | Maintain test focus on protobuf usage; no new tests required   |
| Risk Assessment Agent        | 5.0   | Moderate risk: core serialization lib updated. CI fails are infra, not code. | Review changelog, resolve unrelated pipeline failures, notify consumers  |

---

## Detailed Assessments

- **Code Analysis Agent**: Score 3.0
  - **Findings**: The PR exclusively upgrades the `Google.Protobuf` dependency from 3.26.1 to 3.31.1, with no changes to source code or business logic. Tests (unit/integration) pass; CI/root cause analysis shows failures are infra-related, not from code. Risk is low, but third-party upgrades should always be monitored for subtle issues.
  - **Suggested Action**: Merge after checking for relevant changes in upstream release notes. Observe production logs for protobuf anomalies. Address CI environment/config separately.

- **Complexity Assessment Agent**: Score 1.0
  - **Findings**: The update is a single-line version change in a project file. No new code paths, logic, or architecture changes. No impact on project’s complexity or maintainability. Routine housekeeping update.
  - **Suggested Action**: No complexity mitigation required. Maintain periodic review of dependency updates.

- **Test Coverage Agent**: Score 1.0
  - **Findings**: No new/removed code. Test coverage is fully preserved. All existing tests ran and passed (except infra-related jobs). No reduction in coverage; no additional tests needed for this change, assuming previous protobuf usage is well-tested.
  - **Suggested Action**: Continue to keep protobuf-related logic under test. No new tests required for this update.

- **Risk Assessment Agent**: Score 5.0
  - **Findings**: As a core serialization dependency, even minor updates can carry risk (compatibility, perf, security). Automated tests pass; CI failures are infra-related. Moderate risk score is assigned mainly due to the criticality and the library’s role in inter-service communication.
  - **Suggested Action**: Review and communicate protobuf changelog and any required adjustments. Resolve CI credential/build issues. If feasible, orchestrate a staged rollout. Notify dependent teams.

---

## Triage & Next Steps
**Triage Level**: Low

- **Reviewer Guidance**: No critical action or concern identified regarding the version bump itself. Reviewers should verify that protobuf release notes have no breaking changes affecting custom features (e.g., custom serialization, hand-written mappers). Validate that failed pipeline jobs are not tied to this upgrade.
- **Blockers**: None specific to the code change. Recommend fixing CI pipeline issues in parallel, but these are not direct blockers to merging this PR given the context and scope.

---

## Justification

This PR performs a routine upgrade of the `Google.Protobuf` dependency from 3.26.1 to 3.31.1 without any accompanying code or logic changes. The modification is limited to updating a single version line in the project configuration. Complexity and test impact are both minimal, as confirmed by passing unit and integration tests. 

While code and complexity impact are low, the risk assessment is moderate (5/10) due to the critical, foundational nature of the dependency—changes in core libraries always merit close attention for subtle runtime or compatibility issues. However, current test outcomes, analysis of CI failures (infrastructure-related), and absence of known upstream breaking changes together indicate that the risk is well-contained, provided post-merge monitoring and best-practice dependency hygiene continue.

Applying configured weights as follows:

- CodeAnalysis: 3.0 × 0.40 = 1.20
- ComplexityAnalysis: 1.0 × 0.20 = 0.20
- TestAnalysis: 1.0 × 0.20 = 0.20
- RiskAnalysis: 5.0 × 0.20 = 1.00

**Total weighted impact score = 1.20 + 0.20 + 0.20 + 1.00 = 2.60**

This is **below the auto-approval threshold (3.0)**. Given these results and the clear separation of test/system errors from the dependency change, this PR qualifies for auto-approval and merging.

---

> _This report was automatically generated by [MergeBot](https://github.com/thehapyone/Mergebot)_
```
"""

class MergeBotCrews(BaseModel):
    code_analysis: Crew = Field(default_factory=lambda: CodeAnalysis().crew())
    complexity_assessment: Crew = Field(
        default_factory=lambda: ComplexityAnalysis().crew()
    )
    test_analysis: Crew = Field(default_factory=lambda: TestAnalysis().crew())
    risk_analysis: Crew = Field(default_factory=lambda: RiskAnalysis().crew())
    impact_evaluator: Crew = Field(default_factory=lambda: ImpactEvaluator().crew())
    pr_retriever: Crew = Field(default_factory=lambda: PRProcessor().crew())
    publicator: Crew = Field(default_factory=lambda: MergeFinalizationCrew().crew())


class MergeBotState(BaseModel):
    pr_url: str = ""
    pr_id: int = None
    pr_title: str = ""
    pr_details: str = ""
    code_analysis_assessment: str = ""
    complexity_assessment: str = ""
    test_analysis_assessment: str = ""
    risk_assessment: str = ""
    impact_assessment: dict = {
        "score": "",
        "recommendation": "",
        "report": "",
    }
    analysis_link: str = ""
    impact_evaluator: str = ""
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


class MergeBotFlow(Flow[MergeBotState]):
    @start()
    def initialize(self):
        logger.info("Commencing and starting the MergeBot")
        self.crews = MergeBotCrews()
        # The ID field is automatically available
        logger.info(f"Flow with ID: {self.state.id} initialized")

    # @listen(initialize)
    # async def pr_retriever(self):
    #     """Runs a Crew to extract Pull Request Details"""
    #     pr_details = (
    #         await self.crews.pr_retriever.kickoff_async(
    #             inputs={"input": self.state.pr_url}
    #         )
    #     ).raw
    #     self.state.pr_details = pr_details

    # @listen(pr_retriever)
    # async def code_analysis_assessment(self):
    #     """Runs the Code Analysis Assessment on the PR details"""
    #     self.state.code_analysis_assessment = (
    #         await self.crews.code_analysis.kickoff_async(
    #             inputs={"pr_details": self.state.pr_details}
    #         )
    #     ).raw

    # @listen(pr_retriever)
    # async def complexity_assessment(self):
    #     """Runs the Complexity Assessment on the PR details"""
    #     self.state.complexity_assessment = (
    #         await self.crews.complexity_assessment.kickoff_async(
    #             inputs={"pr_details": self.state.pr_details}
    #         )
    #     ).raw

    # @listen(pr_retriever)
    # async def test_analysis_assessment(self):
    #     """Runs the Test Analysis Assessment on the PR details"""
    #     self.state.test_analysis_assessment = (
    #         await self.crews.test_analysis.kickoff_async(
    #             inputs={"pr_details": self.state.pr_details}
    #         )
    #     ).raw

    # @listen(pr_retriever)
    # async def risk_assessment(self):
    #     """Runs the Risk Analysis Assessment on the PR details"""
    #     self.state.risk_assessment = (
    #         await self.crews.risk_analysis.kickoff_async(
    #             inputs={"pr_details": self.state.pr_details}
    #         )
    #     ).raw

    # @listen(
    #     and_(
    #         code_analysis_assessment,
    #         complexity_assessment,
    #         test_analysis_assessment,
    #         risk_assessment,
    #     )
    # )
    # async def impact_evaluator(self):
    #     """Runs the Impact Evaluator Analysis Assessment on the PR details"""
    #     approval_policy = get_runtime_config(as_pydantic=True).approval_policy
    #     policy_str = approval_policy.to_markdown() if approval_policy else ""
    #     self.state.impact_assessment = extract_assessment(
    #         (
    #             await self.crews.impact_evaluator.kickoff_async(
    #                 inputs={
    #                     "pr_id": self.state.pr_id,
    #                     "approval_policy": policy_str,
    #                     "code_analysis_assessment": self.state.code_analysis_assessment,
    #                     "complexity_assessment": self.state.complexity_assessment,
    #                     "test_analysis": self.state.test_analysis_assessment,
    #                     "risk_assessment": self.state.risk_assessment,
    #                 }
    #             )
    #         ).raw
    #     )

    @listen(initialize)
    async def pr_decision(self):
        """Runs the PR decision crew on the impact assessment report"""
        response = await self.crews.publicator.kickoff_async(
            inputs={
                "pr_id": self.state.pr_id,
                "impact_assessment_report": sample_report,
            }
        )
        self.state.analysis_link = extract_url_from_text(response.tasks_output[0].raw)
        self.state.impact_evaluator = response.raw

        # Store the crew usage metrics
        self.state.usage_metrics = {
            crew_name: crew.usage_metrics.model_dump() for crew_name, crew in self.crews
        }

        logger.info("\nFinal Response:")
        logger.info(self.state.impact_evaluator)


async def run_flow(
    pr_url: str, pr_id: int = None, pr_title: str = "", project: str = None
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
    pr_id_val = pr_id or extract_pr_id(pr_url)
    if not pr_id_val:
        raise Exception(f"Failed to extract PR/MR ID from URL: {pr_url}")

    inital_state = {
        "pr_url": pr_url,
        "pr_id": pr_id_val,
        "pr_title": pr_title,
        "project": project,
    }

    if project and get_platform_type() == "gitlab":
        runtime_config.set("repository.gitlab.gitlab_repository", project)

    mergebot = MergeBotFlow(**inital_state)
    flow_id = mergebot.flow_id

    logger.info(f"Initiated MergeBotFlow with Flow ID: {flow_id}")

    await mergebot.kickoff_async()

    cleanup_crewai_live_console()

    try:
        analysis_result = AnalysisResult(
            title=mergebot.state.pr_title,
            id=mergebot.state.pr_id,
            impact_score=mergebot.state.impact_assessment.get("score"),
            recommendation=mergebot.state.impact_assessment.get("recommendation"),
            last_reviewed=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
            analysis_link=mergebot.state.analysis_link,
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
