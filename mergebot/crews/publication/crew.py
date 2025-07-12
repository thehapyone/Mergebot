from crewai import Agent, Task
from crewai.project import CrewBase, agent, task

from mergebot.crews.commons import BotBaseCrew
from mergebot.tools.gitlab import GitlabMergeApprovalTool, GitlabMergeCommentTool


@CrewBase
class Publication(BotBaseCrew):
    """Publication Crew to handle MR publication tasks."""

    @agent
    def publicator(self) -> Agent:
        return Agent(
            config=self.agents_config["publicator"],
            llm=self.llm_model,
            tools=[GitlabMergeCommentTool()],
        )

    @agent
    def executor(self) -> Agent:
        return Agent(
            config=self.agents_config["executor"],
            llm=self.llm_model,
            tools=[GitlabMergeApprovalTool(), GitlabMergeCommentTool()],
        )

    @task
    def publication_task(self) -> Task:
        return Task(
            config=self.tasks_config["publication_task"],
        )

    @task
    def execution_task(self) -> Task:
        return Task(
            config=self.tasks_config["execution_task"],
        )
