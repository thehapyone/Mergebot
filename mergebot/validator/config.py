# mergebot/validator/config.py

import os
import sys
from functools import lru_cache
from typing import Dict, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from mergebot.logging_config import logger


class LLMConfig(BaseModel):
    model: str = Field(..., description="LLM model to be used")


class GitLabConfig(BaseModel):
    url: str = Field(..., description="GitLab API endpoint URL")
    private_token: Optional[str] = Field(
        default=os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN"),
        description="Private token for GitLab API authentication",
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


class ApprovalPolicy(BaseModel):
    """
    Represents the policy for approving changes based on weighted scores of various agents.

    Attributes:
        enabled (bool): Indicates whether the approval policy is active. Default is False.
        threshold (float): The threshold score below which changes are auto-approved. Default is 3.0.
        weights (Dict[str, float]): A dictionary of agent/crew names with their corresponding weight values.

    Methods:
        validate_weights_agents:
            Validates that all agents specified in `weights` are among the predefined valid agents.
            Ensures each valid agent is defined in `weights` with an associated weight value.

        to_markdown:
            Returns a formatted string in Markdown describing the approval policy, including weights and threshold.
    """

    enabled: bool = False
    threshold: float = 3.0
    weights: Dict[str, float] = {}

    @model_validator(mode="after")
    def validate_weights_agents(self):
        # Hardcoded valid agent/crew names
        valid_agents = {
            "CodeAnalysis",
            "ComplexityAnalysis",
            "TestAnalysis",
            "RiskAnalysis",
        }
        invalid = [k for k in self.weights if k not in valid_agents]
        if invalid:
            raise ValueError(
                f"Invalid agent(s) in approval_policy.weights: {', '.join(invalid)}. "
                f"Valid agents are: {', '.join(valid_agents)}"
            )
        if len(self.weights) != len(valid_agents):
            raise ValueError(
                f"approval_policy.weights must define exactly {len(valid_agents)} agents: {', '.join(valid_agents)}"
            )
        return self

    def to_markdown(self) -> str:
        if not self.enabled or not self.weights:
            return ""
        weights_str = "\n".join(f"  - {k}: {v:.2f}" for k, v in self.weights.items())
        return (
            f"**Approval Policy**:\n"
            f"- Threshold: {self.threshold}\n"
            f"- Weights:\n{weights_str}\n"
            "Auto-approve if weighted impact score <= threshold.\n"
            "Do not adjust, round, or reinterpret the score except for standard rounding."
        )


class Config(BaseModel):
    llm: LLMConfig = Field(..., description="Global configurations")
    repository: RepositoryConfig = Field(..., description="Repository configuration")
    crews: Optional[Dict[str, CrewConfig]] = Field(
        None, description="Crew configurations"
    )
    approval_policy: Optional[ApprovalPolicy] = None

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
