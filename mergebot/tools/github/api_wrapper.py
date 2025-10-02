import json
import os
import re
import time
from datetime import datetime

import jwt
import requests
from github import Github

from mergebot.tools.api_base import PullRequestAPIBase
from mergebot.validator.config import get_runtime_config
from mergebot.validator.logging_config import logger


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

    def _gh_headers(self):
        """
        Returns the correct headers for authenticating GitHub API REST calls using either PAT or App token.
        """
        token = self.github_app_access_token or self.github_personal_access_token
        return {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        }

    def _owner_repo(self):
        """
        Returns (owner, repo) tuple from self.github_repository (format: 'owner/repo').
        """
        try:
            owner, repo = self.github_repository.split("/", 1)
            return owner, repo
        except Exception:
            raise ValueError("github_repository must be in 'owner/repo' format.")

    def _find_run_id_for_pr(self, pr) -> int | None:
        """
        Try to find the Actions workflow run_id for the PR's head commit SHA. Fallback to PR/branch search.
        """
        import requests

        owner, repo = self._owner_repo()
        headers = self._gh_headers()
        # Try: Use head_sha directly (most accurate, quickest)
        url = f"{self.github_api_url}/repos/{owner}/{repo}/actions/runs"
        params = {"head_sha": pr.head.sha, "per_page": 2}
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code == 200:
            runs = resp.json().get("workflow_runs", [])
            if runs:
                return runs[0].get("id")
        # Fallback: search for PR-number-linked runs by branch & pull_request event
        url = f"{self.github_api_url}/repos/{owner}/{repo}/actions/runs"
        params = {"event": "pull_request", "branch": pr.head.ref, "per_page": 20}
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code == 200:
            for run in resp.json().get("workflow_runs", []):
                if any(
                    (pr.number == pr_obj.get("number"))
                    for pr_obj in run.get("pull_requests", [])
                ):
                    return run.get("id")
        return None

    def get_pipeline_details(self, pipeline_id: int) -> str:
        """
        Retrieves and summarizes a GitHub Actions workflow run, including filtered logs for failed steps.
        """
        try:
            run = self.github_repo_instance.get_workflow_run(pipeline_id)
            run_data = run.raw_data
        except Exception as e:
            return f"Failed to retrieve pipeline details for Pipeline ID {pipeline_id} via PyGithub: {e}"

        jobs = self._fetch_action_jobs(pipeline_id)
        job_lines = ["  Jobs:"]
        total_warnings = 0
        total_errors = 0

        for job in jobs:
            job_info = self._summarize_job(job)
            job_lines.append(json.dumps(job_info, indent=2, default=str))
            total_warnings += job_info.get("warnings_count", 0)
            total_errors += job_info.get("errors_count", 0)

        info = [
            "## Pipeline Information:",
            f"  Pipeline ID : {run_data.get('id')}",
            f"  Status      : {run_data.get('status')}",
            f"  Conclusion  : {run_data.get('conclusion')}",
            f"  Ref         : {run_data.get('head_branch')}",
            f"  Head SHA    : {run_data.get('head_sha')}",
            f"  Created At  : {run_data.get('created_at')}",
            f"  Updated At  : {run_data.get('updated_at')}",
            f"  Web URL     : {run_data.get('html_url')}",
            f"  Total Jobs      : {len(jobs)}",
            f"  Total Warnings  : {total_warnings}",
            f"  Total Errors    : {total_errors}",
        ]
        info.extend(job_lines)
        return "\n".join(info)

    def _fetch_action_jobs(self, pipeline_id: int):
        """Fetch job metadata for a workflow run via REST (PyGithub lacks support)."""
        owner, repo = self._owner_repo()
        headers = self._gh_headers()
        job_url = f"{self.github_api_url}/repos/{owner}/{repo}/actions/runs/{pipeline_id}/jobs?per_page=100"
        resp = requests.get(job_url, headers=headers)
        if resp.status_code == 200:
            return resp.json().get("jobs", [])
        return []

    def _summarize_job(self, job: dict) -> dict:
        job_errors = sum(
            1
            for s in job.get("steps", []) or []
            if (s.get("conclusion") or "").lower()
            in {"failure", "timed_out", "cancelled", "action_required"}
        )
        job_entry = {
            "id": job.get("id"),
            "name": job.get("name"),
            "status": job.get("status"),
            "conclusion": job.get("conclusion"),
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
            "html_url": job.get("html_url"),
            "errors_count": job_errors,
            "warnings_count": 0,  # Not yet available; can implement parsing in future
        }
        # Fetch error log snippet if there's a failure
        if job_errors > 0:
            job_entry.update(self._extract_failed_step_log(job))
        return job_entry

    def _extract_failed_step_log(self, job: dict) -> dict:
        """Extract step-level log snippet for failed jobs using started/completed time window."""
        job_id = job.get("id")
        if not job_id:
            return {}
        log_url = f"{self.github_api_url}/repos/{self._owner_repo()[0]}/{self._owner_repo()[1]}/actions/jobs/{job_id}/logs"
        log_resp = requests.get(
            log_url, headers=self._gh_headers(), allow_redirects=True
        )
        if log_resp.status_code != 200:
            return {"log_tail": f"[Failed to retrieve job log: {log_resp.status_code}]"}

        log_lines = [line for line in log_resp.text.splitlines() if line.strip()]

        step_failure_states = {"failure", "timed_out", "cancelled", "action_required"}
        step = None
        for s in reversed(job.get("steps", []) or []):
            if (s.get("conclusion") or "").lower() in step_failure_states:
                step = s
                break
        if step and step.get("started_at") and step.get("completed_at"):
            started = self._parse_iso_time(step["started_at"])
            ended = self._parse_iso_time(step["completed_at"])
            if started and ended:
                timestamp_re = re.compile(
                    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)Z"
                )
                snippet = []
                for line in log_lines:
                    m = timestamp_re.match(line)
                    if m:
                        t = self._parse_iso_time(m.group(1))
                        if t and started <= t <= ended:
                            snippet.append(line)
                if snippet:
                    return {
                        "log_tail": "\n".join(snippet[-30:]),
                        "failed_step": {
                            "name": step.get("name"),
                            "started_at": step["started_at"],
                            "completed_at": step["completed_at"],
                        },
                    }
        # fallback - last 30 lines stripping group markers
        tail_lines = [
            line
            for line in log_lines
            if line
            and not line.startswith("##[group]")
            and not line.startswith("##[endgroup]")
        ][-30:]
        return {"log_tail": "\n".join(tail_lines)}

    @staticmethod
    def _parse_iso_time(timestr: str):
        """Parse ISO string with/without microseconds (truncates excess), returns UTC naive datetime."""
        s = timestr.rstrip("Z")
        if "." in s:
            base, frac = s.split(".", 1)
            frac = (frac + "000000")[:6]
            clean = f"{base}.{frac}"
            try:
                return datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S.%f")
            except Exception:
                return None
        else:
            try:
                return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
            except Exception:
                return None

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
            # Try to find relevant Actions run and include pipeline summary
            run_id = self._find_run_id_for_pr(pr)
            if run_id:
                pr_details["pipeline"] = self.get_pipeline_details(run_id)
            else:
                pr_details["pipeline"] = ""
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

    def _evaluate_ci_state(self, pr):
        """
        Evaluate CI state for PR head commit using the Checks APIs.
        Returns tuple: (ci_passed, ci_state)
        ci_state is one of: 'success' | 'failure' | 'pending' | 'unknown'
        """
        try:
            head_sha = pr.head.sha

            # Prefer the PR head repo to avoid 404 on fork PRs
            head_repo = getattr(pr.head, "repo", None)
            repo_for_commit = (
                head_repo if head_repo is not None else self.github_repo_instance
            )
            commit = repo_for_commit.get_commit(head_sha)

            # Prefer aggregating by check runs (more precise than suites)
            checks_state = None
            try:
                runs = list(commit.get_check_runs())
                if runs:
                    failure_conclusions = {
                        "failure",
                        "cancelled",
                        "timed_out",
                        "action_required",
                    }
                    successish_conclusions = {"success", "neutral", "skipped"}

                    # Any explicit failure from completed runs wins
                    any_failure = any(
                        (getattr(r, "conclusion", "") or "").lower()
                        in failure_conclusions
                        for r in runs
                    )
                    if any_failure:
                        return False, "failure"

                    # Only mark pending if any runs are actually queued or in-progress
                    any_in_progress = any(
                        (getattr(r, "status", "") or "").lower()
                        in {"queued", "in_progress", "waiting"}
                        for r in runs
                    )

                    if any_in_progress:
                        checks_state = "pending"
                    else:
                        # All runs are completed; if they are success/neutral/skipped => success
                        completed_conclusions = [
                            (getattr(r, "conclusion", "") or "").lower() for r in runs
                        ]
                        if completed_conclusions and all(
                            c in successish_conclusions or c == ""
                            for c in completed_conclusions
                        ):
                            checks_state = "success"
            except Exception as e:
                logger.warning(f"Checks API (runs) query failed for {head_sha}: {e}")

            # Fallback to legacy combined statuses if runs didn't yield a state
            if not checks_state:
                try:
                    combined = commit.get_combined_status()
                    statuses_state = (
                        combined.state or ""
                    ).lower()  # success | failure | pending
                    if statuses_state == "failure":
                        return False, "failure"
                    if statuses_state == "pending":
                        return False, "pending"
                    if statuses_state == "success":
                        return True, "success"
                except Exception as e:
                    logger.warning(f"Combined status query failed for {head_sha}: {e}")

            # Decide final CI state from checks_state (failure > pending > success)
            if checks_state == "failure":
                return False, "failure"
            if checks_state == "pending":
                return False, "pending"
            if checks_state == "success":
                return True, "success"
            return None, "unknown"
        except Exception as e:
            logger.error(
                f"CI status evaluation failed for PR #{getattr(pr, 'number', '?')} sha {getattr(getattr(pr, 'head', None), 'sha', '?')}: {e}"
            )
            return None, "unknown"

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

            # Compute effective review summary by latest review per reviewer
            reviews = list(pr.get_reviews())
            latest_by_reviewer = {}

            for r in reviews:
                user = getattr(r, "user", None)
                if not user:
                    continue
                # exclude self-approval
                if user.login == pr.user.login:
                    continue

                key = user.login
                prev = latest_by_reviewer.get(key)
                # Prefer the most recent submitted_at (fallback to updated_at)
                curr_ts = getattr(r, "submitted_at", None) or getattr(
                    r, "updated_at", None
                )
                prev_ts = getattr(prev, "submitted_at", None) or getattr(
                    prev, "updated_at", None
                )
                if prev is None or (curr_ts and prev_ts and curr_ts > prev_ts):
                    latest_by_reviewer[key] = r

            # Reviews summary
            approved = sum(
                1
                for r in latest_by_reviewer.values()
                if (r.state or "").upper() == "APPROVED"
            )
            changes_requested = sum(
                1
                for r in latest_by_reviewer.values()
                if (r.state or "").upper() == "CHANGES_REQUESTED"
            )
            approval_state = approved > 0 and changes_requested == 0

            # CI state
            ci_passed, ci_state = self._evaluate_ci_state(pr)

            return {
                "state": pr.state,
                "draft": draft,
                "mergeable": bool(mergeable) if mergeable is not None else None,
                "ci_passed": ci_passed,
                "ci_state": ci_state,
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
