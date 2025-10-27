import re

from crewai import LLM, Crew, Process
from crewai.project import crew

from mergebot.validator.config import Config


def extract_class_name(class_string: str) -> str:
    # Regular expression to find anything inside parentheses
    match = re.search(r"\((.*?)\)", class_string)
    return match.group(1) if match else class_string


class BotBaseCrew:
    """A base configuration for common crew definition"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"
    verbose: bool = False

    def __init__(self, config: Config):
        self.config = config
        # Get the LLM model for this crew
        crew_name = extract_class_name(self.__class__.__name__)
        llm_model = self.config.get_llm_model_for_crew(crew_name)
        self.llm = LLM(model=llm_model, drop_params=True, additional_drop_params=["stop"])

    @crew
    def crew(self) -> Crew:
        """Creates the crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=self.verbose,
            output_log_file=True,
        )
