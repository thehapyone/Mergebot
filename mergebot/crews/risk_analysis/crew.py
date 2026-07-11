from crewai import Agent, Task
from crewai.project import CrewBase, agent, task

from mergebot.crews.commons import BotBaseCrew
from mergebot.crews.schemas import ReviewerVerdict, make_findings_guardrail


@CrewBase
class RiskAnalysis(BotBaseCrew):
    """RiskAnalysis crew"""

    @agent
    def risk_analysis(self) -> Agent:
        return Agent(config=self.agents_config["risk_analysis"], llm=self.llm)

    @task
    def risk_analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config["risk_analysis_task"],
            output_pydantic=ReviewerVerdict,
            guardrails=[make_findings_guardrail(self.finding_file_checker)],
            guardrail_max_retries=3,
        )
