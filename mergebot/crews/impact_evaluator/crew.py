from crewai import Agent, Task
from crewai.project import CrewBase, agent, task

from mergebot.crews.commons import BotBaseCrew


@CrewBase
class ImpactEvaluator(BotBaseCrew):
    """ImpactEvaluator crew"""

    @agent
    def impact_evaluator(self) -> Agent:
        return Agent(
            config=self.agents_config["impact_evaluator"],
            llm=self.llm,
        )

    @task
    def evaluator_task(self) -> Task:
        return Task(
            config=self.tasks_config["evaluator_task"],
        )
