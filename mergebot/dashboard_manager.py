from functools import lru_cache
import re
from typing import Optional, Dict, List, Any
from pathlib import Path

from datetime import datetime
from jinja2 import Template

# Section markers for robust, sectioned updates
DASHBOARD_MARKER = "<!-- marker:MERGEBOT_DASHBOARD -->"
ACTIVE_MRS_MARKER = "<!-- marker:MERGEBOT_ACTIVE_MRS -->"
RERUNS_MARKER = "<!-- marker:MERGEBOT_RERUNS -->"
ACTIONS_MARKER = "<!-- marker:MERGEBOT_ACTIONS -->"
ANALYTICS_MARKER = "<!-- marker:MERGEBOT_ANALYTICS -->"


class DashboardManager:
    """
    Abstract interface for dashboard management.
    """

    def get_or_create_dashboard(self) -> Dict[str, Any]:
        """
        Fetch the dashboard issue, or create it if not present.
        Returns a dict with at least 'id' and 'body' (markdown).
        """
        raise NotImplementedError

    def parse_dashboard(self, markdown: str) -> Dict[str, Any]:
        """
        Parse the dashboard markdown into structured data.
        Returns a dict with keys for each section.
        """
        raise NotImplementedError

    def update_dashboard(
        self,
        mr_data: List[Dict[str, Any]],
        rerun_requests: List[str],
        action_log: List[str],
        analytics: Dict[str, Any],
    ) -> None:
        """
        Update the dashboard issue with new data.
        """
        raise NotImplementedError


class GitLabDashboardManager(DashboardManager):
    """
    GitLab-specific dashboard manager.
    """

    def __init__(
        self,
        api_wrapper,
        project_id: str,
        dashboard_title: str = "🛠️ Mergebot Project Dashboard",
    ):
        self.api = api_wrapper
        self.project_id = project_id
        self.dashboard_title = dashboard_title

    def get_or_create_dashboard(self) -> Dict[str, Any]:
        """
        Search for the dashboard issue by title or marker.
        If not found, create it with the initial template.
        """
        # Search for existing issue
        issues = self.api.search_issues(self.project_id, self.dashboard_title)
        for issue in issues:
            if DASHBOARD_MARKER in issue.get("description", ""):
                return {"id": issue["iid"], "body": issue["description"]}
        # Not found, create new
        initial_body = self._initial_dashboard_body()
        issue = self.api.create_issue(
            self.project_id, self.dashboard_title, initial_body
        )
        return {"id": issue["iid"], "body": issue["description"]}

    def parse_dashboard(self, markdown: str) -> Dict[str, Any]:
        """
        Extracts sections from the dashboard markdown using markers.
        Returns a dict with section contents and parsed data.
        """

        def extract_section(marker):
            pattern = rf"{re.escape(marker)}(.*?){re.escape(marker)}"
            match = re.search(pattern, markdown, re.DOTALL)
            return match.group(1).strip() if match else ""

        dashboard_section = extract_section(DASHBOARD_MARKER)
        rerun_requests = self.extract_rerun_requests(dashboard_section)
        tracked_mrs = self.extract_tracked_mrs(dashboard_section)
        analytics_section = self.parse_analytics_summary(markdown)

        return {
            "dashboard": dashboard_section,
            "rerun_requests": rerun_requests,
            "tracked_mrs": tracked_mrs,
            "analytics": analytics_section,
        }

    def extract_rerun_requests(self, dashboard_section: str) -> list:
        """
        Extracts MR numbers from checked rerun checkboxes in the dashboard section.
        Returns a list of MR numbers as strings.
        """
        # Matches: - [x] Rerun agent analysis for [!123](...)
        pattern = r"- \[x\] Rerun agent analysis for \[!(\d+)\]"
        return re.findall(pattern, dashboard_section, re.IGNORECASE)

    def extract_tracked_mrs(self, dashboard_section: str) -> list:
        """
        Extracts MR numbers from the Active Merge Requests table in the dashboard section.
        Returns a list of MR numbers as strings.
        """
        # Matches: | [!123](...) | ...
        pattern = r"\|\s*\[!(\d+)\]\("
        return re.findall(pattern, dashboard_section)

    def update_dashboard(
        self,
        mr_data: List[Dict[str, Any]],
        rerun_requests: List[str],
        action_log: List[str],
        analytics: Dict[str, Any],
        **kwargs
    ) -> None:
        """
        Regenerate the dashboard markdown and update the issue.
        """
        dashboard_body = self._generate_dashboard_body(
            mr_data, rerun_requests, action_log, analytics
        )
        dashboard = self.get_or_create_dashboard()
        self.api.update_issue(self.project_id, dashboard["id"], dashboard_body)

    @lru_cache(maxsize=None)
    def _initial_dashboard_body(self) -> str:
        # Load the dashboard template from a file located in the same directory as this script

        current_directory = Path(__file__).parent
        template_path = current_directory / "dashboard_layout.md"

        # Read and return the content of the template file
        with template_path.open("r", encoding="utf-8") as f:
            return f.read()

    def _generate_dashboard_body(
        self,
        mr_data: List[Dict[str, Any]],
        rerun_requests: List[str],
        action_log: List[str],
        analytics: Dict[str, Any],
    ) -> str:
        # Load the dashboard template
        template_str = self._initial_dashboard_body()
        template = Template(template_str)

        # Extract previous MR table for Last Reviewed preservation
        previous_table = None
        try:
            # Find the Active Merge Requests table in the current dashboard
            dashboard = self.get_or_create_dashboard()
            body = dashboard.get("body", "")
            table_match = re.search(
                r"## 🧩 \*\*Active Merge Requests\*\*.*?\n((?:\|.*\n)+)", body, re.DOTALL
            )
            if table_match:
                previous_table = table_match.group(1)
        except Exception:
            previous_table = None

        # Render all sections
        rendered = template.render(
            last_updated=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
            active_mrs_table=self._render_active_mrs_table(mr_data, previous_table),
            rerun_checklist=self._render_rerun_checklist(mr_data, rerun_requests),
            action_log=self._render_action_log(action_log),
            analytics_table=self._render_analytics_table(analytics),
        )
        return rendered

    def _render_active_mrs_table(self, mr_data: List[Dict[str, Any]], previous_table: str = None) -> str:
        """
        Render the MR table, preserving Last Reviewed from previous_table unless MR was just analyzed.
        """
        # Parse previous Last Reviewed values if available
        last_reviewed_map = {}
        if previous_table:
            # Parse each row for MR iid and Last Reviewed
            for line in previous_table.splitlines():
                match = re.match(r"\|\s*\[!(\d+)\][^\|]*\|[^\|]*\|[^\|]*\|[^\|]*\|([^\|]*)\|", line)
                if match:
                    iid, last_reviewed = match.group(1), match.group(2).strip()
                    last_reviewed_map[iid] = last_reviewed

        if not mr_data:
            return "_No active merge requests._"
        header = "| MR | Title | Status | Impact Score | Last Reviewed | Analysis |\n|-----|-------|--------|-------------|---------------|----------|"
        rows = []
        for mr in mr_data:
            iid_str = str(mr['iid'])
            # If this MR was just analyzed, use the new value; else, preserve previous
            last_reviewed = mr.get('last_reviewed', '').strip()
            if not last_reviewed or last_reviewed == "N/A":
                last_reviewed = last_reviewed_map.get(iid_str, "N/A")
            rows.append(
                f"| [!{mr['iid']}]({mr.get('web_url', '#')}) | {mr.get('title', '')} | {mr.get('status', '')} | {mr.get('impact_score', '')} | {last_reviewed} | [View Report]({mr.get('analysis_link', '#')}) |"
            )
        return header + "\n" + "\n".join(rows)

    def _render_rerun_checklist(
        self, mr_data: List[Dict[str, Any]], rerun_requests: List[str]
    ) -> str:
        if not mr_data:
            return "_No merge requests available for rerun._"
        lines = []
        for mr in mr_data:
            checked = "x" if str(mr["iid"]) in rerun_requests else " "
            lines.append(
                f"- [{checked}] Rerun agent analysis for [!{mr['iid']}]({mr.get('web_url', '#')})"
            )
        return "\n".join(lines)

    def _render_action_log(self, action_log: List[str]) -> str:
        if not action_log:
            return "_No recent actions._"
        return "\n".join(f"- {entry}" for entry in action_log)

    def _render_analytics_table(self, analytics: Dict[str, Any]) -> str:
        """
        Render the analytics summary table from a dict of metrics.
        """
        if not analytics:
            return "_No analytics data available._"
        header = "| Metric | Value |\n|-------------------------------|-----------|"
        rows = [f"| {k} | **{v}** |" for k, v in analytics.items()]
        return header + "\n" + "\n".join(rows)

    def parse_analytics_summary(self, markdown: str) -> dict:
        """
        Parse the analytics summary table from the dashboard markdown.
        Returns a dict of metrics.
        """
        # Look for the analytics table by header
        pattern = r"\| Metric \| Value \|.*?\n((?:\|.*\n)+)"
        match = re.search(pattern, markdown)
        if not match:
            return {}
        rows = match.group(1).strip().split("\n")
        summary = {}
        for row in rows:
            cols = [c.strip() for c in row.strip("|").split("|")]
            if len(cols) < 2:
                continue
            key, value = cols[0], cols[1].strip("* ")
            # Try to parse as int, else keep as string
            try:
                summary[key] = int(value)
            except Exception:
                summary[key] = value
        return summary
