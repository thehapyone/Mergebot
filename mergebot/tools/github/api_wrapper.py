import os
import time

import jwt
import requests
from github import Github

from mergebot.tools.api_base import PullRequestAPIBase
from mergebot.validator.config import get_runtime_config


def generate_github_app_jwt(app_id: str, private_key: str) -> str:
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + (10 * 60),
        "iss": app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


class GitHubAPIWrapper(PullRequestAPIBase):
    """
    GitHub API Wrapper supporting both PAT and GitHub App authentication.
    """

    config_section: str = "github"

    # GitHub App attributes
    github_app_id: str = None
    github_installation_id: str = None
    github_app_private_key: str = None
    github_app_access_token: str = None

    def validate_github(self):
        cfg = get_runtime_config()["repository"]["github"]

        # 1) API URL
        self.github_api_url = (
            self.github_api_url
            or cfg.get("api_url")
            or os.getenv("GITHUB_API_URL", "https://api.github.com")
        )

        # 2) Repository (must exist in some source)
        self.github_repository = (
            self.github_repository
            or cfg.get("github_repository")
            or os.getenv("GITHUB_REPOSITORY")
        )
        if not self.github_repository:
            raise ValueError(
                "GitHub repository must be provided via CLI, config.yaml or GITHUB_REPOSITORY."
            )

        # 3) Auth: Prefer PAT, else GitHub App
        self.github_personal_access_token = (
            self.github_personal_access_token
            or cfg.get("private_token")
            or os.getenv("GITHUB_TOKEN")
        )

        # --- GitHub App authentication ---
        self.github_app_id = (
            self.github_app_id
            or str(cfg.get("app_id") or os.getenv("GITHUB_APP_ID") or "").strip()
        )
        self.github_installation_id = (
            self.github_installation_id
            or str(
                cfg.get("installation_id")
                or os.getenv("GITHUB_APP_INSTALLATION_ID")
                or ""
            ).strip()
        )
        self.github_app_private_key = cfg.get("private_key") or os.getenv(
            "GITHUB_APP_PRIVATE_KEY"
        )

        # --- Authentication logic ---
        if self.github_app_id and self.github_app_private_key:
            # Prefer GitHub App regardless of PAT
            self._initialize_github_app(self.github_repository)
            self.github = Github(
                self.github_app_access_token, base_url=self.github_api_url
            )
        else:
            # Fallback to PAT
            self.github = Github(
                self.github_personal_access_token, base_url=self.github_api_url
            )

        # Initialize the repository instance
        self.github_repo_instance = self.github.get_repo(self.github_repository)

    def _discover_installation_id(self, jwt_token: str, repo_full_name: str) -> str:
        """
        Finds the installation_id for the app on the given repository.
        """
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
        }
        url = f"{self.github_api_url}/repos/{repo_full_name}/installation"
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            return str(resp.json().get("id"))
        return None

    def _get_installation_token(self, jwt_token: str, installation_id: str) -> str:
        """
        Exchanges a JWT for an installation access token.
        """
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
        }
        url = f"{self.github_api_url}/app/installations/{installation_id}/access_tokens"
        resp = requests.post(url, headers=headers)
        if resp.status_code == 201:
            app_access_token = resp.json().get("token")
            if app_access_token:
                return app_access_token
            raise ValueError("Failed to obtain GitHub App installation access token.")
        raise Exception(
            f"Failed to get installation access token: {resp.status_code} {resp.text}"
        )

    def _initialize_github_app(self, repo):
        """
        Initializes the GitHub App authentication.
        If installation_id is not provided, it will be auto-discovered.
        If private_key is not provided, it will raise an error.
        """
        jwt_token = generate_github_app_jwt(
            self.github_app_id, self.github_app_private_key
        )

        if not self.github_installation_id:
            self.github_installation_id = self._discover_installation_id(
                jwt_token, repo
            )
            if not self.github_installation_id:
                raise ValueError(
                    "Could not determine GitHub App installation_id for repository."
                )

        self.github_app_access_token = self._get_installation_token(
            jwt_token, self.github_installation_id
        )

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

    def get_pull_request_status(self, pr_number: int) -> dict:
        """
        Return structured PR status used for merge guardrails.
        """
        try:
            pr = self.github_repo_instance.get_pull(pr_number)
            # Draft status
            draft = bool(getattr(pr, "draft", False))
            # Mergeable state
            mergeable = pr.mergeable
            # Reviews summary
            approved = 0
            changes_requested = 0
            try:
                for review in pr.get_reviews():
                    state = (review.state or "").upper()
                    if state == "APPROVED":
                        approved += 1
                    elif state == "CHANGES_REQUESTED":
                        changes_requested += 1
            except Exception:
                # If reviews API fails for any reason, leave counts at 0
                pass
            approval_state = approved > 0 and changes_requested == 0

            # CI status via combined status on HEAD commit
            ci_passed = None
            try:
                head_sha = pr.head.sha
                commit = self.github_repo_instance.get_commit(head_sha)
                combined = commit.get_combined_status()
                # success | failure | pending
                ci_passed = (combined.state or "").lower() == "success"
            except Exception:
                ci_passed = None

            return {
                "state": pr.state,
                "draft": draft,
                "mergeable": bool(mergeable) if mergeable is not None else None,
                "ci_passed": ci_passed,
                "approval_state": approval_state,
                "source_branch": getattr(pr.head, "ref", None),
                "target_branch": getattr(pr.base, "ref", None),
                "reviews": {
                    "changes_requested": changes_requested,
                    "approved": approved,
                },
            }
        except Exception as e:
            return {
                "error": f"Failed to retrieve pull request status for ID {pr_number}: {str(e)}"
            }

    def merge_pull_request(self, pr_number: int, strategy: str = "repo_default") -> str:
        """
        Merge the pull request using the preferred strategy.
        strategy: repo_default | merge | squash | rebase
        """
        try:
            pr = self.github_repo_instance.get_pull(pr_number)
            if strategy == "repo_default":
                result = pr.merge()  # respect repo defaults if possible
            else:
                method = (
                    strategy if strategy in {"merge", "squash", "rebase"} else "merge"
                )
                result = pr.merge(merge_method=method)
            if getattr(result, "merged", False) or (
                isinstance(result, dict) and result.get("merged") is True
            ):
                return f"Merged PR #{pr_number}: {pr.html_url}"
            else:
                message = getattr(result, "message", None) or result.get("message")
                return f"Failed to merge PR #{pr_number}: {message}"
        except Exception as e:
            return f"Failed to merge Pull Request {pr_number}: {str(e)}"

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

            self.github_repo_instance.update_file(
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

    def search_issues(self, title: str):
        """
        Search for issues in the repository by title.
        Returns a list of issues whose title matches (case-insensitive).
        """
        issues = self.github_repo_instance.get_issues(state="all")
        return [
            issue.raw_data
            for issue in issues
            if issue.title.strip().lower() == title.strip().lower()
        ]

    def create_issue(self, title: str, description: str):
        """
        Create a new issue in the repository.
        Returns the created issue object (as dict).
        """
        issue = self.github_repo_instance.create_issue(title=title, body=description)
        return issue.raw_data

    def update_issue(self, issue_number: int, description: str):
        """
        Update the description/body of an issue.
        """
        issue = self.github_repo_instance.get_issue(number=issue_number)
        issue.edit(body=description)
        return issue.raw_data
