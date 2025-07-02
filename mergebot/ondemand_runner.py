import asyncio
import time

from mergebot.dashboard.dashboard_manager import GitLabDashboardManager
from mergebot.flow import run_flow
from mergebot.tools.gitlab.api_wrapper import GitlabAPIWrapper
from mergebot.utils import get_platform_type
from mergebot.validator.logging_config import logger


class OndemandRunner:
    def __init__(self, project: str):
        # Select platform based on get_platform_type()
        self.platform_type = get_platform_type()
        self.project = project
        if self.platform_type == "gitlab":
            self.api = GitlabAPIWrapper()
            self.project_id = self.api.gitlab_repo_instance.id
            self.dashboard_manager = GitLabDashboardManager(self.api, self.project_id)
        else:
            raise NotImplementedError(
                f"Platform '{self.platform_type}' is not yet supported in ondemand mode."
            )

    async def run_once(self):
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

        mrs_to_analyze = []
        for mr_iid, mr in open_mr_iids.items():
            if mr_iid not in tracked_mrs or mr_iid in rerun_requests:
                mrs_to_analyze.append(mr)

        logger.info(f"[Ondemand] MRs to analyze: {[mr.iid for mr in mrs_to_analyze]}")
        analysis_results = []
        analysis_durations = []
        errors = []
        analyzed_iids = set()
        for mr in mrs_to_analyze:
            logger.info(f"[Ondemand] Analyzing MR !{mr.iid} ({mr.title})")
            start = time.time()
            try:
                analysis_result = await run_flow(
                    mr.web_url, mr_iid=mr.iid, mr_title=mr.title, project=self.project
                )
                analysis_results.append(
                    {
                        "iid": analysis_result.iid,
                        "title": analysis_result.title,
                        "status": "Analyzed",
                        "impact_score": analysis_result.impact_score,
                        "recommendation": analysis_result.recommendation,
                        "last_reviewed": analysis_result.last_reviewed,
                        "analysis_link": analysis_result.analysis_link,
                        "web_url": mr.web_url,
                    }
                )
                analyzed_iids.add(mr.iid)
            except Exception as e:
                # Capture detailed error information and log stack trace
                error_msg = f"{type(e).__name__}: {e}"
                logger.error(
                    f"[Ondemand] Error while analyzing MR !{mr.iid}: {error_msg}",
                    exc_info=True,
                )
                errors.append((mr.iid, error_msg))
            duration = time.time() - start
            analysis_durations.append(duration)

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
        logger.info(f"[Ondemand] Running dashboard scan every {interval} seconds")
        while True:
            await self.run_once()
            await asyncio.sleep(interval)
