from crewai import Agent, Task
from crewai.project import CrewBase, agent, task

from mergebot.crews.commons import BotBaseCrew
from mergebot.crews.schemas import ReviewerVerdict, make_findings_guardrail


@CrewBase
class TestAnalysis(BotBaseCrew):
    """TestAnalysis crew"""

    @agent
    def test_coverage_analyzer(self) -> Agent:
        return Agent(
            config=self.agents_config["test_coverage_analyzer"],
            llm=self.llm,
        )

    @task
    def test_analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config["test_analysis_task"],
            output_pydantic=ReviewerVerdict,
            guardrails=[make_findings_guardrail(self.finding_file_checker)],
            guardrail_max_retries=3,
        )
