from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
import yaml


@CrewBase
class ImpactEvaluator:
    """ImpactEvaluator crew"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def impact_evaluator(self) -> Agent:
        return Agent(config=self.agents_config["impact_evaluator"], verbose=True)

    @task
    def evaluator_task(self) -> Task:
        return Task(
            config=self.tasks_config["evaluator_task"],
        )

    @crew
    def crew(self) -> Crew:
        """Creates the ImpactEvaluator crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
