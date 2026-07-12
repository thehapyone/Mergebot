from crewai import Agent, Task
from crewai.project import CrewBase, agent, task

from mergebot.crews.commons import BotBaseCrew
from mergebot.crews.schemas import ReviewerVerdict, make_findings_guardrail


@CrewBase
class ComplexityAnalysis(BotBaseCrew):
    """ComplexityAnalysis crew"""

    @agent
    def complexity_analyzer(self) -> Agent:
        return Agent(
            config=self.agents_config["complexity_analyzer"],
            llm=self.llm,
        )

    @task
    def complexity_analyze_task(self) -> Task:
        return Task(
            config=self.tasks_config["complexity_analyze_task"],
            output_pydantic=ReviewerVerdict,
            guardrails=[make_findings_guardrail(self.finding_file_checker)],
            guardrail_max_retries=3,
        )
