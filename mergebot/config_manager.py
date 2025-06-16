import sys
import yaml
from mergebot.logging_config import logger
from mergebot.validator.config import runtime_config, get_runtime_config, Config
from mergebot.tools.gitlab.api_wrapper import GitLabAPIWrapperExtra

def ensure_repo_config(project: str):
    """
    Ensures that .mergebot.yml exists in the repo and is valid.
    If found, merges it into the runtime config and validates.
    If not found, creates an onboarding PR and aborts execution.
    If invalid, aborts execution.
    """
    wrapper = GitLabAPIWrapperExtra()
    runtime_config.set("repository.gitlab.gitlab_repository", project)
    mergebot_yml = wrapper.get_mergebot_yml()
    if mergebot_yml:
        try:
            repo_config = yaml.safe_load(mergebot_yml)
            if isinstance(repo_config, dict):
                runtime_config.set_many({f"{k}": v for k, v in repo_config.items()})
            # Validate config
            Config(**get_runtime_config())
            logger.info("Loaded and validated .mergebot.yml from repo.")
        except Exception as e:
            logger.error(f"Failed to parse or validate .mergebot.yml: {e}")
            sys.exit(1)
    else:
        # Create onboarding PR with a default .mergebot.yml
        default_mergebot_yml = (
            "# Default Mergebot configuration\n"
            "# See https://github.com/your-org/mergebot for documentation\n"
            "approval_policy:\n"
            "  enabled: false\n"
            "  threshold: 3.0\n"
            "  weights:\n"
            "    CodeAnalysis: 1.0\n"
            "    ComplexityAnalysis: 1.0\n"
            "    TestAnalysis: 1.0\n"
            "    RiskAnalysis: 1.0\n"
        )
        pr_url = wrapper.create_onboarding_pr(default_mergebot_yml)
        logger.info(f".mergebot.yml not found in repo. Created onboarding PR: {pr_url}")
        logger.error("Onboarding required. Please merge the PR to enable Mergebot.")
        sys.exit(1)
