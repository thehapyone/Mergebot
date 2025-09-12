import sys

from mergebot.tools.github.onboarding import GitHubOnboardingManager
from mergebot.tools.gitlab.onboarding import (
    GitlabOnboardingManager,
)
from mergebot.tools.onboarding_base import InvalidMergebotYAML
from mergebot.utils import get_platform_type
from mergebot.validator.config import get_runtime_config, runtime_config
from mergebot.validator.logging_config import logger


def ensure_repo_config(project: str):
    """
    Ensures that a valid Mergebot configuration is present in the repository for the given platform.

    - For supported platforms (currently GitLab):
        - Checks if .mergebot.yml exists in the default branch of the repository.
        - If found and valid, merges it into the runtime config and validates the result.
        - If missing, creates an onboarding PR with a default .mergebot.yml and aborts execution.
        - If present but invalid (malformed YAML), aborts execution and logs a clear error.
    - For unsupported platforms, aborts with an error.

    This function should be called once at application startup, before any flows or runners are executed.
    """
    logger.info(f"Finding Mergebot configuration for project: {project}")
    platform_type = get_platform_type()
    if platform_type == "gitlab":
        runtime_config.set("repository.gitlab.gitlab_repository", project)
        onboarding = GitlabOnboardingManager()
    elif platform_type == "github":
        runtime_config.set("repository.github.github_repository", project)
        onboarding = GitHubOnboardingManager()
    else:
        logger.error(f"Unsupported platform: {platform_type}")
        sys.exit(1)

    try:
        logger.info(f"Checking for .mergebot.yml in repository: {project}")
        repo_config = onboarding.get_mergebot_yml()
        if repo_config is not None:
            logger.info(".mergebot.yml found in repo. Merging and validating config...")
            if isinstance(repo_config, dict):
                runtime_config.set_many({f"{k}": v for k, v in repo_config.items()})
            # Validate config
            _ = get_runtime_config(as_pydantic=True)
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
                sys.exit(1)
            else:
                logger.info(
                    "No existing onboarding PR found. Creating onboarding PR..."
                )
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
                    "      - \"feature/\"\n"
                    "      - \"bugfix/\"\n"
                )
                pr_url = onboarding.create_onboarding_pr(default_mergebot_yml)
                logger.info(f"Onboarding PR created: <{pr_url}>")
                logger.error(
                    "Onboarding required. Please merge the PR to enable Mergebot."
                )
                sys.exit(1)
    except InvalidMergebotYAML as e:
        logger.error(f"Invalid .mergebot.yml detected: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error while ensuring repo config: {e}", exc_info=True)
        sys.exit(1)

    logger.info("Mergebot configuration successfully ensured.")
