import asyncio
from mergebot.dashboard_manager import GitLabDashboardManager
from mergebot.tools.gitlab.api_wrapper import GitLabAPIWrapperExtra
from mergebot.flow import run_flow
from mergebot.logging_config import logger
from mergebot.utils import get_platform_type

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
        # 1. Get or create dashboard
        dashboard = self.dashboard_manager.get_or_create_dashboard()
        # 2. List open MRs
        open_mrs = self.api.gitlab_repo_instance.mergerequests.list(state="opened", all=True)
        open_mr_iids = {str(mr.iid): mr for mr in open_mrs}
        # 3. Parse dashboard for rerun requests (checkboxes) and tracked MRs
        dashboard_data = self.dashboard_manager.parse_dashboard(dashboard["body"])
        rerun_requests = set(dashboard_data["rerun_requests"])
        tracked_mrs = set(dashboard_data["tracked_mrs"])
        # 4. Detect which MRs need analysis (new or rerun)
        mrs_to_analyze = []
        for mr_iid, mr in open_mr_iids.items():
            if mr_iid not in tracked_mrs or mr_iid in rerun_requests:
                mrs_to_analyze.append(mr)

        logger.info(f"[Ondemand] MRs to analyze: {[mr.iid for mr in mrs_to_analyze]}")
        # 5. For each MR needing analysis, trigger run_flow and collect results
        analysis_results = []
        for mr in mrs_to_analyze:
            logger.info(f"[Ondemand] Analyzing MR !{mr.iid} ({mr.title})")
            # await run_flow(
            #     mr.web_url,
            #     dashboard_manager=None,  # We'll update dashboard for all MRs below
            # )

        # 6. Collect latest MR data for dashboard (all open MRs)
        for mr in open_mrs:
            analysis_results.append({
                "iid": mr.iid,
                "title": mr.title,
                "status": "Analyzed" if mr in mrs_to_analyze else "Tracked",
                "impact_score": "N/A",  # TODO: Pull real score from analysis if available
                "last_reviewed": "N/A",  # TODO: Pull real timestamp if available
                "analysis_link": "#",    # TODO: Link to detailed report if available
                "web_url": mr.web_url,
            })

        # 7. Update dashboard with all open MRs, current rerun requests, and empty action log/analytics
        self.dashboard_manager.update_dashboard(
            mr_data=analysis_results,
            # Reset the rerun requests after processing them
            rerun_requests=[],
            action_log=[],
            analytics={},
        )
        logger.info("[Ondemand] Dashboard update complete")

    async def run_periodic(self, interval: int):
        logger.info(f"[Ondemand] Running dashboard scan every {interval} seconds")
        while True:
            await self.run_once()
            await asyncio.sleep(interval)
