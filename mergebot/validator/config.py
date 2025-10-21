# mergebot/validator/config.py

import os
import sys
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

from mergebot.validator.logging_config import logger

load_dotenv()


class LLMConfig(BaseModel):
    model: str = Field(..., description="LLM model to be used")


class GitLabConfig(BaseModel):
    url: str = Field(default=os.getenv("GITLAB_URL"), description="GitLab API endpoint URL")
    private_token: str | None = Field(
        default=os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN"),
        description="Private token for GitLab API authentication",
    )
    webhook_secret: str | None = Field(
        default=os.getenv("GITLAB_WEBHOOK_SECRET"),
        description="Shared secret used to validate GitLab webhooks (X-Gitlab-Token).",
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
class GitHubConfig(BaseModel):
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
    webhook_secret: str | None = Field(
        default=os.getenv("GITHUB_WEBHOOK_SECRET"),
        description="Shared secret used to validate GitHub webhook signatures.",
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


class RepositoryConfig(BaseModel):
    type: str = Field(..., description="Repository type, either 'gitlab' or 'github'")
    gitlab: GitLabConfig | None = None
    github: GitHubConfig | None = None

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
        return values


class CrewConfig(BaseModel):
    llm: LLMConfig | None = None


class ApprovalPolicy(BaseModel):
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


class AnalysisConfig(BaseModel):
    max_mrs: int | None = Field(
        default=None,
        description="Maximum number of merge requests to analyze at a time. 0 or None means unlimited.",
    )
    draft_mrs: bool | None = Field(
        default=False,
        description="If true, analyze Draft/WIP merge requests. If false (default), skip Draft/WIP MRs.",
    )


class TelemetryConfig(BaseModel):
    enabled: bool = Field(default=False, description="Enable full telemetry via OpenTelemetry")


class MergeRules(BaseModel):
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


class MergeConfig(BaseModel):
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


class Config(BaseModel):
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


class RuntimeConfig:
    """
    In-memory, mutable runtime config that overlays changes on top of the default config.
    Allows arbitrary updates, including new keys not present in the default schema.
    Changes are not persisted.
    """

    def __init__(self, base_config: dict):
        self._default = dict(base_config)  # shallow copy is enough if we never mutate
        self._runtime = {}

    def set(self, key_path: str, value):
        """Set a value at a dot-separated key path (supports nested and new keys)."""
        keys = key_path.split(".")
        d = self._runtime
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value

    def set_many(self, updates: dict):
        """
        Set multiple key paths at once, or recursively merge nested dicts.
        If a value is a dict and the key exists, perform a deep merge.
        """

        def deep_merge_dict(d, u):
            for k, v in u.items():
                if isinstance(v, dict) and isinstance(d.get(k), dict):
                    d[k] = deep_merge_dict(d.get(k, {}), v)
                else:
                    d[k] = v
            return d

        for key_path, value in updates.items():
            keys = key_path.split(".")
            d = self._runtime
            for k in keys[:-1]:
                d = d.setdefault(k, {})
            if isinstance(value, dict) and isinstance(d.get(keys[-1]), dict):
                d[keys[-1]] = deep_merge_dict(d.get(keys[-1], {}), value)
            else:
                d[keys[-1]] = value

    def get(self, key_path: str, default=None):
        """Get a value from the runtime config, falling back to default config."""
        keys = key_path.split(".")
        d = self._runtime
        for k in keys[:-1]:
            d = d.get(k, {})
        if keys[-1] in d:
            return d[keys[-1]]
        # Fallback to default
        d = self._default
        for k in keys[:-1]:
            d = d.get(k, {})
        return d.get(keys[-1], default)

    def delete(self, key_path: str):
        """Delete a key from the runtime config only."""
        keys = key_path.split(".")
        d = self._runtime
        for k in keys[:-1]:
            d = d.get(k, {})
        d.pop(keys[-1], None)

    def reset(self):
        """Reset all runtime changes."""
        self._runtime = {}

    def get_config(self):
        """Return a merged dict of default config overlaid with runtime changes."""

        def merge(a, b):
            # Simple recursive merge: b has priority
            if not isinstance(a, dict) or not isinstance(b, dict):
                return b
            result = dict(a)
            for k, v in b.items():
                if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                    result[k] = merge(result[k], v)
                else:
                    result[k] = v
            return result

        return merge(self._default, self._runtime)

    def as_dict(self):
        """Alias for get_config()."""
        return self.get_config()

    def validate(self):
        """Validate the current runtime config against the Pydantic schema. Raises ValidationError if invalid."""
        Config(**self.get_config())


def _load_config_dict_from_disk():
    """Internal helper to load the config dict from disk (config.yaml or CONFIG_PATH)."""
    config_path = os.getenv("CONFIG_PATH", "config.yaml")
    try:
        with open(config_path) as f:
            config_dict = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"Configuration file not found at {config_path}.")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML: {e}")
        sys.exit(1)
    return config_dict


# Initialize the runtime config singleton
runtime_config = RuntimeConfig(_load_config_dict_from_disk())


def get_runtime_config(as_pydantic: bool = False):
    """
    Returns the current runtime config as a dict (merged view).
    If as_pydantic is True, returns a Config object (validates against schema).
    """
    merged = runtime_config.get_config()
    if as_pydantic:
        return Config(**merged)
    return merged
