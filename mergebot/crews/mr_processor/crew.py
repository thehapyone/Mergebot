from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from mergebot.crews.commons import BotBaseCrew
from mergebot.tools.gitlab import GitlabMergeRequestTool


@CrewBase
class MRProcessor(BotBaseCrew):
    """MRProcessor crew"""

    @agent
    def mr_input_handler(self) -> Agent:
        return Agent(
            config=self.agents_config["mr_input_handler"],
            llm=self.llm_model,
            verbose=True,
        )

    @agent
    def mr_retriever(self) -> Agent:
        return Agent(
            config=self.agents_config["mr_retriever"],
            llm=self.llm_model,
            tools=[GitlabMergeRequestTool(result_as_answer=True)],
            verbose=False,
        )

    @task
    def mr_input_task(self) -> Task:
        return Task(
            config=self.tasks_config["mr_input_task"],
        )

    @task
    def mr_retriever_task(self) -> Task:
        return Task(config=self.tasks_config["mr_retriever_task"])
