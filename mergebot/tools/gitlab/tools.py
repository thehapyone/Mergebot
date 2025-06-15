from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from mergebot.tools.gitlab.api_wrapper import GitLabAPIWrapperExtra
from mergebot.tools.gitlab.prompts import (
    APPROVE_MERGE_REQUEST_PROMPT,
    FETCH_PIPELINE_DETAILS_PROMPT,
    GET_MERGE_REQUEST_PROMPT,
    POST_MERGE_REQUEST_COMMENT_PROMPT,
)


class BaseGitLabTool(BaseTool):
    """Base class for all GitLab tools with common functionality."""

    def __init__(self, api_wrapper: GitLabAPIWrapperExtra, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._api_wrapper = api_wrapper

    @property
    def api_wrapper(self) -> GitLabAPIWrapperExtra:
        """Access the injected API wrapper instance."""
        return self._api_wrapper


class GitlabPipelineToolSchema(BaseModel):
    """Input for GitlabPipelineTool."""

    pipeline_id: str = Field(..., description="The ID of the pipeline")


class GitlabPipelineTool(BaseGitLabTool):
    """Tool for fetching and summarizing pipeline details from GitLab."""

    mode: str = "get_pipeline_details"
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

        return self.api_wrapper.run(self.mode, str(pipeline_id))


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

        return self.api_wrapper.run(self.mode, str(mr_iid))


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

    mode: str = "post_merge_request_comment"
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

        return self.api_wrapper.run(
            self.mode, body={"mr_iid": mr_iid, "comment": mr_comment}
        )


class GitlabMergeApprovalTool(BaseGitLabTool):
    """Tool for approving Gitlab merge requests."""

    mode: str = "approve_merge_request"
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

        return self.api_wrapper.run(self.mode, body={"mr_iid": int(mr_iid)})
