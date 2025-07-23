import asyncio
import time

from mergebot.dashboard.dashboard_manager import DashboardManager
from mergebot.flow import run_flow
from mergebot.utils import get_platform_type
from mergebot.validator.config import get_runtime_config
from mergebot.validator.logging_config import logger


def skip_draft_pr(pr, draft_prs_enabled: bool) -> bool:
    """
    Determines whether a pull request (PR) or merge request (MR) should be skipped based on its draft or work-in-progress (WIP) status and configuration.

    The function checks:
    1. If the PR/MR is considered a draft or WIP, determined by either:
        - The PR/MR having the attribute 'work_in_progress' or 'draft' set to True, OR
        - The PR/MR's title starting with "wip" or "draft" (case-insensitive).
    2. The 'draft_prs_enabled' flag, which, if True, means draft/WIP PRs/MRs should NOT be skipped (i.e., return False).
    Args:
        pr: Pull request or merge request object. Should have a 'title' attribute and optionally 'work_in_progress' or 'draft'.
        draft_prs_enabled (bool): If True, draft/WIP PRs/MRs will NOT be skipped.

    Returns:
        bool: True if the PR/MR is to be skipped (i.e., it is a draft/WIP and draft PRs/MRs are NOT enabled); False otherwise.
    """

    def is_draft_pr(pr):
        # Prefer explicit attributes: work_in_progress or draft
        if getattr(pr, "work_in_progress", False) or getattr(pr, "draft", False):
            return True
        title = pr.title.strip().lower()
        return title.startswith("wip") or title.startswith("draft")

    should_skip = is_draft_pr(pr) and not draft_prs_enabled
    if should_skip:
        pr_id = getattr(pr, "iid", "<unknown>")
        pr_title = getattr(pr, "title", "<no title>")
        logger.info(
            f"[Ondemand] Skipping draft PR/MR !{pr_id} ({pr_title}) because draft PRs/MRs are not enabled"
        )
    return should_skip


class OndemandRunner:
    def __init__(self, project: str, workers: int = 4):
        """
        OndemandRunner manages the dashboard update process for MergeBot,
        supporting parallel analysis of multiple pull or merge requests.

        Args:
            project (str): The GitLab project/repository path.
            workers (int): Number of parallel workers for PR/MR analysis.
        """
        self.platform_type = get_platform_type()
        self.project = project
        self.workers = workers
        self.dashboard_manager = DashboardManager(self.platform_type)
        self.pr_id_attr = "iid" if self.platform_type == "gitlab" else "number"

    async def run_once(self):
        """
        Runs a single dashboard scan and update, analyzing all relevant pull or merge requests in parallel.
        """
        logger.info("[Ondemand] Running dashboard scan and update (one-shot)")
        dashboard = self.dashboard_manager.get_or_create_dashboard()
        open_prs, open_pr_iids = self.dashboard_manager.get_open_prs()

        # Parse Dashboard
        dashboard_data = self.dashboard_manager.parse_dashboard(dashboard["body"])
        rerun_requests = set(dashboard_data["rerun_requests"])
        tracked_prs = set(dashboard_data["tracked_prs"])

        # Get runtime config, which may include overrides for this run
        config = get_runtime_config(as_pydantic=True)
        draft_prs_enabled = config.analysis.draft_mrs if config.analysis else False

        prs_to_analyze = [
            pr
            for pr_iid, pr in open_pr_iids.items()
            if (pr_iid not in tracked_prs or pr_iid in rerun_requests)
            and not skip_draft_pr(pr, draft_prs_enabled)
        ]

        # Apply max_prs limit from config if set
        max_prs = config.analysis.max_mrs if config.analysis else None

        if max_prs and len(prs_to_analyze) > max_prs:
            logger.info(
                f"[Ondemand] Limiting analysis to {max_prs} PRs/MRs (out of {len(prs_to_analyze)} total)."
            )
            prs_to_analyze = prs_to_analyze[:max_prs]

        pr_ids = [getattr(pr, self.pr_id_attr) for pr in prs_to_analyze]
        logger.info(f"[Ondemand] PRs/MRs to analyze: {pr_ids}")
        analysis_results = []
        analysis_durations = []
        errors = []
        analyzed_iids = set()

        async def analyze_pr(pr, semaphore):
            async with semaphore:
                # Consolidate attribute extraction for both platforms
                pr_id = getattr(pr, "iid", getattr(pr, "number", "<unknown>"))
                pr_title = getattr(pr, "title", "<unknown>")
                pr_url = getattr(pr, "web_url", getattr(pr, "html_url", "#"))

                logger.info(f"[Ondemand] Analyzing PR/MR !{pr_id} ({pr_title})")
                start = time.time()
                try:
                    analysis_result = await run_flow(
                        pr_url,
                        pr_id=pr_id,
                        pr_title=pr_title,
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
                        "web_url": pr_url,
                        "duration": time.time() - start,
                        "error": None,
                    }
                    return (pr_id, result)
                except Exception as e:
                    error_msg = f"{type(e).__name__}: {e}"
                    logger.error(
                        f"[Ondemand] Error while analyzing PR/MR !{pr_id}: {error_msg}",
                        exc_info=True,
                    )
                    result = {
                        "iid": pr_id,
                        "title": pr_title,
                        "status": "Error",
                        "impact_score": "N/A",
                        "recommendation": "",
                        "last_reviewed": "N/A",
                        "analysis_link": "#",
                        "web_url": pr_url,
                        "duration": time.time() - start,
                        "error": error_msg,
                    }
                    return (pr_id, result)

        semaphore = asyncio.Semaphore(self.workers)
        tasks = [analyze_pr(pr, semaphore) for pr in prs_to_analyze]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for pr_iid, result in results:
            if result["error"] is None:
                analysis_results.append(
                    {k: result[k] for k in result if k != "duration" and k != "error"}
                )
                analyzed_iids.add(pr_iid)
            else:
                errors.append((pr_iid, result["error"]))
                analysis_results.append(
                    {k: result[k] for k in result if k != "duration"}
                )

            analysis_durations.append(result["duration"])

        # For PRs/MRs not analyzed in this run, preserve previous dashboard data
        # TODO: Previous data should be fetched from the dashboard
        #       instead of assuming it is in the dashboard_data.
        #       Analysis link is not shown for example
        for pr in open_prs:
            # Consolidate attribute extraction for both platforms
            pr_id = getattr(pr, "iid", getattr(pr, "number", "<unknown>"))
            pr_title = getattr(pr, "title", "<unknown>")
            pr_url = getattr(pr, "web_url", getattr(pr, "html_url", "#"))
            if pr_id not in analyzed_iids:
                analysis_results.append(
                    {
                        "iid": pr_id,
                        "title": pr_title,
                        "status": "Tracked",
                        "impact_score": "N/A",
                        "recommendation": "",
                        "last_reviewed": "N/A",
                        "analysis_link": "#",
                        "web_url": pr_url,
                    }
                )
        # Compute analytics summary metrics, accumulating with previous values
        prev_analytics = dashboard_data["analytics"]
        prs_processed = prev_analytics.get("PRs/MRs Processed", 0) + len(prs_to_analyze)

        # Count recommendations from analysis_results and accumulate with previous analytics
        prev_auto_approve = prev_analytics.get("Auto Approve", 0)
        prev_manual_review = prev_analytics.get("Manual Reviews", 0)
        auto_approve_count = prev_auto_approve
        manual_review_count = prev_manual_review
        for pr in analysis_results:
            rec = (pr.get("recommendation") or "").strip().lower()
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
            "PRs/MRs Processed": prs_processed,
            "Auto Approve": auto_approve_count,
            "Manual Reviews": manual_review_count,
            "Avg. Time Open→Merge": avg_time,
        }

        # Only reset rerun_requests for processed PRs/MRs
        remaining_rerun_requests = [
            pr_id
            for pr_id in rerun_requests
            if pr_id
            not in [str(getattr(pr, self.pr_id_attr)) for pr in prs_to_analyze]
        ]

        self.dashboard_manager.update_dashboard(
            mr_data=analysis_results,
            rerun_requests=remaining_rerun_requests,
            action_log=[
                f"Analyzed PR/MR !{getattr(pr, self.pr_id_attr)}"
                for pr in prs_to_analyze
            ]
            + [f"Error in PR/MR !{pr_id}: {err}" for pr_id, err in errors],
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
