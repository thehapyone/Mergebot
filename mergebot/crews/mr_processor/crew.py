from crewai import Agent, Task
from crewai.project import CrewBase, agent, task

from mergebot.crews.commons import BotBaseCrew
from mergebot.tools.gitlab import GitlabMergeRequestTool


@CrewBase
class MRProcessor(BotBaseCrew):
    """MRProcessor crew"""

    @agent
    def mr_retriever(self) -> Agent:
        return Agent(
            config=self.agents_config["mr_retriever"],
            llm=self.llm_model,
            tools=[GitlabMergeRequestTool(result_as_answer=True)],
            verbose=False,
        )

    @task
    def mr_retriever_task(self) -> Task:
        return Task(config=self.tasks_config["mr_retriever_task"])
