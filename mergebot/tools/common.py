"""
This module provides a set of base classes and tools for interaction with version control systems,
specifically GitHub and GitLab, through unified APIs. The tools abstract common actions performed
on pull/merge requests and CI/CD pipelines, including fetching request details, posting comments,
approving requests, and obtaining pipeline status.

Key Components:

- BaseVCSTool: Abstract base class to provide lazy instantiation of platform-specific API wrappers
  (GitHubAPIWrapper or GitlabAPIWrapper), based on the current platform as returned by get_platform_type().
- PRToolSchema, PullRequestCommentToolSchema, PullRequestApprovalToolSchema, PipelineToolSchema:
  Pydantic models defining expected arguments for corresponding tools.
- PullRequestTool: Retrieves pull or merge request details.
- PullRequestCommentTool: Posts comments on pull or merge requests.
- PullRequestApprovalTool: Approves pull or merge requests.
- GitlabPipelineTool: Fetches and summarizes GitLab pipeline details.

Each tool uses the BaseVCSTool to interface with the proper API wrapper. The descriptions for each
tool are imported from mergebot.tools.prompts and each exposes a _run method for execution in a toolchain.
"""

from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from mergebot.tools.github.api_wrapper import GitHubAPIWrapper
from mergebot.tools.gitlab.api_wrapper import GitlabAPIWrapper
from mergebot.tools.prompts import (
    APPROVE_MERGE_REQUEST_PROMPT,
    GET_PULL_REQUEST_PROMPT,
    POST_PULL_REQUEST_COMMENT_PROMPT,
)
from mergebot.utils import get_platform_type


class BaseVCSTool(BaseTool):
    """Base class for all GitHub and gitlab tools with common functionality."""

    _api_wrapper: GitHubAPIWrapper | GitlabAPIWrapper = None

    @property
    def api_wrapper(self) -> GitHubAPIWrapper | GitlabAPIWrapper:
        """
        Returns the appropriate API wrapper instance for the configured platform.

        Lazily instantiates the API wrapper for either GitHub or GitLab,
        depending on the platform type returned by get_platform_type().
        If the platform is not supported, raises a ValueError.

        Returns:
            GitHubAPIWrapper or GitlabAPIWrapper: The initialized API wrapper instance.

        Raises:
            ValueError: If the returned platform type is not supported.
        """
        if self._api_wrapper is None:
            platform_type = get_platform_type()
            if platform_type == "github":
                self._api_wrapper = GitHubAPIWrapper()
            elif platform_type == "gitlab":
                self._api_wrapper = GitlabAPIWrapper()
            else:
                raise ValueError(f"Unsupported platform type: {platform_type}")
        return self._api_wrapper


class PRToolSchema(BaseModel):
    """Input for a pull or merge request tool."""

    pr_number: int = Field(..., description="Pull or merge request number")


class PullRequestTool(BaseVCSTool):
    """Tool for getting pull or merge requests from the VCS platform."""

    name: str = "Get Pull Request"
    description: str = GET_PULL_REQUEST_PROMPT
    args_schema: Type[BaseModel] = PRToolSchema

    def _run(
        self,
        **kwargs: Any,
    ) -> str:
        pr_number = kwargs.get("pr_number")
        if not pr_number:
            return "The Pull Request number is required."
        return self.api_wrapper.get_pull_request(pr_number)


class PullRequestCommentToolSchema(BaseModel):
    pr_number: int = Field(..., description="The pull or merge request number")
    comment: str = Field(
        ..., description="The comment to post to the pull or merge request"
    )


class PullRequestCommentTool(BaseVCSTool):
    """Tool for posting comments to pull or merge requests."""

    name: str = "Post Pull Request Comment"
    description: str = POST_PULL_REQUEST_COMMENT_PROMPT
    args_schema: Type[BaseModel] = PullRequestCommentToolSchema

    def _run(
        self,
        **kwargs: Any,
    ) -> str:
        pr_number = kwargs.get("pr_number")
        comment = kwargs.get("comment")
        if not (pr_number and comment):
            return "The pull or merge request number and comment are required."
        return self.api_wrapper.comment_pull_request(pr_number, comment)


class PullRequestApprovalToolSchema(BaseModel):
    pr_number: int = Field(..., description="The pull or merge request number")


class PullRequestApprovalTool(BaseVCSTool):
    """Tool for approving pull or merge requests."""

    name: str = "Approve Pull Request"
    description: str = APPROVE_MERGE_REQUEST_PROMPT
    args_schema: Type[BaseModel] = PullRequestApprovalToolSchema

    def _run(
        self,
        **kwargs: Any,
    ) -> str:
        pr_number = kwargs.get("pr_number")
        if not pr_number:
            return "The pull or merge request number is required."
        return self.api_wrapper.approve_pull_request(pr_number)


class PipelineToolSchema(BaseModel):
    """Input for the Pipeline tool."""

    pipeline_id: str = Field(..., description="The ID of the pipeline")
