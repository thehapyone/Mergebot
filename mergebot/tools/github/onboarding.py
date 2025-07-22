from mergebot.tools.github.api_wrapper import GitHubAPIWrapper
from mergebot.tools.onboarding_base import OnboardingManagerBase


class GitHubOnboardingManager(OnboardingManagerBase):
    """
    Handles GitHub onboarding operations for Mergebot, such as managing the .mergebot.yml
    configuration file, checking if onboarding pull requests exist,
    creating onboarding pull requests, and validating YAML configuration files.
    """

    @property
    def api_wrapper(self):
        if self._api_wrapper is None:
            self._api_wrapper = GitHubAPIWrapper()
            self.vcs = "github"
        return self._api_wrapper

    def onboarding_pr_exists(self):
        default_branch = self.project.default_branch
        pulls = self.project.get_pulls(
            state="open",
            head=f"{self.project.owner.login}:{self.onboarding_branch}",
            base=default_branch,
        )
        return pulls[0].html_url if pulls.totalCount > 0 else None

    def create_onboarding_pr(self, default_content: str):
        default_branch = self.project.default_branch

        # Ensure the branch exists (create if not)
        if not self.branch_exists():
            source_sha = self.project.get_branch(default_branch).commit.sha
            self.project.create_git_ref(
                ref=f"refs/heads/{self.onboarding_branch}", sha=source_sha
            )

        # Write or update the file in the onboarding branch
        self.api_wrapper.update_file(
            branch_name=self.onboarding_branch,
            file_path=self.config_file,
            file_contents=default_content,
            commit_message="chore: add .mergebot.yml for onboarding",
        )

        pr = self.project.create_pull(
            title=self.pr_title,
            body=self.pr_description(),
            head=self.onboarding_branch,
            base=default_branch,
        )
        return pr.html_url
