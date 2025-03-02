from crewai import Crew, Process
from crewai.project import CrewBase, crew

from mergebot.validator.config import load_config


@CrewBase
class BotBaseCrew:
    """A base configuration for common crew definition"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    # Load the configuration once
    config = load_config()

    # Get the LLM model for this crew
    llm_model = config.get_llm_model_for_crew(__name__)

    @crew
    def crew(self) -> Crew:
        """Creates the crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
