from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, task, crew

from mergebot.crews.commons import BotBaseCrew
from mergebot.tools.gitlab import GitlabMergeCommentTool, GitlabMergeApprovalTool


@CrewBase
class Publication(BotBaseCrew):
    """Publication Crew to handle MR publication tasks."""

    @agent
    def publication_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["publication_agent"],
            llm=self.llm_model,
            tools=[GitlabMergeCommentTool()],
            verbose=True,
        )

    @agent
    def execution_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["execution_agent"],
            llm=self.llm_model,
            tools=[GitlabMergeApprovalTool(), GitlabMergeCommentTool()],
            verbose=True,
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

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            memory=True,
            planning=False,
            process=Process.sequential,
            verbose=True,
        )
