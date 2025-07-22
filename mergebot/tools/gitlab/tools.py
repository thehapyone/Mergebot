from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from mergebot.tools.gitlab.api_wrapper import GitlabAPIWrapper
from mergebot.tools.gitlab.prompts import (
    APPROVE_MERGE_REQUEST_PROMPT,
    FETCH_PIPELINE_DETAILS_PROMPT,
    GET_MERGE_REQUEST_PROMPT,
    POST_MERGE_REQUEST_COMMENT_PROMPT,
)


class BaseGitLabTool(BaseTool):
    """Base class for all GitLab tools with common functionality."""

    _api_wrapper: GitlabAPIWrapper = None

    @property
    def api_wrapper(self) -> GitlabAPIWrapper:
        """Lazy initialization of API wrapper to ensure project is available."""
        if self._api_wrapper is None:
            self._api_wrapper = GitlabAPIWrapper()
        return self._api_wrapper


class GitlabPipelineToolSchema(BaseModel):
    """Input for GitlabPipelineTool."""

    pipeline_id: str = Field(..., description="The ID of the pipeline")


class GitlabPipelineTool(BaseGitLabTool):
    """Tool for fetching and summarizing pipeline details from GitLab."""

    name: str = "Get Pipeline Details"
    description: str = FETCH_PIPELINE_DETAILS_PROMPT
    args_schema: Type[BaseModel] = GitlabPipelineToolSchema

    def _run(
        self,
        **kwargs: Any,
    ) -> str:
        """Use the GitLab API to fetch pipeline details."""
        pipeline_id = kwargs.get("pipeline_id")

        if not pipeline_id:
            return "The Pipeline ID is required."
        try:
            pipeline_details = self.api_wrapper.get_pipeline_details(int(pipeline_id))
            return pipeline_details
        except ValueError:
            return "Invalid input. Please provide the Pipeline ID as an integer."


class GitlabMRToolSchema(BaseModel):
    """Input for GitlabMRTools."""

    merge_request_iid: str = Field(
        ..., description="The project level ID of the merge request"
    )


class GitlabMergeRequestTool(BaseGitLabTool):
    """Tool for getting merge requests from the GitLab API."""

    mode: str = "get_merge_request"
    name: str = "Get Merge Requests"
    description: str = GET_MERGE_REQUEST_PROMPT
    args_schema: Type[BaseModel] = GitlabMRToolSchema

    def _run(
        self,
        **kwargs: Any,
    ) -> str:
        """Use the GitLab API to run an operation."""
        mr_iid = kwargs.get("merge_request_iid")

        if not mr_iid:
            return "The Merge Request IID is required."

        try:
            mr_details = self.api_wrapper.get_merge_request(int(mr_iid))
            return mr_details
        except ValueError:
            return (
                "Invalid input. Please provide the Merge Request number as an integer."
            )


class GitlabCommentToolSchema(BaseModel):
    """Input for GitlabTools."""

    merge_request_iid: str = Field(
        ..., description="The project level ID of the merge request"
    )
    comment: str = Field(
        ..., description="The merge request comment to be posted to the MR"
    )


class GitlabMergeCommentTool(BaseGitLabTool):
    """Tool for posting merge comments using the Gitlab API."""

    name: str = "Post Merge Requests Comment"
    description: str = POST_MERGE_REQUEST_COMMENT_PROMPT
    args_schema: Type[BaseModel] = GitlabCommentToolSchema

    def _run(
        self,
        **kwargs: Any,
    ) -> str:
        """Use the GitLab API to run an operation."""
        mr_iid = kwargs.get("merge_request_iid")
        mr_comment = kwargs.get("comment")

        if not (mr_iid or mr_comment):
            return "The Merge Request IID and message are required."

        return self.api_wrapper.comment_pull_request(
            pr_number=int(mr_iid), body=mr_comment
        )


class GitlabMergeApprovalTool(BaseGitLabTool):
    """Tool for approving Gitlab merge requests."""

    name: str = "Approve Merge Requests Comment"
    description: str = APPROVE_MERGE_REQUEST_PROMPT
    args_schema: Type[BaseModel] = GitlabMRToolSchema

    def _run(
        self,
        **kwargs: Any,
    ) -> str:
        """Use the GitLab API to run an operation."""
        mr_iid = kwargs.get("merge_request_iid")

        if not mr_iid:
            return "The Merge Request IID are required."

        try:
            return self.api_wrapper.approve_pull_request(int(mr_iid))
        except ValueError:
            return "Invalid input parameters provided. Please ensure the Merge Request IID is an integer."
