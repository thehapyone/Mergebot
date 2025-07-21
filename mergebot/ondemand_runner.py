import asyncio
import time

from mergebot.dashboard.dashboard_manager import GitLabDashboardManager
from mergebot.flow import run_flow
from mergebot.tools.gitlab.api_wrapper import GitlabAPIWrapper
from mergebot.utils import get_platform_type
from mergebot.validator.config import get_runtime_config
from mergebot.validator.logging_config import logger


def skip_draft_mr(mr, draft_mrs_enabled: bool) -> bool:
    """
    Determines whether a merge request (MR) should be skipped based on its draft or work-in-progress (WIP) status and configuration.

    The function checks:
    1. If the MR is considered a draft or WIP, determined by either:
        - The MR having the attribute 'work_in_progress' or 'draft' set to True, OR
        - The MR's title starting with "wip" or "draft" (case-insensitive).
    2. The 'draft_mrs_enabled' flag, which, if True, means draft/WIP MRs should NOT be skipped (i.e., return False).
    Args:
        mr: Merge request object. Should have a 'title' attribute and optionally 'work_in_progress' or 'draft'.
        draft_mrs_enabled (bool): If True, draft/WIP MRs will NOT be skipped.

    Returns:
        bool: True if the MR is to be skipped (i.e., it is a draft/WIP and draft MRs are NOT enabled); False otherwise.
    """

    def is_draft_mr(mr):
        # Prefer explicit attributes: work_in_progress or draft
        if getattr(mr, "work_in_progress", False) or getattr(mr, "draft", False):
            return True
        title = mr.title.strip().lower()
        return title.startswith("wip") or title.startswith("draft")

    return is_draft_mr(mr) and not draft_mrs_enabled


class OndemandRunner:
    def __init__(self, project: str, workers: int = 4):
        """
        OndemandRunner manages the dashboard update process for MergeBot,
        supporting parallel analysis of multiple merge requests.

        Args:
            project (str): The GitLab project/repository path.
            workers (int): Number of parallel workers for MR analysis.
        """
        self.platform_type = get_platform_type()
        self.project = project
        self.workers = workers
        if self.platform_type == "gitlab":
            self.api = GitlabAPIWrapper()
            self.project_id = self.api.gitlab_repo_instance.id
            self.dashboard_manager = GitLabDashboardManager(self.api, self.project_id)
        else:
            raise NotImplementedError(
                f"Platform '{self.platform_type}' is not yet supported in ondemand mode."
            )

    async def run_once(self):
        """
        Runs a single dashboard scan and update, analyzing all relevant merge requests in parallel.
        """
        logger.info("[Ondemand] Running dashboard scan and update (one-shot)")
        dashboard = self.dashboard_manager.get_or_create_dashboard()
        open_mrs = self.api.gitlab_repo_instance.mergerequests.list(
            state="opened", all=True
        )
        open_mr_iids = {str(mr.iid): mr for mr in open_mrs}

        # Parse Dashboard
        dashboard_data = self.dashboard_manager.parse_dashboard(dashboard["body"])
        rerun_requests = set(dashboard_data["rerun_requests"])
        tracked_mrs = set(dashboard_data["tracked_mrs"])

        # Get runtime config, which may include overrides for this run
        config = get_runtime_config(as_pydantic=True)
        draft_mrs_enabled = config.analysis.draft_mrs if config.analysis else False

        mrs_to_analyze = [
            mr
            for mr_iid, mr in open_mr_iids.items()
            if (mr_iid not in tracked_mrs or mr_iid in rerun_requests)
            and not skip_draft_mr(mr, draft_mrs_enabled)
        ]

        # Apply max_mrs limit from config if set
        max_mrs = config.analysis.max_mrs if config.analysis else None

        if max_mrs and len(mrs_to_analyze) > max_mrs:
            logger.info(
                f"[Ondemand] Limiting analysis to {max_mrs} MRs (out of {len(mrs_to_analyze)} total)."
            )
            mrs_to_analyze = mrs_to_analyze[:max_mrs]

        logger.info(f"[Ondemand] MRs to analyze: {[mr.iid for mr in mrs_to_analyze]}")
        analysis_results = []
        analysis_durations = []
        errors = []
        analyzed_iids = set()

        async def analyze_mr(mr, semaphore):
            async with semaphore:
                logger.info(f"[Ondemand] Analyzing MR !{mr.iid} ({mr.title})")
                start = time.time()
                try:
                    analysis_result = await run_flow(
                        mr.web_url,
                        mr_iid=mr.iid,
                        mr_title=mr.title,
                        project=self.project,
                    )
                    result = {
                        "iid": analysis_result.iid,
                        "title": analysis_result.title,
                        "status": "Analyzed",
                        "impact_score": analysis_result.impact_score,
                        "recommendation": analysis_result.recommendation,
                        "last_reviewed": analysis_result.last_reviewed,
                        "analysis_link": analysis_result.analysis_link,
                        "web_url": mr.web_url,
                        "duration": time.time() - start,
                        "error": None,
                    }
                    return (mr.iid, result)
                except Exception as e:
                    error_msg = f"{type(e).__name__}: {e}"
                    logger.error(
                        f"[Ondemand] Error while analyzing MR !{mr.iid}: {error_msg}",
                        exc_info=True,
                    )
                    result = {
                        "iid": mr.iid,
                        "title": mr.title,
                        "status": "Error",
                        "impact_score": "N/A",
                        "recommendation": "",
                        "last_reviewed": "N/A",
                        "analysis_link": "#",
                        "web_url": mr.web_url,
                        "duration": time.time() - start,
                        "error": error_msg,
                    }
                    return (mr.iid, result)

        semaphore = asyncio.Semaphore(self.workers)
        tasks = [analyze_mr(mr, semaphore) for mr in mrs_to_analyze]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for mr_iid, result in results:
            if result["error"] is None:
                analysis_results.append(
                    {k: result[k] for k in result if k != "duration" and k != "error"}
                )
                analyzed_iids.add(mr_iid)
            else:
                errors.append((mr_iid, result["error"]))
                analysis_results.append(
                    {k: result[k] for k in result if k != "duration"}
                )

            analysis_durations.append(result["duration"])

        # For MRs not analyzed in this run, preserve previous dashboard data
        # TODO: Previous data should be fetched from the dashboard
        #       instead of assuming it is in the dashboard_data.
        #       Analysis link is not shown for example
        for mr in open_mrs:
            if mr.iid not in analyzed_iids:
                analysis_results.append(
                    {
                        "iid": mr.iid,
                        "title": mr.title,
                        "status": "Tracked",
                        "impact_score": "N/A",
                        "recommendation": "",
                        "last_reviewed": "N/A",
                        "analysis_link": "#",
                        "web_url": mr.web_url,
                    }
                )

        # Compute analytics summary metrics, accumulating with previous values
        prev_analytics = dashboard_data["analytics"]
        mrs_processed = prev_analytics.get("MRs Processed", 0) + len(mrs_to_analyze)

        # Count recommendations from analysis_results and accumulate with previous analytics
        prev_auto_approve = prev_analytics.get("Auto Approve", 0)
        prev_manual_review = prev_analytics.get("Manual Reviews", 0)
        auto_approve_count = prev_auto_approve
        manual_review_count = prev_manual_review
        for mr in analysis_results:
            rec = (mr.get("recommendation") or "").strip().lower()
            if "auto-approve" in rec:
                auto_approve_count += 1
            elif "human review" in rec:
                manual_review_count += 1

        # For average, keep a running sum
        prev_avg = prev_analytics.get("Avg. Time Open→Merge", "N/A")
        if analysis_durations:
            avg_seconds = sum(analysis_durations) / len(analysis_durations)
            avg_time = f"{int(avg_seconds // 60)}h {int(avg_seconds % 60)}m"
        else:
            avg_time = prev_avg if prev_avg != "N/A" else "N/A"

        analytics_summary = {
            "MRs Processed": mrs_processed,
            "Auto Approve": auto_approve_count,
            "Manual Reviews": manual_review_count,
            "Avg. Time Open→Merge": avg_time,
        }

        # Only reset rerun_requests for processed MRs
        remaining_rerun_requests = [
            iid
            for iid in rerun_requests
            if iid not in [str(mr.iid) for mr in mrs_to_analyze]
        ]

        self.dashboard_manager.update_dashboard(
            mr_data=analysis_results,
            rerun_requests=remaining_rerun_requests,
            action_log=[f"Analyzed MR !{mr.iid}" for mr in mrs_to_analyze]
            + [f"Error in MR !{iid}: {err}" for iid, err in errors],
            analytics=analytics_summary,
        )
        logger.info("[Ondemand] Dashboard update complete")

    async def run_periodic(self, interval: int):
        """
        Runs dashboard scans and updates periodically at the specified interval.
        """
        logger.info(f"[Ondemand] Running dashboard scan every {interval} seconds")
        while True:
            await self.run_once()
            await asyncio.sleep(interval)
