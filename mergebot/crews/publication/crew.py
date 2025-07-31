from crewai import Agent, Task
from crewai.project import CrewBase, agent, task

from mergebot.crews.commons import BotBaseCrew
from mergebot.tools import (
    ApprovePullOrMergeRequestTool,
    GitlabMergeCommentTool,
)
from crewai.project import crew

from crewai import LLM, Crew, Process


@CrewBase
class MergeFinalizationCrew(BotBaseCrew):
    """Crew to handle MR/PR assessment reporting and finalization tasks."""

    @agent
    def reporter(self) -> Agent:
        return Agent(
            config=self.agents_config["reporter"],
            llm=self.llm,
            tools=[GitlabMergeCommentTool()],
        )

    @agent
    def finalizer(self) -> Agent:
        return Agent(
            config=self.agents_config["finalizer"],
            llm=self.llm,
            tools=[GitlabMergeCommentTool(), ApprovePullOrMergeRequestTool()],
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

    @crew
    def crew(self) -> Crew:
        """Creates the crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            cache=False,
            process=Process.sequential,
            verbose=True,
            output_log_file="test.log",
        )
