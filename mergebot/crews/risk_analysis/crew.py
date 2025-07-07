from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from mergebot.crews.commons import BotBaseCrew


@CrewBase
class RiskAnalysis(BotBaseCrew):
    """RiskAnalysis crew"""

    @agent
    def risk_analysis(self) -> Agent:
        return Agent(
            config=self.agents_config["risk_analysis"], llm=self.llm_model, verbose=True
        )

    @task
    def risk_analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config["risk_analysis_task"],
        )

    @crew
    def crew(self) -> Crew:
        """Creates the RiskAnalysis crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
        )
