from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from mergebot.tools.github.api_wrapper import GitHubAPIWrapper


class BaseGitHubTool(BaseTool):
    """Base class for all GitHub tools with common functionality."""

    _api_wrapper: GitHubAPIWrapper = None

    @property
    def api_wrapper(self) -> GitHubAPIWrapper:
        """Lazy initialization of API wrapper to ensure project is available."""
        if self._api_wrapper is None:
            self._api_wrapper = GitHubAPIWrapper()
        return self._api_wrapper


class GitHubPRToolSchema(BaseModel):
    """Input for GitHubPRTool."""

    pr_number: int = Field(..., description="The pull request number")


class GitHubPullRequestTool(BaseGitHubTool):
    """Tool for getting pull requests from the GitHub API."""

    name: str = "Get Pull Request"
    description: str = "Fetches details for a GitHub pull request."
    args_schema: Type[BaseModel] = GitHubPRToolSchema

    def _run(
        self,
        **kwargs: Any,
    ) -> str:
        pr_number = kwargs.get("pr_number")
        if not pr_number:
            return "The Pull Request number is required."
        return self.api_wrapper.get_pull_request(pr_number)


class GitHubPRCommentToolSchema(BaseModel):
    pr_number: int = Field(..., description="The pull request number")
    comment: str = Field(..., description="The comment to post to the PR")


class GitHubPullRequestCommentTool(BaseGitHubTool):
    """Tool for posting comments to GitHub pull requests."""

    name: str = "Post Pull Request Comment"
    description: str = "Posts a comment to a GitHub pull request."
    args_schema: Type[BaseModel] = GitHubPRCommentToolSchema

    def _run(
        self,
        **kwargs: Any,
    ) -> str:
        pr_number = kwargs.get("pr_number")
        comment = kwargs.get("comment")
        if not (pr_number and comment):
            return "The Pull Request number and comment are required."
        return self.api_wrapper.comment_pull_request(pr_number, comment)


class GitHubPRApprovalTool(BaseGitHubTool):
    """Tool for approving GitHub pull requests."""

    name: str = "Approve Pull Request"
    description: str = "Approves a GitHub pull request."
    args_schema: Type[BaseModel] = GitHubPRToolSchema

    def _run(
        self,
        **kwargs: Any,
    ) -> str:
        pr_number = kwargs.get("pr_number")
        if not pr_number:
            return "The Pull Request number is required."
        return self.api_wrapper.approve_pull_request(pr_number)
