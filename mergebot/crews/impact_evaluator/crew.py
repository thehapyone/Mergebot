from crewai import Agent, Task
from crewai.project import agent, task

from mergebot.crews.commons import BotBaseCrew

class ImpactEvaluator(BotBaseCrew):
    """ImpactEvaluator crew"""

    @agent
    def impact_evaluator(self) -> Agent:
        return Agent(config=self.agents_config["impact_evaluator"], llm=self.llm_model, verbose=True)

    @task
    def evaluator_task(self) -> Task:
        return Task(
            config=self.tasks_config["evaluator_task"],
        )
