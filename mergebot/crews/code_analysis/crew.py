from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

@CrewBase
class CodeAnalysis:
    """CodeAnalysis crew"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def code_analyzer(self) -> Agent:
        return Agent(config=self.agents_config["code_analyzer"], verbose=True)

    @task
    def analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config["analysis_task"],
        )

    @crew
    def crew(self) -> Crew:
        """Creates the CodeAnalysis crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
