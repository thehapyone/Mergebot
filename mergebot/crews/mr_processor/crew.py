from crewai import Agent, Crew, Process, Task
from crewai.project import agent, crew, task

from mergebot.crews.commons import BotBaseCrew

class MRProcessor(BotBaseCrew):
    """MRProcessor crew"""

    @agent
    def mr_input_handler(self) -> Agent:
        return Agent(
            config=self.agents_config['mr_input_handler'],
            llm=self.llm_model,
            verbose=True
        )

    @agent
    def mr_retriever(self) -> Agent:
        return Agent(
            config=self.agents_config['mr_retriever'],
            llm=self.llm_model,
            verbose=True
        )

    @agent
    def pipeline_retriever(self) -> Agent:
        return Agent(
            config=self.agents_config['pipeline_retriever'],
            llm=self.llm_model,
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
