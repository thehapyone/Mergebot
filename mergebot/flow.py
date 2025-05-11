from datetime import datetime
from crewai.flow.flow import Flow, listen, start, and_
from crewai import Crew
from pydantic import BaseModel
import re
from mergebot.logging_config import logger
from mergebot.crews import (
    CodeAnalysis,
    ComplexityAnalysis,
    RiskAnalysis,
    TestAnalysis,
    ImpactEvaluator,
    MRProcessor,
    Publication,
)

# Sample Input
bot_input = "MR https://gitlab.its.getingecloud.net/dts/lestrade/aide-recorder/-/merge_requests/71"


def extract_mr_title(mr_details: str) -> str:
    """
    Extracts the MR title from the mr_details string.

    Args:
        mr_details (str): A string containing details of the merge request.

    Returns:
        str: Extracted title from the MR details. If no title is found, returns an empty string.
    """
    try:
        # Define a regex pattern to find the "Title" line in the MR details
        title_pattern = r"^Title:\s*(.+)$"

        # Search the mr_details string for the "Title" information
        match = re.search(title_pattern, mr_details, re.MULTILINE)

        # Return the extracted title or an empty string if not found
        return match.group(1).strip() if match else ""
    except Exception as e:
        logger.error(f"Error extracting MR title: {e}")
        return mr_details


def extract_impact_score(impact_assessment: str) -> str:
    """
    Extracts the impact score from the impact assessment.

    Args:
        impact_assessment (str): A string containing the impact assessment details.

    Returns:
        str: Extracted impact score from the assessment. If no score is found, returns an empty string.
    """
    # Define a regex pattern to find the "Overall Impact Score" line in the assessment
    score_pattern = r"^Overall Impact Score:\s*(.+)$"

    # Search the impact_assessment string for the "Overall Impact Score"
    match = re.search(score_pattern, impact_assessment, re.MULTILINE)

    # Return the extracted score or an empty string if not found
    return match.group(1).strip() if match else ""


def extract_merge_request_id(output_string):
    pattern = r"https://.+/merge_requests/(\d+)"

    # Search the output string for the pattern
    match = re.search(pattern, output_string)

    # Extract and return the Merge Request ID if found
    if match:
        return int(match.group(1))
    else:
        return None


class MergeBotCrews(BaseModel):
    """Defines the bot crews"""

    code_analysis: Crew = CodeAnalysis().crew()
    complexity_assessment: Crew = ComplexityAnalysis().crew()
    test_analysis: Crew = TestAnalysis().crew()
    risk_analysis: Crew = RiskAnalysis().crew()
    impact_evaluator: Crew = ImpactEvaluator().crew()
    mr_processor: Crew = MRProcessor().crew()
    publicator: Crew = Publication().crew()


class MergeBotState(BaseModel):
    """Defines the bot data state"""

    mr_url: str = ""
    mr_details: str = ""
    mr_id: int = None
    code_analysis_assessment: str = ""
    complexity_assessment: str = ""
    test_analysis_assessment: str = ""
    risk_assessment: str = ""
    impact_assessment: str = ""
    impact_evaluator: str = ""


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
        self.state.impact_assessment = (
            await self.crews.impact_evaluator.kickoff_async(
                inputs={
                    "mr_id": self.state.mr_id,
                    "code_analysis_assessment": self.state.code_analysis_assessment,
                    "complexity_assessment": self.state.complexity_assessment,
                    "test_analysis": self.state.test_analysis_assessment,
                    "risk_assessment": self.state.risk_assessment,
                }
            )
        ).raw
        logger.info("\nFinal Impact Assessment Report:")
        logger.info(self.state.impact_assessment)

    @listen(impact_evaluator)
    async def mr_decision(self):
        """Runs the MR decision crew on the impact assessment report"""
        self.state.impact_evaluator = (
            await self.crews.publicator.kickoff_async(
                inputs={
                    "mr_id": self.state.mr_id,
                    "impact_assessment_report": self.state.impact_assessment,
                }
            )
        ).raw

        logger.info("\nFinal Response:")
        logger.info(self.state.impact_evaluator)


import asyncio


async def run_flow(mr_url: str, dashboard_manager=None, dashboard_context: dict = None):
    """
    Initiates the MergeBotFlow to process a merge request URL.

    Optionally updates the dashboard after analysis if dashboard_manager is provided.

    Args:
        mr_url (str): The URL of the merge request to process.
        dashboard_manager: Optional dashboard manager instance for updating dashboard.
        dashboard_context: Optional dict with additional dashboard context (e.g., rerun_requests, action_log, analytics).

    Returns:
        None
    """

    mr_id = extract_merge_request_id(mr_url)
    inital_state = {"mr_url": mr_url, "mr_id": mr_id}

    mergebot = MergeBotFlow(**inital_state)
    flow_id = mergebot.flow_id
    logger.info(f"Initiated MergeBotFlow with Flow ID: {flow_id}")

    await mergebot.kickoff_async()

    # After analysis, update dashboard if manager is provided
    if dashboard_manager is not None:
        # Prepare MR data for dashboard (single MR)
        mr_data = [
            {
                "iid": mr_id,
                "title": extract_mr_title(getattr(mergebot.state, "mr_details", ""))[
                    :80
                ],
                "impact_score": extract_impact_score(getattr(mergebot.state, "impact_assessment", "")),
                "last_reviewed": datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
                "analysis_link": "#",  # TODO: Link to detailed report if available
                "web_url": mr_url,
            }
        ]
        # Use context or defaults
        rerun_requests = (
            dashboard_context.get("rerun_requests", []) if dashboard_context else []
        )
        action_log = (
            dashboard_context.get("action_log", []) if dashboard_context else []
        )
        analytics = dashboard_context.get("analytics", {}) if dashboard_context else {}
        dashboard_manager.update_dashboard(
            mr_data=mr_data,
            rerun_requests=rerun_requests,
            action_log=action_log,
            analytics=analytics,
        )
