from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, model_validator


class PullRequestAPIBase(BaseModel):
    """
    Base class for unified pull/merge request API wrappers.
    """

    ## GitHub-specific attributes
    github: Any = None
    github_repo_instance: Any = None
    github_api_url: Optional[str] = None
    github_repository: Optional[str] = None
    github_personal_access_token: Optional[str] = None
    github_branch: Optional[str] = None
    github_base_branch: Optional[str] = None

    ## GitLab-specific attributes
    gitlab: Any = None
    gitlab_repo_instance: Any = None
    gitlab_url: Optional[str] = None
    gitlab_repository: Optional[str] = None
    gitlab_personal_access_token: Optional[str] = None
    gitlab_branch: Optional[str] = None
    gitlab_base_branch: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

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
            raise ValueError(
                "config_section must be set to either 'gitlab' or 'github'"
            )

        return self

    def get_pull_request(self, pr_number: int) -> str:
        """
        Fetch pull/merge request details (pretty-printed).
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses to fetch pull/merge request details."
        )

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

    @staticmethod
    def pretty_print_pull_request(pr_details: dict) -> str:
        """
        Shared pretty-print logic for PR/MR details.
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
            changes_info.extend(
                [
                    f"File: {change.get('filename', change.get('new_path', ''))}",
                    f"  - Additions: {change.get('additions', change.get('lines_added', ''))}",
                    f"  - Deletions: {change.get('deletions', change.get('lines_removed', ''))}",
                    f"  - Changes: {change.get('changes', '')}",
                    (
                        f"  - Patch:\n{change.get('patch', change.get('diff', ''))}\n"
                        if change.get("patch", change.get("diff", None))
                        else ""
                    ),
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
