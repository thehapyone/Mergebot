from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task


@CrewBase
class RiskAnalysis:
    """RiskAnalysis crew"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def risk_analysis(self) -> Agent:
        return Agent(config=self.agents_config["risk_analysis"], verbose=True)

    @task
    def risk_analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config["risk_analysis_task"],
        )

    @crew
    def crew(self) -> Crew:
        """Creates the RiskAnalysis crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
