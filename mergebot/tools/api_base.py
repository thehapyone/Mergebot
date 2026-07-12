from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from mergebot.validator.config import Config
from mergebot.workspace.manager import PrRef


@dataclass(frozen=True)
class PullRequestDetails:
    """Pretty-printed PR/MR details plus typed metadata for workspace provisioning.

    `details` is the exact text blob the analysis crews consume today; `details_no_patch`
    is the same render with per-file patches omitted (used when the fact pack's
    compressed diff replaces the raw patch); `ref` is best-effort and None when the
    platform metadata could not be resolved.
    """

    details: str
    details_no_patch: str
    ref: PrRef | None = None


class PullRequestAPIBase(BaseModel):
    """
    Base class for unified pull/merge request API wrappers.
    """

    config: Config
    project_path: str
    ## GitHub-specific attributes
    github: Any = None
    github_repo_instance: Any = None
    github_api_url: str | None = None
    github_repository: str | None = None
    github_personal_access_token: str | None = None
    github_branch: str | None = None
    github_base_branch: str | None = None

    ## GitLab-specific attributes
    gitlab: Any = None
    gitlab_repo_instance: Any = None
    gitlab_url: str | None = None
    gitlab_repository: str | None = None
    gitlab_personal_access_token: str | None = None
    gitlab_branch: str | None = None
    gitlab_base_branch: str | None = None

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def validate_gitlab(self):
        """
        Loads and validates GitLab configuration and environment variables.

        This method sets the GitLab-related fields as follows:
        1. Loads configuration values from runtime config, environment variables, and user-provided attributes.
        2. Ensures that a GitLab repository and personal access token are defined, raising ValueError if missing.
        3. Sets branch and base_branch fields with fallbacks to defaults.
        4. Initializes and authenticates the GitLab client instance, setting up the repository instance.

        Raises:
            ValueError: If gitlab_repository or gitlab_personal_access_token is not provided.
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses to handle GitLab-specific validation."
        )

    def validate_github(self):
        """
        Loads and validates Github configuration and environment variables.

        This method sets the Github-related fields as follows:
        1. Loads configuration values from runtime config, environment variables, and user-provided attributes.
        2. Ensures that a Github repository and personal access token are defined, raising ValueError if missing.
        3. Sets branch and base_branch fields with fallbacks to defaults.
        4. Initializes and authenticates the Github client instance, setting up the repository instance.

        Raises:
            ValueError: If github_repository or github_personal_access_token is not provided.
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses to handle Github-specific validation."
        )

    @model_validator(mode="after")
    def validate_environment(self) -> "PullRequestAPIBase":
        """
        Load & validate config from:
          1) kwargs passed into the constructor
          2) repository.gitlab section in config.yaml
          3) environment variables
          4) sensible defaults
        """

        if self.config_section == "gitlab":
            self.validate_gitlab()
        elif self.config_section == "github":
            self.validate_github()
        else:
            raise ValueError("config_section must be set to either 'gitlab' or 'github'")

        return self

    def get_pull_request(self, pr_number: int) -> str:
        """
        Fetch pull/merge request details (pretty-printed).

        Thin delegate over `get_pull_request_with_ref`: returns only the text blob on
        success and passes the `{"error": ...}` dict through unchanged on failure.
        """
        result = self.get_pull_request_with_ref(pr_number)
        if isinstance(result, PullRequestDetails):
            return result.details
        return result

    def comment_pull_request(self, pr_number: int, body: str) -> str:
        """
        Post a comment to a pull/merge request and return the comment link.
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses to fetch pull/merge request details."
        )

    def approve_pull_request(self, pr_number: int) -> str:
        """
        Approve a pull/merge request and return the review/approval link.
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses to fetch pull/merge request details."
        )

    def get_pull_request_status(self, pr_number: int) -> dict:
        """
        Return a structured status for pre-merge guardrails:
        {
          "state": "open|closed|merged",
          "draft": bool,
          "mergeable": bool|None,
          "ci_passed": bool|None,
          "approval_state": bool|None,
          "source_branch": str|None,
          "target_branch": str|None,
          "reviews": {
            "changes_requested": int,
            "approved": int
          }
        }
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses to return PR/MR status."
        )

    def merge_pull_request(self, pr_number: int, strategy: str = "repo_default") -> str:
        """
        Perform the merge operation using the repository's platform.
        strategy: 'repo_default' | 'merge' | 'squash' | 'rebase' (platform support varies)
        Returns a human-readable string (include a link when available).
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses to perform the merge."
        )

    def get_pull_request_with_ref(self, pr_number: int) -> "PullRequestDetails | dict":
        """
        Fetch pull/merge request details as `PullRequestDetails` (pretty text in both
        renders plus a typed `PrRef`), or an `{"error": ...}` dict on failure.
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses to fetch pull/merge request details."
        )

    def resolve_git_token(self) -> str | None:
        """
        Return the already-resolved platform token usable for git HTTPS auth
        (GitHub App installation token or PAT; GitLab PAT).
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses to expose the platform token."
        )

    @staticmethod
    def pretty_print_pull_request(pr_details: dict, include_patch: bool = True) -> str:
        """
        Shared pretty-print logic for PR/MR details.

        With `include_patch=False` the per-file patches are omitted (used when the
        repository-context compressed diff replaces the raw patch for large PRs).
        """
        pr_metadata = [
            "## Pull Request Details:",
            f"PR Number: {pr_details.get('number', pr_details.get('iid', ''))}",
            f"Title: {pr_details['title']}",
            f"Author: {pr_details.get('user', pr_details.get('author', ''))}",
            f"State: {pr_details['state']}",
            f"Created At: {pr_details['created_at']}",
            f"Updated At: {pr_details['updated_at']}",
            f"Target Branch: {pr_details.get('base', pr_details.get('target_branch', ''))}",
            f"Source Branch: {pr_details.get('head', pr_details.get('source_branch', ''))}",
            f"Labels: {', '.join(pr_details.get('labels', []))}",
            f"Draft: {pr_details.get('is_draft', False)}",
            f"Merged: {pr_details.get('merged', False)}",
            f"Mergeable: {pr_details.get('mergeable', '')}",
            f"Mergeable State: {pr_details.get('mergeable_state', '')}",
            f"Web URL: {pr_details['url']}",
        ]

        # Prepare Changes and Statistics strings
        changes_info = ["\n## Changes:"]
        for change in pr_details.get("file_changes", pr_details.get("changes", [])):
            patch = change.get("patch", change.get("diff", None))
            if not patch:
                patch_line = ""
            elif include_patch:
                patch_line = f"  - Patch:\n{patch}\n"
            else:
                patch_line = "  - Patch: omitted here; see the Repository Context compressed diff\n"
            changes_info.extend(
                [
                    f"File: {change.get('filename', change.get('new_path', ''))}",
                    f"  - Additions: {change.get('additions', change.get('lines_added', ''))}",
                    f"  - Deletions: {change.get('deletions', change.get('lines_removed', ''))}",
                    f"  - Changes: {change.get('changes', '')}",
                    patch_line,
                ]
            )
        stats_info = [
            "## Statistics:",
            f"Total Files Changed: {pr_details.get('total_files_changed')}",
            f"Total Lines Added: {pr_details.get('additions', pr_details.get('total_lines_added', ''))}",
            f"Total Lines Removed: {pr_details.get('deletions', pr_details.get('total_lines_removed', ''))}",
        ]

        # Add Pipeline Summary block if available
        pipeline_summary = pr_details.get("pipeline", "")

        full_output = "\n".join(
            pr_metadata
            + changes_info
            + stats_info
            + [f"\nBody:\n{pr_details['body']}"]
            + [pipeline_summary]
        )
        return full_output

    def search_issues(self, title: str):
        """
        Search for issues in the project by title.
        Returns a list of issues whose title matches (case-insensitive).
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses to fetch pull/merge request details."
        )

    def create_issue(self, title: str, description: str):
        """
        Create a new issue in the project.
        Returns the created issue object (as dict).
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses to fetch pull/merge request details."
        )

    def update_issue(self, issue_iid: int, description: str):
        """
        Update the description/body of an issue.
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses to fetch pull/merge request details."
        )

    def create_file(
        self, branch_name: str, file_path: str, file_contents: str, commit_message: str
    ) -> bool:
        """
        Creates a new file on the repo
        Returns:
            str: A success or failure
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses to fetch pull/merge request details."
        )

    def update_file(
        self, branch_name: str, file_path: str, file_contents: str, commit_message: str
    ):
        """Updates an existing file on the repo"""

        raise NotImplementedError(
            "This method should be implemented in subclasses to fetch pull/merge request details."
        )
