from mergebot.tools.gitlab.api_wrapper import GitlabAPIWrapper
from mergebot.tools.onboarding_base import OnboardingManagerBase


class GitlabOnboardingManager(OnboardingManagerBase):
    """
    Handles GitLab onboarding operations for Mergebot, such as managing the .mergebot.yml
    configuration file, checking if onboarding pull requests (merge requests) exist,
    creating onboarding merge requests, and validating YAML configuration files.
    """

    vcs: str = "gitlab"

    @property
    def api_wrapper(self):
        if self._api_wrapper is None:
            self._api_wrapper = GitlabAPIWrapper()
        return self._api_wrapper

    def onboarding_pr_exists(self):
        default_branch = self.project.default_branch
        mrs = self.project.mergerequests.list(
            source_branch=self.onboarding_branch,
            target_branch=default_branch,
            state="opened",
            all=True,
        )
        return mrs[0].web_url if mrs else None

    def create_onboarding_pr(self, default_content: str):
        default_branch = self.project.default_branch

        # Ensure the branch exists (create if not)
        if not self.branch_exists():
            self.project.branches.create(
                {"branch": self.onboarding_branch, "ref": default_branch}
            )

        # Write or update the file in the onboarding branch
        self.api_wrapper.update_file(
            branch_name=self.onboarding_branch,
            file_path=self.config_file,
            file_contents=default_content,
            commit_message="chore: add .mergebot.yml for onboarding",
        )

        mr = self.project.mergerequests.create(
            {
                "source_branch": self.onboarding_branch,
                "target_branch": default_branch,
                "title": self.pr_title,
                "remove_source_branch": True,
                "description": self.pr_description(),
            }
        )
        return mr.web_url
