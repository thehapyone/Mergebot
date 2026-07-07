import json
import os
import re
from typing import Any

import gitlab

from mergebot.tools.api_base import PullRequestAPIBase, PullRequestDetails
from mergebot.validator.logging_config import logger
from mergebot.workspace.manager import PrRef


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


def parse_job_log(log: str, job_status: str) -> dict[str, Any]:
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


class GitlabAPIWrapper(PullRequestAPIBase):
    """
    GitLab API Wrapper.
    """

    config_section: str = "gitlab"

    def validate_gitlab(self):
        repo_cfg = self.config.repository.gitlab

        repo_url = repo_cfg.url if repo_cfg and getattr(repo_cfg, "url", None) else None
        token = (
            repo_cfg.private_token
            if repo_cfg and getattr(repo_cfg, "private_token", None)
            else None
        )
        base_branch = (
            repo_cfg.base_branch if repo_cfg and getattr(repo_cfg, "base_branch", None) else None
        )

        # 1) URL
        self.gitlab_url = (
            self.gitlab_url or repo_url or os.getenv("GITLAB_URL", "https://gitlab.com")
        )

        # 2) Repository (must exist in some source)
        self.gitlab_repository = (
            self.gitlab_repository or self.project_path or os.getenv("GITLAB_REPOSITORY")
        )
        if not self.gitlab_repository:
            raise ValueError(
                "GitLab repository must be provided via CLI, config.yaml or GITLAB_REPOSITORY."
            )

        # 3) Token (must exist in some source)
        self.gitlab_personal_access_token = (
            self.gitlab_personal_access_token or token or os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN")
        )
        if not self.gitlab_personal_access_token:
            raise ValueError(
                "GitLab Personal Access Token must be provided via CLI, config.yaml or GITLAB_PERSONAL_ACCESS_TOKEN."
            )

        # 4) Branches w/ defaults
        self.gitlab_branch = self.gitlab_branch or base_branch or os.getenv("GITLAB_BRANCH", "main")
        self.gitlab_base_branch = (
            self.gitlab_base_branch or base_branch or os.getenv("GITLAB_BASE_BRANCH", "main")
        )

        # Instantiate & authenticate the GitLab client
        self.gitlab = gitlab.Gitlab(
            url=self.gitlab_url,
            private_token=self.gitlab_personal_access_token,
            keep_base_url=True,
            timeout=60,
        )
        self.gitlab.auth()

        # Set the repository instance
        self.gitlab_repo_instance = self.gitlab.projects.get(self.gitlab_repository)

    def resolve_git_token(self) -> str | None:
        """Return the token usable for git HTTPS auth (the GitLab PAT)."""
        return self.gitlab_personal_access_token

    def _repo_size_kb(self) -> int | None:
        """Best-effort repository size in KB; needs Reporter+ for project statistics."""
        cached = getattr(self, "_cached_repo_size_kb", "unset")
        if cached != "unset":
            return cached
        size_kb = None
        try:
            project = self.gitlab.projects.get(self.gitlab_repository, statistics=True)
            repository_size = (project.statistics or {}).get("repository_size")
            if repository_size is not None:
                size_kb = int(repository_size) // 1024
        except Exception as e:
            logger.debug(f"Failed to resolve GitLab repository size: {e}")
        self._cached_repo_size_kb = size_kb
        return size_kb

    def _build_pr_ref(self, mr) -> PrRef | None:
        """Best-effort typed MR metadata for workspace provisioning (proposal 3.1)."""
        try:
            diff_refs = getattr(mr, "diff_refs", None) or {}
            return PrRef(
                clone_url=self.gitlab_repo_instance.http_url_to_repo,
                head_sha=mr.sha,
                base_sha=diff_refs.get("base_sha"),
                pr_number=mr.iid,
                fetch_ref=f"refs/merge-requests/{mr.iid}/head",
                repo_size_kb=self._repo_size_kb(),
            )
        except Exception as e:
            logger.warning(f"Failed to build PrRef for MR !{getattr(mr, 'iid', '?')}: {e}")
            return None

    def get_pull_request_with_ref(self, pr_number: int) -> PullRequestDetails | dict:
        try:
            # Fetch the merge request
            mr = self.gitlab_repo_instance.mergerequests.get(pr_number)

            # Fetch author details
            author = mr.author
            author_details = {
                "id": author["id"],
                "username": author["username"],
                "name": author["name"],
            }

            # Fetch assignee details
            assignees_details = [
                {
                    "id": assignee["id"],
                    "username": assignee["username"],
                    "name": assignee["name"],
                }
                for assignee in mr.assignees
            ]

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

            # --- Pipeline info (and detailed pipeline if present) ---
            pipeline_details = (
                self.get_pipeline_details(mr.head_pipeline["id"])
                if mr.head_pipeline and mr.head_pipeline.get("id")
                else ""
            )

            # Compile the final MR details

            mr_details = {
                "iid": mr.iid,
                "title": mr.title,
                "author": author_details["name"],
                "state": mr.state,
                "created_at": mr.created_at,
                "updated_at": mr.updated_at,
                "source_branch": mr.source_branch,
                "target_branch": mr.target_branch,
                "labels": mr.labels,
                "url": mr.web_url,
                "merge_status": mr.detailed_merge_status,
                "first_contribution": mr.first_contribution,
                "approvals_required": approvals.approvals_required,
                "approvals_received": len(approvals.approved_by),
                "assignees": assignees_details,
                "changes": changes,
                "stats": stats,
                "body": mr.description,
                "merged": mr.merged_at is not None,
                "is_draft": mr.work_in_progress,
                "mergeable": mr.merge_status,
                "mergeable_state": mr.detailed_merge_status,
                "number": mr.iid,
                "base": mr.target_branch,
                "head": mr.source_branch,
                "additions": total_lines_added,
                "deletions": total_lines_removed,
                "changed_files": len(changes),
                "pipeline": pipeline_details,
            }
            return PullRequestDetails(
                details=self.pretty_print_pull_request(mr_details),
                details_no_patch=self.pretty_print_pull_request(mr_details, include_patch=False),
                ref=self._build_pr_ref(mr),
            )
        except Exception as e:
            return {
                "error": f"Failed to retrieve merge request details for MR IID {pr_number}: {e!s}"
            }

    def comment_pull_request(self, pr_number: int, body: str) -> str:
        try:
            mr = self.gitlab_repo_instance.mergerequests.get(pr_number)
            note = mr.notes.create({"body": body.strip()})
            note_url = f"{mr.web_url}#note_{note.id}"
            return f"Comment posted at {note_url}"
        except Exception as e:
            return f"Failed to post comment to Merge Request {pr_number}: {e!s}"

    def approve_pull_request(self, pr_number: int) -> str:
        """
        Approves a Merge Request if not already approved by the authenticated user.
        Avoids re-approving to prevent GitLab errors.
        """
        try:
            mr = self.gitlab_repo_instance.mergerequests.get(pr_number)
            # Get approvals info
            approvals = mr.approvals.get()

            # Fetch authenticated user ID
            current_user = self.gitlab.user
            current_user_id = getattr(current_user, "id", None)
            # Check if already approved by this user
            already_approved = any(
                approver.get("user").get("id") == current_user_id
                for approver in getattr(approvals, "approved_by", [])
                if approver.get("user") and current_user_id is not None
            )
            if already_approved:
                return f"Merge Request {pr_number} is already approved by the current user (user_id={current_user_id}). No action taken."

            mr.approve()
            return f"Successfully approved Merge Request {pr_number}."
        except Exception as e:
            return f"Failed to approve Merge Request {pr_number}: {e!s}"

    def get_bot_identity(self) -> str:
        """Return the username of the authenticated GitLab service account."""
        cached = getattr(self, "_cached_bot_username", None)
        if cached:
            return cached
        username = ""
        try:
            user = getattr(self.gitlab, "user", None)
            if user:
                username = (getattr(user, "username", "") or "").strip()
        except Exception:
            username = ""
        self._cached_bot_username = username
        return username

    def _evaluate_ci_state(self, mr):
        """
        Evaluate CI state for MR head pipeline.
        Returns tuple: (ci_passed, ci_state)
        ci_state: 'success' | 'failure' | 'pending' | 'unknown'
        """
        try:
            hp = getattr(mr, "head_pipeline", None)
            status = ((hp or {}).get("status") or "").lower() if hp else ""
            if status == "success":
                return True, "success"
            if status in {"failed", "canceled"}:
                return False, "failure"
            if status in {"running", "pending", "created", "waiting_for_resource"}:
                return False, "pending"
            return None, "unknown"
        except Exception as e:
            logger.warning(f"CI state evaluation failed for MR !{getattr(mr, 'iid', '?')}: {e}")
            return None, "unknown"

    def get_pull_request_status(self, pr_number: int) -> dict:
        """
        Return structured MR status used for merge guardrails.
        """
        try:
            mr = self.gitlab_repo_instance.mergerequests.get(pr_number)

            # Draft/WIP
            draft = bool(getattr(mr, "work_in_progress", False))

            # Mergeable state (GitLab uses merge_status / detailed_merge_status)
            mergeable_flag = None
            try:
                status_val = (getattr(mr, "merge_status", "") or "").lower()
                detailed_val = (getattr(mr, "detailed_merge_status", "") or "").lower()
                if status_val:
                    mergeable_flag = status_val == "can_be_merged"
                elif detailed_val:
                    # Treat obviously mergeable states as True
                    mergeable_flag = detailed_val in {
                        "mergeable",
                        "can_be_merged",
                    }
            except Exception:
                mergeable_flag = None

            ci_passed, ci_state = self._evaluate_ci_state(mr)

            # Approvals
            approval_state = None
            approved_count = 0
            changes_requested = 0  # Best-effort; GitLab has no native "changes requested"
            try:
                approvals = mr.approvals.get()
                approved_count = len(getattr(approvals, "approved_by", []) or [])
                approvals_required = getattr(approvals, "approvals_required", 0) or 0
                approvals_left = getattr(approvals, "approvals_left", None)
                if approvals_left is not None:
                    approval_state = approvals_left == 0
                else:
                    approval_state = approved_count >= approvals_required
            except Exception:
                approval_state = None

            # Attempt to infer "changes requested" via unresolved discussions (best-effort)
            try:
                discussions = mr.discussions.list(all=True)
                for d in discussions:
                    # discussion objects may expose .resolved or via attributes
                    resolved = getattr(d, "resolved", None)
                    if resolved is None:
                        resolved = bool(d.attributes.get("resolved", True))
                    if resolved is False:
                        changes_requested += 1
            except Exception:
                # If not accessible, leave as 0 (unknown -> treated as no explicit blocks)
                pass

            return {
                "state": mr.state,
                "draft": draft,
                "mergeable": mergeable_flag,
                "ci_passed": ci_passed,
                "ci_state": ci_state,
                "approval_state": approval_state,
                "source_branch": getattr(mr, "source_branch", None),
                "target_branch": getattr(mr, "target_branch", None),
                "reviews": {
                    "changes_requested": changes_requested,
                    "approved": approved_count,
                },
            }
        except Exception as e:
            return {
                "error": f"Failed to retrieve merge request status for MR IID {pr_number}: {e!s}"
            }

    def merge_pull_request(self, pr_number: int, strategy: str = "repo_default") -> str:
        """
        Merge the merge request using the preferred strategy.
        strategy: repo_default | merge | squash | rebase (GitLab supports squash option; rebase maps to default merge)
        """
        try:
            mr = self.gitlab_repo_instance.mergerequests.get(pr_number)
            if strategy == "squash":
                mr.merge(squash=True)
            else:
                # repo_default, merge, rebase -> perform default merge
                mr.merge()
            return f"Merged Merge Request !{pr_number}: {mr.web_url}"
        except Exception as e:
            return f"Failed to merge Merge Request {pr_number}: {e!s}"

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
            return f"Failed to retrieve pipeline details for Pipeline ID {pipeline_id}: {e!s}"

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
            file = self.gitlab_repo_instance.files.get(file_path=file_path, ref=branch_name)
            file.content = file_contents
            file.save(branch=branch_name, commit_message=commit_message)
        except Exception as e:
            raise Exception(
                f"Failed to update file {file_path} in branch {branch_name}: {e!s}"
            ) from e
