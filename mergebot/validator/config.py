from functools import lru_cache
from pydantic import BaseModel, Field, ValidationError
from pydantic import model_validator
from typing import List, Optional
import yaml


class LLMConfig(BaseModel):
    model: str = Field(..., description="LLM model to be used")


class GitLabConfig(BaseModel):
    api_endpoint: str = Field(..., description="GitLab API endpoint URL")
    private_token: str = Field(
        ..., description="Private token for GitLab API authentication"
    )


class RepositoryConfig(BaseModel):
    type: str = Field(..., description="Repository type, either 'gitlab' or 'github'")
    gitlab: Optional[GitLabConfig] = None

    @model_validator(mode="before")
    @classmethod
    def validate_repository_settings(cls, values: dict) -> dict:
        repo_type = values.get("type")
        gitlab_config = values.get("gitlab")

        if repo_type == "gitlab":
            if not gitlab_config:
                raise ValueError(
                    "GitLab configuration must be provided when repository type is 'gitlab'"
                )
        else:
            raise ValueError("Repository type must be 'gitlab'.")
        return values


class ProjectConfig(BaseModel):
    id: str = Field(..., description="Identifier for the project")
    name: str = Field(..., description="Name of the project")


class CrewConfig(BaseModel):
    name: str = Field(..., description="Name of the crew")
    llm: Optional[LLMConfig] = None


class Config(BaseModel):
    llm: LLMConfig = Field(..., description="Global configurations")
    repository: RepositoryConfig = Field(..., description="Repository configuration")
    project: ProjectConfig = Field(..., description="Project configuration")
    crews: List[CrewConfig] = Field(..., description="List of crew configurations")

    def get_llm_model_for_crew(self, crew_name: str) -> str:
        """Get LLM model for the crew"""
        crew_config = self.crews.get(crew_name)
        if crew_config and crew_config.llm and crew_config.llm.model:
            return crew_config.llm.model
        else:
            return self.llm.model

# Function to load and validate the configuration
@lru_cache
def load_config() -> Config:
    config_path = ""
    with open(config_path, "r") as f:
        config_dict = yaml.safe_load(f)

    try:
        config = Config(**config_dict)
        return config
    except ValidationError as e:
        print("Configuration validation error:", e)
        raise
