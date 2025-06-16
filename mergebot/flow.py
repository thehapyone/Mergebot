import re
from datetime import datetime

from crewai import Crew
from crewai.flow.flow import Flow, and_, listen, start
from pydantic import BaseModel, Field, ValidationError

from mergebot.crews import (
    CodeAnalysis,
    ComplexityAnalysis,
    ImpactEvaluator,
    MRProcessor,
    Publication,
    RiskAnalysis,
    TestAnalysis,
)
from mergebot.logging_config import logger
from mergebot.validator.config import get_runtime_config


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


def extract_merge_request_id(output_string):
    pattern = r"https://.+/merge_requests/(\d+)"
    match = re.search(pattern, output_string)
    return int(match.group(1)) if match else None


class MergeBotCrews(BaseModel):
    code_analysis: Crew = CodeAnalysis().crew()
    complexity_assessment: Crew = ComplexityAnalysis().crew()
    test_analysis: Crew = TestAnalysis().crew()
    risk_analysis: Crew = RiskAnalysis().crew()
    impact_evaluator: Crew = ImpactEvaluator().crew()
    mr_processor: Crew = MRProcessor().crew()
    publicator: Crew = Publication().crew()


class MergeBotState(BaseModel):
    mr_url: str = ""
    mr_id: int = None
    mr_title: str = ""
    mr_details: str = ""
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


class AnalysisResult(BaseModel):
    title: str
    iid: int
    impact_score: str = Field(default="")
    recommendation: str = Field(default="")
    last_reviewed: str
    analysis_link: str


class MergeBotFlow(Flow[MergeBotState]):
    crews = MergeBotCrews()

    @start()
    def begin(self):
        logger.info("Commencing and starting the MergeBot")

    @listen(begin)
    async def mr_retriever(self):
        """Runs a Crew to extract Merge Request Details"""
        mr_details = (
            await self.crews.mr_processor.kickoff_async(
                inputs={"input": self.state.mr_url}
            )
        ).raw
        self.state.mr_details = mr_details

    @listen(mr_retriever)
    async def code_analysis_assessment(self):
        """Runs the Code Analysis Assessment on the MR details"""
        self.state.code_analysis_assessment = (
            await self.crews.code_analysis.kickoff_async(
                inputs={"mr_details": self.state.mr_details}
            )
        ).raw

    @listen(mr_retriever)
    async def complexity_assessment(self):
        """Runs the Complexity Assessment on the MR details"""
        self.state.complexity_assessment = (
            await self.crews.complexity_assessment.kickoff_async(
                inputs={"mr_details": self.state.mr_details}
            )
        ).raw

    @listen(mr_retriever)
    async def test_analysis_assessment(self):
        """Runs the Test Analysis Assessment on the MR details"""
        self.state.test_analysis_assessment = (
            await self.crews.test_analysis.kickoff_async(
                inputs={"mr_details": self.state.mr_details}
            )
        ).raw

    @listen(mr_retriever)
    async def risk_assessment(self):
        """Runs the Risk Analysis Assessment on the MR details"""
        self.state.risk_assessment = (
            await self.crews.risk_analysis.kickoff_async(
                inputs={"mr_details": self.state.mr_details}
            )
        ).raw

    @listen(
        and_(
            code_analysis_assessment,
            complexity_assessment,
            test_analysis_assessment,
            risk_assessment,
        )
    )
    async def impact_evaluator(self):
        """Runs the Impact Evaluator Analysis Assessment on the MR details"""
        approval_policy = get_runtime_config(as_pydantic=True).approval_policy
        policy_str = approval_policy.to_markdown() if approval_policy else ""
        self.state.impact_assessment = extract_assessment(
            (
                await self.crews.impact_evaluator.kickoff_async(
                    inputs={
                        "mr_id": self.state.mr_id,
                        "approval_policy": policy_str,
                        "code_analysis_assessment": self.state.code_analysis_assessment,
                        "complexity_assessment": self.state.complexity_assessment,
                        "test_analysis": self.state.test_analysis_assessment,
                        "risk_assessment": self.state.risk_assessment,
                    }
                )
            ).raw
        )

    @listen(impact_evaluator)
    async def mr_decision(self):
        """Runs the MR decision crew on the impact assessment report"""
        response = await self.crews.publicator.kickoff_async(
            inputs={
                "mr_id": self.state.mr_id,
                "impact_assessment_report": self.state.impact_assessment,
            }
        )
        self.state.analysis_link = extract_url_from_text(response.tasks_output[0].raw)
        self.state.impact_evaluator = response.raw

        logger.info("\nFinal Response:")
        logger.info(self.state.impact_evaluator)


async def run_flow(
    mr_url: str, mr_iid: int = None, mr_title: str = "", project: str = None
) -> AnalysisResult:
    """
    Initiates the MergeBotFlow to process a merge request URL.

    Args:
        mr_url (str): The URL of the merge request to process.
        mr_iid (int): Optional merge request ID to process.
        mr_title (str): Optional merge request title.
        project (str): The GitLab project/repository path.

    Returns:
        AnalysisResult: Validated analysis result for dashboard/tracking.
    """
    mr_id = mr_iid or extract_merge_request_id(mr_url)
    if not mr_id:
        raise Exception(f"Failed to extract MR ID from URL: {mr_url}")

    inital_state = {"mr_url": mr_url, "mr_id": mr_id, "mr_title": mr_title, "project": project}

    mergebot = MergeBotFlow(**inital_state)
    flow_id = mergebot.flow_id

    logger.info(f"Initiated MergeBotFlow with Flow ID: {flow_id}")

    await mergebot.kickoff_async()

    try:
        analysis_result = AnalysisResult(
            title=mergebot.state.mr_title,
            iid=mergebot.state.mr_id,
            impact_score=mergebot.state.impact_assessment.get("score"),
            recommendation=mergebot.state.impact_assessment.get("recommendation"),
            last_reviewed=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
            analysis_link=mergebot.state.analysis_link,
        )
    except ValidationError as e:
        logger.error(f"AnalysisResult validation failed: {e}")
        raise

    return analysis_result
