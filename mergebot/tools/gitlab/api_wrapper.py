import json
import os
import re
from typing import Any, Dict, List, Optional

import gitlab
from pydantic import BaseModel, ConfigDict, model_validator

from mergebot.validator.config import get_runtime_config


def strip_ansi_codes(text: str) -> str:
    """
    Removes ANSI escape sequences from the text.

    Parameters:
        text (str): The text containing ANSI codes.

    Returns:
        str: The cleaned text without ANSI codes.
    """
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text)


def parse_job_log(log: str, job_status: str) -> Dict[str, Any]:
    """
    Parses the job log to extract warnings and errors with context

    Parameters:
        log (str): The job log string.
        job_status (str): Status of the job (e.g., 'success', 'failed').

    Returns:
        Dict[str, Any]: A dictionary containing lists of warnings and errors with context.
    """
    # First, extract the scripts in section
    script_lines = log.split("\n")

    warnings = []
    errors = []

    # Remove ANSI codes from lines
    lines = [strip_ansi_codes(line) for line in script_lines]

    context_size = 5
    # If the job failed, capture the tail of the step_script
    if job_status == "failed":
        error_context = "\n".join(lines[-30:])
        errors.append(error_context)
    else:
        # For successful jobs, look for warnings and errors with context
        i = 0
        while i < len(lines):
            line = lines[i]
            if "WARNING" in line or "WARN" in line:
                # Collect context lines before and after
                start = max(i - context_size, 0)
                end = min(i + context_size, len(lines))
                context = "\n".join(lines[start:end])
                warnings.append(context)
                i = end  # Skip lines already processed
            else:
                i += 1

    return {"warnings": warnings, "errors": errors}


def parse_diff_content(diff: str):
    """
    Parses the diff content to calculate lines added and removed.

    Parameters:
        diff (str): The diff string.

    Returns:
        Tuple[int, int]: Number of lines added and removed.
    """
    additions = len(re.findall(r"^(\+[^+])", diff, re.MULTILINE))
    deletions = len(re.findall(r"^-(?!-)", diff, re.MULTILINE))
    return additions, deletions


def pretty_print_merge_request(mr_details: dict):
    # Prepare MR Metadata string
    mr_metadata = [
        "## Merge Request Details:",
        f"MR IID: {mr_details['mr']['iid']}",
        f"Title: {mr_details['mr']['title']}",
        f"Author: {mr_details['mr']['author']['name']} ({mr_details['mr']['author']['username']})",
        f"State: {mr_details['mr']['state']}",
        f"Created At: {mr_details['mr']['created_at']}",
        f"Updated At: {mr_details['mr']['updated_at']}",
        f"Source Branch: {mr_details['mr']['source_branch']}",
        f"Target Branch: {mr_details['mr']['target_branch']}",
        f"Labels: {', '.join(mr_details['mr']['labels'])}",
        f"Approvals Required: {mr_details['mr']['approvals_required']}",
        f"Approvals Received: {mr_details['mr']['approvals_received']}",
        f"Web URL: {mr_details['mr']['web_url']}",
        f"Merge Status: {mr_details['mr']['merge_status']}",
        f"First Contribution: {mr_details['mr']['first_contribution']}",
    ]

    # Append Assignee Details
    assignee_info = [
        f"- {assignee['name']} ({assignee['username']})"
        for assignee in mr_details["mr"]["assignees"]
    ]
    mr_metadata.append(
        f"Assignees:\n{chr(10).join(assignee_info) if assignee_info else 'None'}"
    )

    # Add Pipeline Summary block if available
    pipeline_summary = mr_details.get("pipeline")

    # Prepare Changes and Statistics strings
    changes_info = ["\n## Changes:"]
    for change in mr_details["changes"]:
        changes_info.extend(
            [
                f"File: {change['new_path']}",
                f"  - Lines Added: {change['lines_added']}",
                f"  - Lines Removed: {change['lines_removed']}",
                f"  - Change Type: {'New File' if change['new_file'] else 'Renamed File' if change['renamed_file'] else 'Deleted File' if change['deleted_file'] else 'Modified'}",
                f"  - Generated File: {'Yes' if change['generated_file'] else 'No'}",
                f"  - Diff:\n{change['diff']}\n",
            ]
        )

    stats_info = [
        "## Statistics:",
        f"Total Files Changed: {mr_details['stats']['total_files_changed']}",
        f"Total Lines Added: {mr_details['stats']['total_lines_added']}",
        f"Total Lines Removed: {mr_details['stats']['total_lines_removed']}",
    ]

    # Compile all information into a single string for output
    full_output = "\n".join(
        mr_metadata + changes_info + stats_info + [pipeline_summary]
    )

    # Return the formatted string
    return full_output


class GitlabAPIWrapper(BaseModel):
    """
    GitLab API Wrapper.
    """

    gitlab: Any = None  #: :meta private:
    gitlab_repo_instance: Any = None  #: :meta private:
    gitlab_url: Optional[str] = None
    gitlab_repository: Optional[str] = None
    gitlab_personal_access_token: Optional[str] = None
    gitlab_branch: Optional[str] = None
    gitlab_base_branch: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def validate_environment(cls, values: Dict) -> Any:
        """
        Load & validate config from:
          1) kwargs passed into the constructor
          2) repository.gitlab section in config.yaml
          3) environment variables
          4) sensible defaults
        """

        cfg = get_runtime_config()["repository"]["gitlab"]

        # 1) URL
        gitlab_url = (
            values.get("gitlab_url")
            or cfg.get("url")
            or os.getenv("GITLAB_URL", "https://gitlab.com")
        )

        # 2) Repository (must exist in some source)
        gitlab_repo = (
            values.get("gitlab_repository")
            or cfg.get("gitlab_repository")
            or os.getenv("GITLAB_REPOSITORY")
        )
        if not gitlab_repo:
            raise ValueError(
                "GitLab repository must be provided via CLI, config.yaml or GITLAB_REPOSITORY."
            )

        # 3) Token (must exist in some source)
        token = (
            values.get("gitlab_personal_access_token")
            or cfg.get("private_token")
            or os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN")
        )
        if not token:
            raise ValueError(
                "GitLab Personal Access Token must be provided via CLI, config.yaml or GITLAB_PERSONAL_ACCESS_TOKEN."
            )

        # 4) Branches w/ defaults
        branch = (
            values.get("gitlab_branch")
            or cfg.get("branch")
            or cfg.get("base_branch")
            or os.getenv("GITLAB_BRANCH", "main")
        )
        base_branch = (
            values.get("gitlab_base_branch")
            or cfg.get("base_branch")
            or os.getenv("GITLAB_BASE_BRANCH", "main")
        )

        # Instantiate & authenticate the GitLab client
        gl = gitlab.Gitlab(url=gitlab_url, private_token=token, keep_base_url=True)
        gl.auth()

        # Populate the model’s values
        values.update(
            gitlab=gl,
            gitlab_repo_instance=gl.projects.get(gitlab_repo),
            gitlab_url=gitlab_url,
            gitlab_repository=gitlab_repo,
            gitlab_personal_access_token=token,
            gitlab_branch=branch,
            gitlab_base_branch=base_branch,
        )
        return values

    def create_file(
        self, branch_name: str, file_path: str, file_contents: str, commit_message: str
    ) -> bool:
        """
        Creates a new file on the gitlab repo
        Returns:
            str: A success or failure
        """
        try:
            self.gitlab_repo_instance.files.head(file_path, branch_name)
            return False
        except Exception:
            data = {
                "branch": branch_name,
                "commit_message": commit_message,
                "file_path": file_path,
                "content": file_contents,
            }

            self.gitlab_repo_instance.files.create(data)
            self.gitlab_repo_instance.save()

        return True

    def update_file(
        self, branch_name: str, file_path: str, file_contents: str, commit_message: str
    ):
        """Updates an existing file on the gitlab repo"""
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
            file = self.gitlab_repo_instance.files.get(
                file_path=file_path, ref=branch_name
            )
            file.content = file_contents
            file.save(branch=branch_name, commit_message=commit_message)
        except Exception as e:
            raise Exception(
                f"Failed to update file {file_path} in branch {branch_name}: {str(e)}"
            )

    def search_issues(self, title: str):
        """
        Search for issues in the project by title.
        Returns a list of issues whose title matches (case-insensitive).
        """
        issues = self.gitlab_repo_instance.issues.list(search=title, all=True)
        # Optionally filter by exact title match
        return [
            issue.attributes
            for issue in issues
            if issue.title.strip().lower() == title.strip().lower()
        ]

    def create_issue(self, title: str, description: str):
        """
        Create a new issue in the project.
        Returns the created issue object (as dict).
        """
        issue = self.gitlab_repo_instance.issues.create(
            {"title": title, "description": description}
        )
        return issue.attributes

    def update_issue(self, issue_iid: int, description: str):
        """
        Update the description/body of an issue.
        """
        issue = self.gitlab_repo_instance.issues.get(issue_iid)
        issue.description = description
        issue.save()
        return issue.attributes

    def get_pipeline_job(self, job_id: int) -> dict:
        """Gets the job information"""
        job = self.gitlab_repo_instance.jobs.get(job_id)

        # Get the job logs
        job_log = job.trace()

        # Parse the log to extract warnings and errors
        parsed_log = parse_job_log(job_log.decode("utf-8"), job.status)
        num_warnings = len(parsed_log["warnings"])
        num_errors = len(parsed_log["errors"])

        # Prepare job details
        job_detail = {
            "id": job.id,
            "name": job.name,
            "status": job.status,
            "stage": job.stage,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "duration": job.duration,
            "web_url": job.web_url,
            "warnings_count": num_warnings,
            "errors_count": num_errors,
        }

        # Include sample of warnings and errors if any
        if num_warnings > 0:
            job_detail["warnings_sample"] = parsed_log["warnings"][:5]
        if num_errors > 0:
            job_detail["errors_sample"] = parsed_log["errors"][:5]

        return job_detail

    def get_pipeline_details(self, pipeline_id: int) -> str:
        """
        Retrieves detailed, human-readable pipeline info, including job logs and summaries.

        Parameters:
            pipeline_id (int): The ID of the pipeline.

        Returns:
            str: Formatted multi-line string with pipeline and job summary.
        """
        try:
            pipeline = self.gitlab_repo_instance.pipelines.get(pipeline_id)

            # Basic pipeline info
            info = [
                "## Pipeline Information:",
                f"  Pipeline ID : {pipeline.id}",
                f"  Status      : {pipeline.status}",
                f"  Ref         : {pipeline.ref}",
                f"  Created At  : {pipeline.created_at}",
                f"  Updated At  : {pipeline.updated_at}",
                f"  Web URL     : {pipeline.web_url}",
            ]

            # Fetch jobs and analyze
            jobs = pipeline.jobs.list(get_all=True)
            total_warnings = 0
            total_errors = 0
            job_lines = ["  Jobs:"]
            for job in jobs:
                job_detail = self.get_pipeline_job(job.id)
                total_warnings += job_detail["warnings_count"]
                total_errors += job_detail["errors_count"]
                job_lines.append(json.dumps(job_detail, indent=2, default=str))

            info.extend(
                [
                    f"  Total Jobs      : {len(jobs)}",
                    f"  Total Warnings  : {total_warnings}",
                    f"  Total Errors    : {total_errors}",
                ]
            )
            info.extend(job_lines)

            return "\n".join(info)

        except Exception as e:
            return f"Failed to retrieve pipeline details for Pipeline ID {pipeline_id}: {str(e)}"

    def get_merge_request(self, mr_iid: int) -> str:
        """
        Retrieves comprehensive details of a merge request, including diffs and statistics.

        Parameters:
            mr_iid (int): The internal ID (iid) of the merge request.

        Returns:
            Dict[str, Any]: A dictionary containing detailed MR information.
        """
        try:
            # Fetch the merge request
            mr = self.gitlab_repo_instance.mergerequests.get(mr_iid)

            # Fetch author details
            author = mr.author
            author_details = {
                "id": author["id"],
                "username": author["username"],
                "name": author["name"],
            }

            # Fetch assignee details
            assignees_details = []
            for assignee in mr.assignees:
                assignees_details.append(
                    {
                        "id": assignee["id"],
                        "username": assignee["username"],
                        "name": assignee["name"],
                    }
                )

            # Fetch MR changes/diffs
            changes = []
            total_lines_added = 0
            total_lines_removed = 0

            mr_changes = mr.changes(unidiff=True, access_raw_diffs=True)
            for change in mr_changes["changes"]:
                # Calculate lines added and removed from the diff content
                lines_added, lines_removed = parse_diff_content(change.get("diff", ""))
                total_lines_added += lines_added
                total_lines_removed += lines_removed

                changes.append(
                    {
                        "old_path": change.get("old_path"),
                        "new_path": change.get("new_path"),
                        "a_mode": change.get("a_mode"),
                        "b_mode": change.get("b_mode"),
                        "new_file": change.get("new_file", False),
                        "renamed_file": change.get("renamed_file", False),
                        "deleted_file": change.get("deleted_file", False),
                        "generated_file": change.get("generated_file", False),
                        "diff": change.get("diff"),
                        "lines_added": lines_added,
                        "lines_removed": lines_removed,
                    }
                )

            # Calculate statistics
            stats = {
                "total_files_changed": len(changes),
                "total_lines_added": total_lines_added,
                "total_lines_removed": total_lines_removed,
            }

            # Get approvals
            approvals = mr.approvals.get()

            # # MR Discussions
            # discussion_notes = []

            # discussions = mr.discussions.list(all=True)
            # for discussion in discussions:
            #     discussion_id = discussion.attributes.get("id")
            #     notes = discussion.attributes.get("notes")
            #     for note in notes:
            #         data = {"discussion_id": discussion_id, "note": note}
            #         discussion_notes.append(data)

            # --- Pipeline info (and detailed pipeline if present) ---
            pipeline_details = (
                self.get_pipeline_details(mr.head_pipeline["id"])
                if mr.head_pipeline and mr.head_pipeline.get("id")
                else None
            )

            # Compile the final MR details
            mr_details = {
                "mr": {
                    # "id": mr.id,
                    "iid": mr.iid,
                    "project_id": mr.project_id,
                    "title": mr.title,
                    "description": mr.description,
                    "state": mr.state,
                    "created_at": mr.created_at,
                    "updated_at": mr.updated_at,
                    "author": author_details,
                    "assignees": assignees_details,
                    "source_branch": mr.source_branch,
                    "target_branch": mr.target_branch,
                    "labels": mr.labels,
                    "web_url": mr.web_url,
                    "merge_status": mr.detailed_merge_status,
                    "first_contribution": mr.first_contribution,
                    "approvals_required": approvals.approvals_required,
                    "approvals_received": len(approvals.approved_by),
                    # "approvals_received": mr.approvals_received,
                    # "discussion_unresolved_count": mr.discussion_unresolved_count,
                },
                "pipeline": pipeline_details,
                "changes": changes,
                "stats": stats,
            }

            return pretty_print_merge_request(mr_details)

        except Exception as e:
            return {
                "error": f"Failed to retrieve merge request details for MR IID {mr_iid}: {str(e)}"
            }

    def post_merge_request_comment(self, mr_iid: int, comment: str) -> str:
        """
        Posts a comment to a merge request.

        Parameters:
            mr_iid (int): The internal ID (iid) of the merge request.
            comment (str): The comment text to post.

        Returns:
            str: Success or failure message.
        """
        try:
            mr = self.gitlab_repo_instance.mergerequests.get(mr_iid)
            note = mr.notes.create({"body": comment.strip()})
            note_url = f"{mr.web_url}#note_{note.id}"
            return f"Comment posted at {note_url}"
        except Exception as e:
            return f"Failed to post comment to Merge Request {mr_iid}: {str(e)}"

    def post_merge_request_thread_comment(
        self, mr_iid: int, note_id: int, comment: str
    ) -> str:
        """
        Posts a reply to an existing comment thread in a merge request.

        Parameters:
            mr_iid (int): The internal ID (iid) of the merge request.
            note_id (int): The ID of the note (comment) to reply to.
            comment (str): The reply comment text.

        Returns:
            str: Success or failure message.
        """
        try:
            mr = self.gitlab_repo_instance.mergerequests.get(mr_iid)
            note = mr.notes.get(note_id)
            note.notes.create({"body": comment})
            return f"Successfully posted reply to comment {note_id} in Merge Request {mr_iid}."
        except Exception as e:
            return f"Failed to post reply to comment {note_id} in Merge Request {mr_iid}: {str(e)}"

    def get_merge_request_comments(self, mr_iid: int) -> List[Dict[str, Any]]:
        """
        Retrieves all comments for a specific merge request.

        Parameters:
            mr_iid (int): The internal ID (iid) of the merge request.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing comment details.
        """
        try:
            mr = self.gitlab_repo_instance.mergerequests.get(mr_iid)
            notes = mr.notes.list(all=True)
            comments = []
            for note in notes:
                comments.append(
                    {
                        "id": note.id,
                        "body": note.body,
                        "author": note.author["username"],
                        "created_at": note.created_at,
                        "updated_at": note.updated_at,
                    }
                )
            return comments
        except Exception as e:
            return [
                {
                    "error": f"Failed to get comments for Merge Request {mr_iid}: {str(e)}"
                }
            ]

    def approve_merge_request(self, mr_iid: int) -> str:
        """
        Approves a merge request.

        Parameters:
            mr_iid (int): The internal ID (iid) of the merge request.

        Returns:
            str: Success or failure message.
        """
        try:
            # Retrieve the merge request
            mr = self.gitlab_repo_instance.mergerequests.get(mr_iid)
            # Approve the merge request
            mr.approve()
            return f"Successfully approved Merge Request {mr_iid}."
        except Exception as e:
            return f"Failed to approve Merge Request {mr_iid}: {str(e)}"

    def run(self, mode: str, query: str = "", body: dict = {}) -> str:
        # Parent class handling

        if mode == "get_merge_request":
            try:
                mr_iid = int(query.strip())
                mr_details = self.get_merge_request(mr_iid)
                return mr_details
            except ValueError:
                return "Invalid input. Please provide the Merge Request number as an integer."
        elif mode == "post_merge_request_comment":
            try:
                return self.post_merge_request_comment(**body)
            except ValueError:
                return "Invalid input format. Expected:\n<mr_iid>\n\n<comment>"
        elif mode == "approve_merge_request":
            try:
                return self.approve_merge_request(**body)
            except ValueError:
                return "Invalid input format."
        elif mode == "get_pipeline_details":
            try:
                pipeline_id = int(query.strip())
                pipeline_details = self.get_pipeline_details(pipeline_id)
                return pipeline_details
            except ValueError:
                return "Invalid input. Please provide the Pipeline ID as an integer."
        elif mode == "post_merge_request_thread_comment":
            try:
                parts = query.split("\n\n", 2)
                if len(parts) != 3:
                    raise ValueError
                mr_iid = int(parts[0].strip())
                note_id = int(parts[1].strip())
                comment = parts[2].strip()
                return self.post_merge_request_thread_comment(mr_iid, note_id, comment)
            except ValueError:
                return "Invalid input format. Expected:\n<mr_iid>\n\n<note_id>\n\n<comment>"
        elif mode == "get_merge_request_comments":
            try:
                mr_iid = int(query.strip())
                comments = self.get_merge_request_comments(mr_iid)
                return json.dumps(comments, indent=2)
            except ValueError:
                return "Invalid input. Please provide the Merge Request number as an integer."
        else:
            raise ValueError(f"Invalid mode: {mode}")
