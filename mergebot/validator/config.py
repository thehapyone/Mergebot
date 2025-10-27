# mergebot/validator/config.py

import os
import sys
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mergebot.validator.logging_config import logger

load_dotenv()


class StrictBaseModel(BaseModel):
    """Base model enforcing strict schema (no extra keys)."""

    model_config = ConfigDict(extra="forbid")


class LLMConfig(StrictBaseModel):
    model: str = Field(..., description="LLM model to be used")


class WebhookProjectConfig(StrictBaseModel):
    """
    Webhook-specific settings for a single project entry.
    """

    secret: str | None = Field(
        default=None,
        description="Shared secret used to validate incoming webhook requests for this project.",
    )
    enabled_events: list[str] | None = Field(
        default=None,
        description="Optional allow-list of event names Mergebot should process for this project.",
    )


class GitLabConfig(StrictBaseModel):
    url: str = Field(default=os.getenv("GITLAB_URL"), description="GitLab API endpoint URL")
    private_token: str | None = Field(
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


# GitHub configuration mirrors GitLab but for GitHub REST API
class GitHubConfig(StrictBaseModel):
    """
    GitHub authentication supports **either** a Personal Access Token
    or a GitHub App (App ID + private key, with optional installation_id).

    Only one path is required; PAT remains for backward-compatibility.
    """

    api_url: str = Field(default="https://api.github.com", description="GitHub API endpoint URL")

    # --- Personal-access-token path (legacy) ---
    private_token: str | None = Field(
        default=os.getenv("GITHUB_TOKEN"),
        description="Personal access token for GitHub API authentication (legacy)",
    )

    # --- GitHub-App path ---
    app_id: str | None = Field(
        default=os.getenv("GITHUB_APP_ID"), description="Numeric GitHub App ID"
    )
    installation_id: str | None = Field(
        default=os.getenv("GITHUB_APP_INSTALLATION_ID"),
        description="Installation ID for the GitHub App (optional)",
    )
    private_key: str | None = Field(
        default=os.getenv("GITHUB_APP_PRIVATE_KEY"),
        description="The raw PEM string for the GitHub App private key",
    )

    base_branch: str = Field(default="main", description="Base branch for the project")

    @model_validator(mode="after")
    def validate_auth_choice(self):
        has_pat = bool(self.private_token)
        has_app = bool(self.app_id) and bool(self.private_key)

        if not (has_pat or has_app):
            raise ValueError(
                "GitHub authentication required: provide either\n"
                "  • personal access token (private_token / GITHUB_TOKEN)  **or**\n"
                "  • app_id + private_key (or GITHUB_APP_ID + GITHUB_APP_PRIVATE_KEY)\n"
                "installation_id is optional; Mergebot will auto-discover if omitted."
            )
        return self


class CrewConfig(StrictBaseModel):
    llm: LLMConfig | None = None


class ApprovalPolicy(StrictBaseModel):
    """
    Represents the policy for approving changes based on weighted scores of various agents.

    Attributes:
        threshold (float): The threshold score below which changes are auto-approved. Default is 3.0.
        weights (Dict[str, float]): A dictionary of agent/crew names with their corresponding weight values.

    Methods:
        validate_weights_agents:
            Validates that all agents specified in `weights` are among the predefined valid agents.
            Ensures each valid agent is defined in `weights` with an associated weight value.

        to_markdown:
            Returns a formatted string in Markdown describing the approval policy, including weights and threshold.
    """

    threshold: float = 3.0
    weights: dict[str, float] = {}

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
        if not self.weights:
            return ""
        weights_str = "\n".join(f"  - {k}: {v:.2f}" for k, v in self.weights.items())
        return (
            f"**Approval Policy**:\n"
            f"- Threshold: {self.threshold}\n"
            f"- Weights:\n{weights_str}\n"
            "Auto-approve if weighted impact score <= threshold.\n"
            "Do not adjust, round, or reinterpret the score except for standard rounding."
        )


class AnalysisConfig(StrictBaseModel):
    max_mrs: int | None = Field(
        default=None,
        description="Maximum number of merge requests to analyze at a time. 0 or None means unlimited.",
    )
    draft_mrs: bool | None = Field(
        default=False,
        description="If true, analyze Draft/WIP merge requests. If false (default), skip Draft/WIP MRs.",
    )


class TelemetryConfig(StrictBaseModel):
    enabled: bool = Field(default=False, description="Enable full telemetry via OpenTelemetry")


class MergeRules(StrictBaseModel):
    """
    Gate conditions evaluated before performing an auto-merge.
    All set to True by default (strict/safe).
    """

    ci_passed: bool = Field(default=True, description="Require CI to be green/success")
    ci_strict: bool = Field(
        default=False,
        description="If true, treat unknown/no CI as failure. If false (default), allow projects with no CI configured.",
    )
    no_changes_requested: bool = Field(
        default=True, description="Block merge if any review has 'changes requested'"
    )
    mergeable: bool = Field(
        default=True, description="Require platform to report mergeable (no conflicts)"
    )
    approval_state: bool = Field(
        default=True, description="Require platform approval state to be satisfied"
    )
    branch_prefixes: list[str] | None = Field(
        default=None,
        description="Allow-list for source branches. If set, only auto-merge when source branch starts with any of these prefixes.",
    )


class MergeConfig(StrictBaseModel):
    """
    Auto-merge configuration.
    - enabled: Explicit opt-in to allow Mergebot to merge.
    - threshold: If None, falls back to approval_policy.threshold for merge gating.
    - strategy: Preferred merge strategy; platform support may vary.
    - rules: Safety guardrails grouped under a single block.
    """

    enabled: bool = Field(default=False, description="Enable auto-merge capability")
    threshold: float | None = Field(
        default=None,
        description="Merge threshold; if None, fallback to approval_policy.threshold",
    )
    strategy: Literal["repo_default", "merge", "squash", "rebase"] = Field(
        default="repo_default",
        description="Merge strategy to apply (platform-respected)",
    )
    rules: MergeRules = Field(
        default_factory=MergeRules, description="Pre-merge guardrail conditions"
    )


class ProjectConfigOverrides(StrictBaseModel):
    """
    Represents per-project configuration overrides used in multi-project deployments.
    Any unset field falls back to the global configuration.
    """

    crews: dict[str, "CrewConfig"] | None = Field(
        default=None, description="Optional crew overrides scoped to this project."
    )
    approval_policy: ApprovalPolicy | None = Field(
        default=None, description="Optional approval policy overrides for this project."
    )
    analysis: AnalysisConfig | None = Field(
        default=None, description="Optional analysis overrides for this project."
    )
    merge: MergeConfig | None = Field(
        default=None,
        description="Optional merge configuration overrides for this project.",
    )


class ProjectDefinition(StrictBaseModel):
    """Defines a single repository serviced by Mergebot."""

    path: str = Field(
        ...,
        description="Repository path (e.g., 'group/project' for GitLab or 'owner/repo' for GitHub).",
    )
    webhook: WebhookProjectConfig | None = Field(
        default=None, description="Webhook-related settings for this project."
    )
    overrides: ProjectConfigOverrides | None = Field(
        default=None,
        description="Optional configuration overrides applied on top of global defaults for this project.",
    )


class RepositoryConfig(StrictBaseModel):
    type: str = Field(..., description="Repository type, either 'gitlab' or 'github'")
    gitlab: GitLabConfig | None = None
    github: GitHubConfig | None = None
    projects: list[ProjectDefinition] = Field(
        default_factory=list,
        description="List of repositories serviced by this Mergebot instance.",
    )

    @model_validator(mode="before")
    @classmethod
    def validate_repository_settings(cls, values: dict) -> dict:
        repo_type = values.get("type")
        gitlab_config = values.get("gitlab")
        github_config = values.get("github")

        if repo_type == "gitlab" and not gitlab_config:
            raise ValueError(
                "GitLab configuration must be provided when repository type is 'gitlab'"
            )
        if repo_type == "github" and not github_config:
            raise ValueError(
                "GitHub configuration must be provided when repository type is 'github'"
            )
        projects = values.get("projects") or []
        if not isinstance(projects, list):
            raise ValueError("repository.projects must be a list of project definitions")
        return values


class Config(StrictBaseModel):
    llm: LLMConfig = Field(..., description="Global configurations")
    repository: RepositoryConfig = Field(..., description="Repository configuration")
    crews: dict[str, CrewConfig] | None = Field(None, description="Crew configurations")
    approval_policy: ApprovalPolicy | None = None
    analysis: AnalysisConfig | None = None
    telemetry: TelemetryConfig | None = None
    merge: MergeConfig | None = None

    def get_llm_model_for_crew(self, crew_name: str) -> str:
        """Get LLM model for the crew"""
        crew_config = self.crews.get(crew_name) if self.crews else None
        if crew_config and crew_config.llm and crew_config.llm.model:
            return crew_config.llm.model
        else:
            return self.llm.model


def load_config_dict(config_path: str | None = None) -> dict:
    """Load the base configuration dictionary from disk."""

    resolved_path = config_path or os.getenv("CONFIG_PATH", "config.yaml")
    try:
        with open(resolved_path) as f:
            config_dict = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"Configuration file not found at {resolved_path}.")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML: {e}")
        sys.exit(1)

    if config_dict is None:
        logger.error("Configuration file is empty.")
        sys.exit(1)

    if not isinstance(config_dict, dict):
        logger.error("Configuration root must be a mapping/dictionary.")
        sys.exit(1)

    return config_dict


def load_config(config_path: str | None = None) -> Config:
    """Load and validate the base configuration from disk."""

    return Config(**load_config_dict(config_path))
