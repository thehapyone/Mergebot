import re
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any, Literal

from jinja2 import Template

from mergebot.dashboard.dedupe import stats_quality_key
from mergebot.tools.github.api_wrapper import GitHubAPIWrapper
from mergebot.tools.gitlab.api_wrapper import GitlabAPIWrapper

# Section markers for robust, sectioned updates
DASHBOARD_MARKER = "<!-- marker:MERGEBOT_DASHBOARD -->"
ACTIVE_PRS_MARKER = "<!-- marker:MERGEBOT_ACTIVE_PRS -->"
RERUNS_MARKER = "<!-- marker:MERGEBOT_RERUNS -->"
ACTIONS_MARKER = "<!-- marker:MERGEBOT_ACTIONS -->"
ANALYTICS_MARKER = "<!-- marker:MERGEBOT_ANALYTICS -->"
SESSION_LOCK_MARKER = "<!-- marker:MERGEBOT_SESSION_LOCK -->"


@cache
def _load_dashboard_template() -> str:
    """Load the dashboard template from file (cached)."""
    current_directory = Path(__file__).parent
    template_path = current_directory / "dashboard_layout.md"
    with template_path.open("r", encoding="utf-8") as f:
        return f.read()


class DashboardManager:
    """
    VCS Agnostic Dashboard manager (supports PR/MR).
    """

    def __init__(
        self,
        platform_type: Literal["gitlab", "github"],
    ):
        if platform_type == "gitlab":
            self.api = GitlabAPIWrapper()
        elif platform_type == "github":
            self.api = GitHubAPIWrapper()
        else:
            raise ValueError(f"Unsupported VCS: {platform_type}")

        self.platform_type = platform_type
        self.dashboard_title: str = "🛠️ Mergebot Project Dashboard"

    def get_open_prs(self):
        """
        A utility function to fetch all open PRs/MRs and returns a tuple:
            (list_of_prs, {pr_id_string: pr_object, ...})
        """
        if self.platform_type == "gitlab":
            # Use all=True and iterator to reduce memory if large
            open_prs = list(
                self.api.gitlab_repo_instance.mergerequests.list(state="opened", all=True)
            )
            get_id = lambda pr: str(pr.iid)  # noqa: E731
        elif self.platform_type == "github":
            open_prs = list(self.api.github_repo_instance.get_pulls(state="open"))
            get_id = lambda pr: str(pr.number)  # noqa: E731
        else:
            raise NotImplementedError(f"Platform '{self.platform_type}' is not supported.")
        open_pr_iids = {get_id(pr): pr for pr in open_prs}
        return open_prs, open_pr_iids

    def get_or_create_dashboard(self) -> dict[str, Any]:
        """
        Retrieves the existing Mergebot dashboard issue for the current repository/project,
        identified by a unique title and marker in its body/description. If no such issue
        exists, a new one is created using the dashboard template.

        Returns:
            dict: A dictionary containing the dashboard issue's unique identifier (either
                  'number' for GitHub or 'iid' for GitLab) as 'id' and its text content
                  (either 'body' for GitHub or 'description' for GitLab) as 'body'.
        """
        # Search for existing issue
        issues = self.api.search_issues(self.dashboard_title)
        id_key = "number" if self.platform_type == "github" else "iid"
        body_key = "body" if self.platform_type == "github" else "description"
        for issue in issues:
            if DASHBOARD_MARKER in issue.get(body_key, ""):
                return {"id": issue[id_key], "body": issue[body_key]}
        # Not found, create new
        initial_body = self._initial_dashboard_body()
        issue = self.api.create_issue(self.dashboard_title, initial_body)
        return {"id": issue[id_key], "body": issue[body_key]}

    def parse_dashboard(self, markdown: str) -> dict[str, Any]:
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
        tracked_prs = self.extract_tracked_prs(dashboard_section)
        analytics_section = self.parse_analytics_summary(markdown)

        return {
            "dashboard": dashboard_section,
            "rerun_requests": rerun_requests,
            "tracked_prs": tracked_prs,
            "analytics": analytics_section,
        }

    def extract_rerun_requests(self, dashboard_section: str) -> list:
        """
        Extracts PR/MR numbers from checked rerun checkboxes in the dashboard section.
        Returns a list of PR/MR numbers as strings.
        """
        # Matches: - [x] Rerun agent analysis for [!123](...)
        pattern = r"- \[x\] Rerun agent analysis for \[!(\d+)\]"
        return re.findall(pattern, dashboard_section, re.IGNORECASE)

    def extract_tracked_prs(self, dashboard_section: str) -> list:
        """
        Extracts PR/MR numbers from the Active PRs/MRs table in the dashboard section.
        Returns a list of PR/MR numbers as strings.
        """
        # Matches: | [!123](...) | ...
        pattern = r"\|\s*\[!(\d+)\]\("
        return re.findall(pattern, dashboard_section)

    def update_dashboard(
        self,
        mr_data: list[dict[str, Any]],
        rerun_requests: list[str],
        action_log: list[str],
        analytics: dict[str, Any],
        **kwargs,
    ) -> None:
        """
        Regenerate the dashboard markdown and update the issue.
        """
        dashboard_body = self._generate_dashboard_body(
            mr_data, rerun_requests, action_log, analytics
        )
        dashboard = self.get_or_create_dashboard()
        self.api.update_issue(dashboard["id"], dashboard_body)

    def _initial_dashboard_body(self) -> str:
        """Load the dashboard template (delegates to cached module function)."""
        return _load_dashboard_template()

    def _generate_dashboard_body(
        self,
        mr_data: list[dict[str, Any]],
        rerun_requests: list[str],
        action_log: list[str],
        analytics: dict[str, Any],
    ) -> str:
        # Load the dashboard template
        template_str = self._initial_dashboard_body()
        template = Template(template_str)

        # Extract previous MR table for Last Reviewed preservation and current lock section
        previous_table = None
        locks_section = "_No active session lock_"
        try:
            # Find the Active Merge Requests table and Session Lock section in the current dashboard
            dashboard = self.get_or_create_dashboard()
            body = dashboard.get("body", "")
            table_match = re.search(
                r"## 🧩 \*\*Active Pull/Merge Requests \(PR/MR\)\*\*.*?\n((?:\|.*\n)+)",
                body,
                re.DOTALL,
            )
            if table_match:
                previous_table = table_match.group(1)

            # Extract the session lock section content between markers (without markers)
            lock_pattern = rf"{re.escape(SESSION_LOCK_MARKER)}(.*?){re.escape(SESSION_LOCK_MARKER)}"
            lock_match = re.search(lock_pattern, body, re.DOTALL)
            if lock_match:
                content = (lock_match.group(1) or "").strip()
                if content:
                    locks_section = content
        except Exception:
            # Keep defaults if anything goes wrong
            previous_table = None
            locks_section = "_No active session lock_"

        # Render all sections
        rendered = template.render(
            last_updated=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
            active_mrs_table=self._render_active_mrs_table(mr_data, previous_table),
            rerun_checklist=self._render_rerun_checklist(mr_data, rerun_requests),
            action_log=self._render_action_log(action_log),
            analytics_table=self._render_analytics_table(analytics),
            locks_section=locks_section,
        )
        return rendered

    def _render_active_mrs_table(
        self, mr_data: list[dict[str, Any]], previous_table: str | None = None
    ) -> str:
        """
        Render the MR table, preserving Last Reviewed from previous_table unless MR was just analyzed.
        """
        # Parse previous Last Reviewed values if available
        last_reviewed_map = {}
        recommendation_map = {}
        impact_score_map = {}
        if previous_table:
            # Parse each row for PR id, Impact Score, Recommendation, and Last Reviewed
            for line in previous_table.splitlines():
                match = re.match(
                    r"\|\s*\[!(\d+)\][^\|]*\|[^\|]*\|[^\|]*\|([^\|]*)\|([^\|]*)\|([^\|]*)\|",
                    line,
                )
                if match:
                    pr_id = match.group(1)
                    impact_score = match.group(2).strip()
                    recommendation = match.group(3).strip()
                    last_reviewed = match.group(4).strip()
                    impact_score_map[pr_id] = impact_score
                    recommendation_map[pr_id] = recommendation
                    last_reviewed_map[pr_id] = last_reviewed

        if not mr_data:
            return "_No active pull or merge requests._"
        header = "| PR/MR | Title | Status | Impact Score | Recommendation | Last Reviewed | Analysis |\n|-------|-------|--------|-------------|----------------|---------------|----------|"
        rows = []
        for pr in mr_data:
            pr_id_str = str(pr["id"])
            # If this PR/MR was just analyzed, use the new value; else, preserve previous
            last_reviewed = pr.get("last_reviewed", "").strip()
            recommendation = pr.get("recommendation", "").strip()
            impact_score = pr.get("impact_score", "").strip()
            if not last_reviewed or last_reviewed == "N/A":
                last_reviewed = last_reviewed_map.get(pr_id_str, "N/A")
            if not recommendation:
                recommendation = recommendation_map.get(pr_id_str, "")
            if not impact_score or impact_score == "N/A":
                impact_score = impact_score_map.get(pr_id_str, "N/A")

            rows.append(
                f"| [!{pr['id']}]({pr.get('web_url', '#')}) | {pr.get('title', '')} | {pr.get('status', '')} | {impact_score} | {recommendation} | {last_reviewed} | [View Report]({pr.get('analysis_link', '#')}) |"
            )
        return header + "\n" + "\n".join(rows)

    def _render_rerun_checklist(
        self, mr_data: list[dict[str, Any]], rerun_requests: list[str]
    ) -> str:
        if not mr_data:
            return "_No pull or merge requests available for rerun._"
        lines = []
        for pr in mr_data:
            checked = "x" if str(pr["id"]) in rerun_requests else " "
            lines.append(
                f"- [{checked}] Rerun agent analysis for [!{pr['id']}]({pr.get('web_url', '#')})"
            )
        return "\n".join(lines)

    def _render_action_log(self, action_log: list[str]) -> str:
        if not action_log:
            return "_No recent actions._"
        return "\n".join(f"- {entry}" for entry in action_log)

    def _render_analytics_table(self, analytics: dict[str, Any]) -> str:
        """
        Render the analytics summary table from a dict of metrics.
        """
        if not analytics:
            return "_No analytics data available._"
        header = "| Metric | Value |\n|-------------------------------|-----------|"
        rows = [f"| {k} | **{v}** |" for k, v in analytics.items()]
        return header + "\n" + "\n".join(rows)

    def parse_active_prs_table(self, markdown: str) -> dict[str, dict[str, str]]:
        """
        Parse the 'Active Pull/Merge Requests' table and return a map:
        {
            "<id>": {"impact_score": str, "recommendation": str, "last_reviewed": str}
        }
        If the table is not present, returns an empty dict.
        """
        try:
            table_match = re.search(
                r"## 🧩 \*\*Active Pull/Merge Requests \(PR/MR\)\*\*.*?\n((?:\|.*\n)+)",
                markdown,
                re.DOTALL,
            )
            if not table_match:
                return {}
            table_text = table_match.group(1)
            result: dict[str, dict[str, str]] = {}

            for line in table_text.splitlines():
                m = re.match(
                    r"\|\s*\[!(\d+)\][^\|]*\|[^\|]*\|[^\|]*\|([^\|]*)\|([^\|]*)\|([^\|]*)\|",
                    line,
                )
                if m:
                    pr_id = m.group(1)
                    impact_score = m.group(2).strip()
                    recommendation = m.group(3).strip()
                    last_reviewed = m.group(4).strip()
                    existing = result.get(pr_id)
                    if existing is None or stats_quality_key(
                        impact_score, recommendation, last_reviewed
                    ) > stats_quality_key(
                        existing.get("impact_score", ""),
                        existing.get("recommendation", ""),
                        existing.get("last_reviewed", ""),
                    ):
                        result[pr_id] = {
                            "impact_score": impact_score,
                            "recommendation": recommendation,
                            "last_reviewed": last_reviewed,
                        }
            return result
        except Exception:
            return {}

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
