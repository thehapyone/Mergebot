import asyncio
from mergebot.dashboard_manager import GitLabDashboardManager
from mergebot.tools.gitlab.api_wrapper import GitLabAPIWrapperExtra
from mergebot.flow import run_flow
from mergebot.logging_config import logger
from mergebot.utils import get_platform_type
import time
from datetime import datetime

class OndemandRunner:
    def __init__(self):
        # Select platform based on get_platform_type()
        self.platform_type = get_platform_type()
        if self.platform_type == "gitlab":
            self.api = GitLabAPIWrapperExtra()
            self.project_id = self.api.gitlab_repo_instance.id
            self.dashboard_manager = GitLabDashboardManager(self.api, self.project_id)
        else:
            raise NotImplementedError(f"Platform '{self.platform_type}' is not yet supported in ondemand mode.")

    async def run_once(self):
        logger.info("[Ondemand] Running dashboard scan and update (one-shot)")
        dashboard = self.dashboard_manager.get_or_create_dashboard()
        open_mrs = self.api.gitlab_repo_instance.mergerequests.list(state="opened", all=True)
        open_mr_iids = {str(mr.iid): mr for mr in open_mrs}
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
        for mr in mrs_to_analyze:
            logger.info(f"[Ondemand] Analyzing MR !{mr.iid} ({mr.title})")
            start = time.time()
            try:
                # await run_flow(
                #     mr.web_url,
                #     dashboard_manager=None,
                # )
                result = "Success"
            except Exception as e:
                result = f"Error: {e}"
                errors.append((mr.iid, str(e)))
            duration = time.time() - start
            analysis_durations.append(duration)

        # Build MR data for dashboard
        for mr in open_mrs:
            analysis_results.append({
                "iid": mr.iid,
                "title": mr.title,
                "status": "Analyzed" if mr in mrs_to_analyze else "Tracked",
                "impact_score": "N/A",
                "last_reviewed": datetime.now().strftime("%Y-%m-%d %H:%M UTC") if mr in mrs_to_analyze else "N/A",
                "analysis_link": "#",
                "web_url": mr.web_url,
            })

        # Compute analytics summary metrics, accumulating with previous values
        dashboard_body = dashboard.get("body", "")
        prev_analytics = self.dashboard_manager.parse_analytics_summary(dashboard_body)
        mrs_processed = prev_analytics.get("MRs Processed", 0) + len(mrs_to_analyze)
        auto_merges = prev_analytics.get("Auto-merges", 0)  # TODO: Implement auto-merge detection if available
        manual_reviews = prev_analytics.get("Manual Reviews", 0)  # TODO: Implement manual review detection if available

        # For average, keep a running sum and count in a hidden comment (not implemented here), or just use a simple running average
        prev_avg = prev_analytics.get("Avg. Time Open→Merge", "N/A")
        if analysis_durations:
            avg_seconds = sum(analysis_durations) / len(analysis_durations)
            avg_time = f"{int(avg_seconds//60)}h {int(avg_seconds%60)}m"
        else:
            avg_time = prev_avg if prev_avg != "N/A" else "N/A"

        analytics_summary = {
            "MRs Processed": mrs_processed,
            "Auto-merges": auto_merges,
            "Manual Reviews": manual_reviews,
            "Avg. Time Open→Merge": avg_time,
        }

        # Only reset rerun_requests for processed MRs
        remaining_rerun_requests = [iid for iid in rerun_requests if iid not in [str(mr.iid) for mr in mrs_to_analyze]]

        self.dashboard_manager.update_dashboard(
            mr_data=analysis_results,
            rerun_requests=remaining_rerun_requests,
            action_log=[f"Analyzed MR !{mr.iid}" for mr in mrs_to_analyze] + [f"Error in MR !{iid}: {err}" for iid, err in errors],
            analytics=analytics_summary,
        )
        logger.info("[Ondemand] Dashboard update complete")

    async def run_periodic(self, interval: int):
        logger.info(f"[Ondemand] Running dashboard scan every {interval} seconds")
        while True:
            await self.run_once()
            await asyncio.sleep(interval)
