"""Project registry and context helpers for multi-project configurations.

This module provides:
- ProjectContext: a resolved, runtime-ready view of a single project's config.
- ProjectRegistry: utilities to list, check, and resolve projects from the repo config.
- _merge_dicts: internal helper for deep-merging project overrides into the base config.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from mergebot.validator.config import (
    Config,
    ProjectConfigOverrides,
    ProjectDefinition,
    load_config,
)


def _merge_dicts(base: dict[str, Any], overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    """Recursively merge ``overrides`` into ``base`` returning a new dictionary."""

    result = dict(base)
    if not overrides:
        return result

    for key, value in overrides.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


@dataclass(slots=True)
class ProjectContext:
    """
    Represents the fully-resolved configuration for a single project.

    A ProjectContext contains the merged base configuration with any project-specific overrides
    applied. It also exposes convenience properties for platform type, webhook secret, and
    identifiers, and can produce isolated ProjectRuntime instances for execution.
    """

    project_path: str
    config: Config
    definition: ProjectDefinition
    _config_dict: dict[str, Any] | None = None

    def __post_init__(self):
        self._config_dict = self.config.model_dump(mode="python", exclude_none=True)
        self._config_dict.get("repository", {}).pop("projects", None)

    @property
    def platform_type(self) -> str:
        """Return the repository platform type for this project (e.g., 'github' or 'gitlab')."""
        return self.config.repository.type

    @property
    def webhook_secret(self) -> str | None:
        """Return the project's webhook secret if configured, otherwise None."""
        if self.definition.webhook and self.definition.webhook.secret:
            return self.definition.webhook.secret
        return None

    @property
    def overrides(self) -> ProjectConfigOverrides | dict:
        """Return the project specific configuration overrides."""
        if self.definition.overrides:
            return self.definition.overrides.model_dump(mode="python", exclude_none=True)
        return {}

    @property
    def project_id(self) -> str:
        """The project path."""
        return self.project_path

    @property
    def repository_identifier(self) -> str | None:
        """Alias for the project's path used as repository identifier."""
        return self.project_path

    def build_runtime(
        self,
        repo_config: Mapping[str, Any] | None = None,
    ) -> ProjectRuntime:
        """Merge repo-level config and overrides to produce a project runtime."""

        base = copy.deepcopy(self._config_dict or {})
        repo_data = repo_config if isinstance(repo_config, Mapping) else {}
        merged = _merge_dicts(base, repo_data)
        # Merge in any project-specific overrides
        merged = _merge_dicts(merged, self.overrides)
        config = Config(**merged)
        return ProjectRuntime(context=self, config=config)


@dataclass(slots=True)
class ProjectRuntime:
    """Container tying together a project context with its effective configuration."""

    context: ProjectContext
    config: Config

    @property
    def platform_type(self) -> str:
        return self.context.platform_type

    @property
    def project_path(self) -> str:
        return self.context.project_path

    @property
    def repository_identifier(self) -> str | None:
        return self.context.repository_identifier

    @property
    def webhook_secret(self) -> str | None:
        return self.context.webhook_secret


class ProjectRegistry:
    """Registry responsible for resolving multi-project configuration entries.

    The registry reads the current runtime configuration to discover projects, exposes convenience
    methods to list and check them, and resolves ProjectContext instances on demand with caching.
    """

    def __init__(self):
        """Initialize the registry from the current runtime configuration."""
        self._base_config = load_config()
        definitions = self._base_config.repository.projects or []
        self._definitions: dict[str, ProjectDefinition] = {p.path: p for p in definitions}
        if not self._definitions:
            raise RuntimeError(
                "No projects defined in configuration. Populate 'repository.projects' with at least one entry."
            )
        self._contexts: dict[str, ProjectContext] = {}

    def list_project_ids(self) -> Iterable[str]:
        """Return a list of project identifiers (paths) available in the repository configuration."""
        return list(self._definitions.keys())

    def has_project(self, project_id: str) -> bool:
        """Return True if the given project_id is present in the repository configuration."""
        return project_id in self._definitions

    def resolve(self, project_id: str) -> ProjectContext:
        """
        Resolve and cache a ProjectContext for the given project_id.

        This merges the base configuration with any project-specific overrides, constructs a
        pydantic Config, and returns a runtime-ready ProjectContext.
        """
        if project_id in self._contexts:
            return self._contexts[project_id]

        definition = self._definitions.get(project_id)
        if definition is None:
            raise KeyError(f"Project '{project_id}' is not registered in configuration")

        base_dump = self._base_config.model_dump(mode="python", exclude_none=True)
        ## Remove projects from config
        base_dump.get("repository", {}).pop("projects", None)

        ## Convert project overrides to dict if available
        overrides_dump = (
            definition.overrides.model_dump(mode="python", exclude_none=True)
            if definition.overrides
            else {}
        )
        merged_dict = _merge_dicts(base_dump, overrides_dump)

        merged_config = Config(**merged_dict)
        context = ProjectContext(
            project_path=project_id,
            config=merged_config,
            definition=definition,
        )
        self._contexts[project_id] = context
        return context

    def default_context(self) -> ProjectContext:
        """Return the first available project context as a reasonable default."""
        if not self._definitions:
            raise RuntimeError("No projects defined in repository configuration")
        first_id = next(iter(self._definitions))
        return self.resolve(first_id)
