from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
import yaml

@CrewBase
class ComplexityAnalysis():
    """ComplexityAnalysis crew"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def complexity_analyzer(self) -> Agent:
        return Agent(
            config=self.agents_config['complexity_analyzer'],
            verbose=True
        )

    @task
    def complexity_analyze_task(self) -> Task:
        return Task(
            config=self.tasks_config['complexity_analyze_task'],
        )

    @crew
    def crew(self) -> Crew:
        """Creates the ComplexityAnalysis crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
