"""Dashboard table regeneration: concurrent sessions' rows must not be dropped."""

from types import SimpleNamespace

from mergebot.dashboard.dashboard_manager import DashboardManager

PREVIOUS_TABLE = (
    "| [!1](https://x/1) | Mine | Analyzed | 2.0 | Auto-Approve | 2026-07-01 | [View Report](#) |\n"
    "| [!7](https://x/7) | Theirs | Analyzed | 4.5 | Requires human review | 2026-07-07 "
    "| [View Report](#) |\n"
)


def render(mr_data, previous_table=PREVIOUS_TABLE, carry_over_ids=None):
    # _render_active_mrs_table touches no instance state; a dummy self suffices.
    return DashboardManager._render_active_mrs_table(
        SimpleNamespace(), mr_data, previous_table, carry_over_ids
    )


ROW_FOR_1 = {
    "id": 1,
    "title": "Mine",
    "status": "Analyzed",
    "impact_score": "3.1",
    "recommendation": "Requires human review",
    "last_reviewed": "2026-07-07",
    "web_url": "https://x/1",
    "analysis_link": "#",
}


class TestCarryOver:
    def test_concurrent_row_survives_when_still_open(self):
        """PR !7 was written by another session; this writer never saw it but knows
        it is still open — its row must be carried over, not dropped."""
        table = render([ROW_FOR_1], carry_over_ids={"1", "7"})
        assert "| [!1]" in table
        assert "Theirs" in table
        assert "4.5" in table

    def test_closed_row_is_dropped_without_carry_over(self):
        table = render([ROW_FOR_1], carry_over_ids={"1"})
        assert "Theirs" not in table  # !7 not confirmed open → dropped as before

    def test_default_behavior_unchanged(self):
        table = render([ROW_FOR_1])
        assert "Theirs" not in table

    def test_row_in_mr_data_is_not_duplicated(self):
        table = render([ROW_FOR_1], carry_over_ids={"1"})
        assert table.count("[!1]") == 1

    def test_preservation_of_fresh_values_still_works(self):
        row = dict(ROW_FOR_1, impact_score="N/A", recommendation="", last_reviewed="N/A")
        table = render([row], carry_over_ids={"1"})
        # N/A fields fall back to the previous (fresh-at-write-time) table values
        assert "2.0" in table
        assert "Auto-Approve" in table

    def test_empty_table_placeholder(self):
        assert render([], previous_table=None) == "_No active pull or merge requests._"
