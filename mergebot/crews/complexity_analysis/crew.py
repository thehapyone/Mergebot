from crewai import Agent, Task
from crewai.project import CrewBase, agent, task

from mergebot.crews.commons import BotBaseCrew


@CrewBase
class ComplexityAnalysis(BotBaseCrew):
    """ComplexityAnalysis crew"""

    @agent
    def complexity_analyzer(self) -> Agent:
        return Agent(
            config=self.agents_config["complexity_analyzer"],
            llm=self.llm_model,
            verbose=True,
        )

    @task
    def complexity_analyze_task(self) -> Task:
        return Task(
            config=self.tasks_config["complexity_analyze_task"],
        )
