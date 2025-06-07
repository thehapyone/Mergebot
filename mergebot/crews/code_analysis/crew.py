from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from mergebot.crews.commons import BotBaseCrew


@CrewBase
class CodeAnalysis(BotBaseCrew):
    """CodeAnalysis crew"""

    @agent
    def code_analyzer(self) -> Agent:
        return Agent(
            config=self.agents_config["code_analyzer"], llm=self.llm_model, verbose=True
        )

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
            memory=False,
            cache=False,
            planning=False,
            process=Process.sequential,
            verbose=True,
        )
