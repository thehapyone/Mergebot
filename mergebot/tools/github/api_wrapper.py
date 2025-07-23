import os

from github import Github

from mergebot.tools.api_base import PullRequestAPIBase
from mergebot.validator.config import get_runtime_config


class GitHubAPIWrapper(PullRequestAPIBase):
    """
    GitHub API Wrapper.
    """

    config_section: str = "github"

    def validate_github(self):
        cfg = get_runtime_config()["repository"]["github"]

        # 1) API URL
        self.github_api_url = (
            self.github_api_url
            or cfg.get("api_url")
            or os.getenv("GITHUB_API_URL", "https://api.github.com")
        )

        # 2) Repository (must exist in some source)
        self.github_repo = (
            self.github_repo
            or cfg.get("github_repository")
            or os.getenv("GITHUB_REPOSITORY")
        )
        if not self.github_repo:
            raise ValueError(
                "GitHub repository must be provided via CLI, config.yaml or GITHUB_REPOSITORY."
            )

        # 3) Token (must exist in some source)
        self.github_personal_access_token = (
            self.github_personal_access_token
            or cfg.get("private_token")
            or os.getenv("GITHUB_TOKEN")
        )
        if not self.github_personal_access_token:
            raise ValueError(
                "GitHub Personal Access Token must be provided via CLI, config.yaml or GITHUB_TOKEN."
            )

        # 4) Branches w/ defaults
        self.github_branch = (
            self.github_branch
            or cfg.get("branch")
            or cfg.get("base_branch")
            or os.getenv("GITHUB_BRANCH", "main")
        )
        self.gitlab_base_branch = (
            self.gitlab_base_branch
            or cfg.get("base_branch")
            or os.getenv("GITHUB_BASE_BRANCH", "main")
        )

        # Instantiate & authenticate the GitHub client
        self.github = Github(
            self.github_personal_access_token, base_url=self.github_api_url
        )
        self.github_repo_instance = self.github.get_repo(self.gitlab_repository)

    def get_pull_request(self, pr_number: int) -> str:
        try:
            pr = self.github_repo_instance.get_pull(pr_number)
            files = list(pr.get_files())
            additions = sum(f.additions for f in files)
            deletions = sum(f.deletions for f in files)
            total_files_changed = len(files)
            file_changes = [
                {
                    "filename": f.filename,
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "changes": f.changes,
                    "patch": getattr(f, "patch", None),
                }
                for f in files
            ]
            pr_details = {
                "number": pr.number,
                "title": pr.title,
                "user": pr.user.login,
                "state": pr.state,
                "created_at": pr.created_at.isoformat(),
                "updated_at": pr.updated_at.isoformat(),
                "base": pr.base.ref,
                "head": pr.head.ref,
                "mergeable": pr.mergeable,
                "labels": [label.name for label in pr.labels],
                "url": pr.html_url,
                "additions": additions,
                "deletions": deletions,
                "total_files_changed": total_files_changed,
                "file_changes": file_changes,
                "body": pr.body,
                "is_draft": pr.draft,
                "merged": pr.merged,
                "mergeable_state": pr.mergeable_state,
                "review_comments": [c.body for c in pr.get_review_comments()],
                "comments": [c.body for c in pr.get_issue_comments()],
            }
            return self.pretty_print_pull_request(pr_details)
        except Exception as e:
            return {
                "error": f"Failed to retrieve pull request details for ID {pr_number}: {str(e)}"
            }

    def comment_pull_request(self, pr_number: int, body: str) -> str:
        try:
            pr = self.github_repo_instance.get_pull(pr_number)
            comment = pr.create_issue_comment(body)
            comment_url = f"{pr.html_url}#issuecomment-{comment.id}"
            return f"Comment posted at {comment_url}"
        except Exception as e:
            return f"Failed to post comment to Pull Request {pr_number}: {str(e)}"

    def approve_pull_request(self, pr_number: int) -> str:
        try:
            pr = self.github_repo_instance.get_pull(pr_number)
            review = pr.create_review(event="APPROVE")
            review_url = f"{pr.html_url}#pullrequestreview-{review.id}"
            return f"Approved PR #{pr_number}. Review: {review_url}"
        except Exception as e:
            return f"Failed to approve Pull Request {pr_number}: {str(e)}"

    def create_file(
        self, branch_name: str, file_path: str, file_contents: str, commit_message: str
    ) -> bool:
        """
        Creates a new file on the repo
        Returns:
            str: A success or failure
        """
        try:
            self.github_repo_instance.get_contents(file_path, ref=branch_name)
            return False  # File already exists
        except Exception:
            # File does not exist, proceed to create it
            self.github_repo_instance.create_file(
                path=file_path,
                message=commit_message,
                content=file_contents,
                branch=branch_name,
            )
        return True

    def update_file(
        self, branch_name: str, file_path: str, file_contents: str, commit_message: str
    ):
        """Updates an existing file on the repo"""

        created = self.create_file(
            branch_name=branch_name,
            file_path=file_path,
            file_contents=file_contents,
            commit_message=commit_message,
        )

        if created:
            return

        # If file creation failed, try updating the existing file
        try:
            file = self.github_repo_instance.get_contents(file_path, ref=branch_name)

            self.project.update_file(
                path=file_path,
                message=commit_message,
                content=file_contents,
                sha=file.sha,
                branch=branch_name,
            )
        except Exception as e:
            raise Exception(
                f"Failed to update file {file_path} in branch {branch_name}: {str(e)}"
            )
