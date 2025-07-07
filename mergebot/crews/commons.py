import re

from crewai import Crew, Process
from crewai.project import crew

from mergebot.validator.config import get_runtime_config


def extract_class_name(class_string: str) -> str:
    # Regular expression to find anything inside parentheses
    match = re.search(r"\((.*?)\)", class_string)
    return match.group(1) if match else class_string


class BotBaseCrew:
    """A base configuration for common crew definition"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    # Load the configuration once
    config = get_runtime_config(as_pydantic=True)

    def __init__(self):
        # Get the LLM model for this crew
        crew_name = extract_class_name(self.__class__.__name__)
        self.llm_model = self.config.get_llm_model_for_crew(crew_name)

    @crew
    def crew(self) -> Crew:
        """Creates the crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=False,
            output_log_file=True
        )
