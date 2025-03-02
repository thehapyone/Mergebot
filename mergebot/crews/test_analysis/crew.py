from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
import yaml

@CrewBase
class TestAnalysis():
    """TestAnalysis crew"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def test_coverage_analyzer(self) -> Agent:
        return Agent(
            config=self.agents_config['test_coverage_analyzer'],
            verbose=True
        )

    @task
    def test_analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config['test_analysis_task'],
        )

    @crew
    def crew(self) -> Crew:
        """Creates the TestAnalysis crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
