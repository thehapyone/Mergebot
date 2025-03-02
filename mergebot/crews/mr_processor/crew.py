from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
import yaml

@CrewBase
class MRProcessor():
    """MRProcessor crew"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def mr_input_handler(self) -> Agent:
        return Agent(
            config=self.agents_config['mr_input_handler'],
            verbose=True
        )

    @agent
    def mr_retriever(self) -> Agent:
        return Agent(
            config=self.agents_config['mr_retriever'],
            verbose=True
        )

    @agent
    def pipeline_retriever(self) -> Agent:
        return Agent(
            config=self.agents_config['pipeline_retriever'],
            verbose=True
        )

    @task
    def mr_input_task(self) -> Task:
        return Task(
            config=self.tasks_config['mr_input_task'],
        )

    @task
    def mr_retriever_task(self) -> Task:
        return Task(
            config=self.tasks_config['mr_retriever_task'],
        )

    @crew
    def crew(self) -> Crew:
        """Creates the MRProcessor crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
