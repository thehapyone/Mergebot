from collections.abc import Mapping
from typing import Any

from mergebot.project_registry import ProjectContext, ProjectRuntime
from mergebot.tools.github.onboarding import GitHubOnboardingManager
from mergebot.tools.gitlab.onboarding import GitlabOnboardingManager
from mergebot.tools.onboarding_base import InvalidMergebotYAMLError
from mergebot.validator.logging_config import logger


class EnsureRepoConfigError(RuntimeError):
    """Raised when repository configuration cannot be ensured for a project."""


def ensure_repo_config(
    context: ProjectContext, overrides: Mapping[str, Any] | None = None
) -> ProjectRuntime:
    """Resolve the effective configuration for a project and return a ProjectRuntime.

    The function validates repository-level configuration by fetching ``.mergebot.yml``
    (creating an onboarding PR when missing) and merges it with the server-level
    project definition and any explicit overrides. A fully validated ``ProjectRuntime``
    is returned for downstream consumers.
    """
    logger.info(f"Finding Mergebot configuration for project: {context.project_path}")
    platform_type = context.platform_type
    if platform_type == "gitlab":
        onboarding = GitlabOnboardingManager(
            config=context.config, project_path=context.project_path
        )
    elif platform_type == "github":
        onboarding = GitHubOnboardingManager(
            config=context.config, project_path=context.project_path
        )
    else:
        logger.error(f"Unsupported platform: {platform_type}")
        raise EnsureRepoConfigError(f"Unsupported platform: {platform_type}")

    runtime: ProjectRuntime | None = None

    try:
        logger.info("Checking for .mergebot.yml in repository: %s", context.project_path)
        repo_config = onboarding.get_mergebot_yml()
        if repo_config is not None:
            logger.info(".mergebot.yml found in repo. Merging and validating config...")
            if not isinstance(repo_config, Mapping):
                logger.error(".mergebot.yml must define a mapping at the root level.")
                raise EnsureRepoConfigError(".mergebot.yml must define a mapping at the root level")

            runtime = context.build_runtime(
                repo_config=repo_config,
            )
            logger.info("Successfully loaded and validated .mergebot.yml from repo.")
        else:
            logger.warning(
                ".mergebot.yml not found in repo. Checking for existing onboarding PR..."
            )
            existing_pr_url = onboarding.onboarding_pr_exists()
            if existing_pr_url:
                logger.info(f"Onboarding PR already exists: <{existing_pr_url}>")
                logger.error(
                    "Onboarding required. Please merge the existing PR to enable Mergebot."
                )
                raise EnsureRepoConfigError("Onboarding PR already exists for this project")
            else:
                logger.info("No existing onboarding PR found. Creating onboarding PR...")
                base_branch = onboarding.project.default_branch
                default_mergebot_yml = (
                    "# Default Mergebot configuration\n"
                    "# See docs for full configuration: https://github.com/thehapyone/Mergebot/tree/main/docs/configuration\n"
                    "repository:\n"
                    f"  type: {platform_type}\n"
                    f"  {platform_type}:\n"
                    f"    base_branch: {base_branch}\n"
                    "approval_policy:\n"
                    "  threshold: 3.0\n"
                    "  weights:\n"
                    "    CodeAnalysis: 0.4\n"
                    "    ComplexityAnalysis: 0.2\n"
                    "    TestAnalysis: 0.2\n"
                    "    RiskAnalysis: 0.2\n"
                    "analysis:\n"
                    "  max_mrs: 10\n"
                    "merge:\n"
                    "  enabled: false\n"
                    "  threshold: 2.5\n"
                    "  strategy: repo_default\n"
                    "  rules:\n"
                    "    ci_passed: true\n"
                    "    ci_strict: false\n"
                    "    no_changes_requested: true\n"
                    "    mergeable: true\n"
                    "    approval_state: true\n"
                    "    branch_prefixes:\n"
                    '      - "feature/"\n'
                    '      - "renovate/"\n'
                    '      - "dependabot/"\n'
                )
                pr_url = onboarding.create_onboarding_pr(default_mergebot_yml)
                logger.info(f"Onboarding PR created: <{pr_url}>")
                logger.error("Onboarding required. Please merge the PR to enable Mergebot.")
                raise EnsureRepoConfigError("Onboarding PR created for project")
    except InvalidMergebotYAMLError as e:
        logger.error(f"Invalid .mergebot.yml detected: {e}")
        raise EnsureRepoConfigError(str(e)) from e
    except Exception as e:
        logger.error(f"Error while ensuring repo config: {e}")
        raise EnsureRepoConfigError(str(e)) from e

    logger.info("Mergebot configuration successfully ensured.")
    if runtime is None:
        logger.error("Failed to initialize ProjectRuntime.")
        raise EnsureRepoConfigError("Failed to initialize ProjectRuntime.")
    return runtime
