from crewai.flow.flow import Flow, listen, start, and_
from crewai import Crew
from pydantic import BaseModel
import re
import logging
from mergebot.crews import (
    CodeAnalysis,
    ComplexityAnalysis,
    RiskAnalysis,
    TestAnalysis,
    ImpactEvaluator,
    MRProcessor,
    Publication,
)


logging.basicConfig(level=logging.INFO)

# Sample Input
bot_input = "MR https://gitlab.its.getingecloud.net/dts/lestrade/aide-recorder/-/merge_requests/71"


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

    mr_details: str = ""
    mr_id: int = None
    code_analysis_assessment: str = ""
    complexity_assessment: str = ""
    test_analysis_assessment: str = ""
    risk_assessment: str = ""
    impact_assessment: str = ""


class MergeBotFlow(Flow[MergeBotState]):
    crews = MergeBotCrews()

    @start()
    def begin(self):
        logging.info("Commencing and starting the MergeBot")

    @listen(begin)
    def mr_retriever(self):
        """Runs a Crew to extract Merge Request Details"""
        mr_details = self.crews.mr_processor.kickoff(inputs={"input": bot_input}).raw
        self.state.mr_details = mr_details
        self.state.mr_id = extract_merge_request_id(mr_details)

    @listen(mr_retriever)
    def code_analysis_assessment(self):
        """Runs the Code Analysis Assessment on the MR details"""
        self.state.code_analysis_assessment = self.crews.code_analysis.kickoff(
            inputs={"mr_details": self.state.mr_details}
        ).raw

    @listen(mr_retriever)
    def complexity_assessment(self):
        """Runs the Complexity Assessment on the MR details"""
        self.state.complexity_assessment = self.crews.complexity_assessment.kickoff(
            inputs={"mr_details": self.state.mr_details}
        ).raw

    @listen(mr_retriever)
    def test_analysis_assessment(self):
        """Runs the Test Analysis Assessment on the MR details"""
        self.state.test_analysis_assessment = self.crews.test_analysis.kickoff(
            inputs={"mr_details": self.state.mr_details}
        ).raw

    @listen(mr_retriever)
    def risk_assessment(self):
        """Runs the Risk Analysis Assessment on the MR details"""
        self.state.risk_assessment = self.crews.risk_analysis.kickoff(
            inputs={"mr_details": self.state.mr_details}
        ).raw

    @listen(
        and_(
            code_analysis_assessment,
            complexity_assessment,
            test_analysis_assessment,
            risk_assessment,
        )
    )
    def impact_evaluator(self):
        """Runs the Impact Evaluator Analysis Assessment on the MR details"""
        self.state.impact_assessment = self.crews.impact_evaluator.kickoff(
            inputs={
                "mr_id": self.state.mr_id,
                "code_analysis_assessment": self.state.code_analysis_assessment,
                "complexity_assessment": self.state.complexity_assessment,
                "test_analysis": self.state.test_analysis_assessment,
                "risk_assessment": self.state.risk_assessment,
            }
        ).raw
        logging.info("\nFinal Impact Assessment Report:")
        logging.info(self.state.impact_assessment)

    @listen(impact_evaluator)
    def mr_decision(self):
        """Runs the MR decision crew on the impact assessment report"""
        result = self.crews.publicator.kickoff(
            inputs={
                "mr_id": self.state.mr_id,
                "impact_assessment_report": self.state.impact_assessment,
            }
        ).raw

        logging.info("\nFinal Response:")
        logging.info(result)

    @listen(mr_decision)
    def finish(self):
        logging.info("MergeBot Processing Completed")


mergebot = MergeBotFlow()

if __name__ == "__main__":
    mergebot.kickoff()
    mergebot.plot("mergebot_flow")
