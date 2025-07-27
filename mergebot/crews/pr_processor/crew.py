from crewai import Agent, Task
from crewai.project import CrewBase, agent, task

from mergebot.crews.commons import BotBaseCrew
from mergebot.tools import PullRequestTool


@CrewBase
class PRProcessor(BotBaseCrew):
    """PR Processor crew"""

    verbose = False

    @agent
    def pr_retriever(self) -> Agent:
        return Agent(
            config=self.agents_config["pr_retriever"],
            llm=self.llm_model,
            tools=[PullRequestTool()],
        )

    @task
    def pr_retriever_task(self) -> Task:
        return Task(config=self.tasks_config["pr_retriever_task"])
