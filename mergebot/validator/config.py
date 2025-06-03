# mergebot/validator/config.py

from functools import lru_cache
import os
import sys
from pydantic import BaseModel, Field, ValidationError
from pydantic import model_validator, field_validator
from typing import Dict, Optional
import yaml
from mergebot.logging_config import logger

class LLMConfig(BaseModel):
    model: str = Field(..., description="LLM model to be used")


class GitLabConfig(BaseModel):
    url: str = Field(..., description="GitLab API endpoint URL")
    private_token: Optional[str] = Field(
        default=os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN"),
        description="Private token for GitLab API authentication",
    )
    project: str = Field(
        ..., description="GitLab project path (e.g., 'username/project_name')"
    )
    base_branch: str = Field(default="main", description="Base branch for the project")

    @field_validator("private_token")
    @classmethod
    def validate_private_token(cls, v: str):
        if not v:
            raise ValueError(
                "Missing GitLab private token. Set the GITLAB_PERSONAL_ACCESS_TOKEN environment variable "
                "or provide the token in the 'private_token' config field."
            )
        return v


class RepositoryConfig(BaseModel):
    type: str = Field(..., description="Repository type, either 'gitlab' or 'github'")
    gitlab: Optional[GitLabConfig] = None

    @model_validator(mode="before")
    @classmethod
    def validate_repository_settings(cls, values: dict) -> dict:
        repo_type = values.get("type")
        gitlab_config = values.get("gitlab")

        if repo_type == "gitlab" and not gitlab_config:
            raise ValueError(
                "GitLab configuration must be provided when repository type is 'gitlab'"
            )
        return values


class CrewConfig(BaseModel):
    llm: Optional[LLMConfig] = None


class Config(BaseModel):
    llm: LLMConfig = Field(..., description="Global configurations")
    repository: RepositoryConfig = Field(..., description="Repository configuration")
    crews: Optional[Dict[str, CrewConfig]] = Field(
        None, description="Crew configurations"
    )

    def get_llm_model_for_crew(self, crew_name: str) -> str:
        """Get LLM model for the crew"""
        crew_config = self.crews.get(crew_name) if self.crews else None
        if crew_config and crew_config.llm and crew_config.llm.model:
            return crew_config.llm.model
        else:
            return self.llm.model


@lru_cache
def load_config() -> Config:
    config_path = os.getenv("CONFIG_PATH", "config.yaml")
    try:
        with open(config_path, "r") as f:
            config_dict = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"Configuration file not found at {config_path}.")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML: {e}")
        sys.exit(1)

    try:
        config = Config(**config_dict)
        return config
    except ValidationError as e:
        logger.error(f"Configuration validation error: {e}")
        sys.exit(1)
