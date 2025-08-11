from crewai import Agent, Task
from crewai.project import CrewBase, agent, task

from mergebot.crews.commons import BotBaseCrew
from mergebot.tools import (
    ApprovePullOrMergeRequestTool,
    PostCommentTool,
)


@CrewBase
class MergeFinalizationCrew(BotBaseCrew):
    """Crew to handle MR/PR assessment reporting and finalization tasks."""

    @agent
    def reporter(self) -> Agent:
        return Agent(
            config=self.agents_config["reporter"],
            llm=self.llm,
            tools=[PostCommentTool()],
        )

    @agent
    def finalizer(self) -> Agent:
        return Agent(
            config=self.agents_config["finalizer"],
            llm=self.llm,
            tools=[PostCommentTool(), ApprovePullOrMergeRequestTool()],
            max_iter=3,
        )

    @task
    def reporting_task(self) -> Task:
        return Task(
            config=self.tasks_config["reporting_task"],
        )

    @task
    def finalization_task(self) -> Task:
        return Task(
            config=self.tasks_config["finalization_task"],
        )
