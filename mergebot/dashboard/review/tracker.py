"""Dashboard-backed storage for Mergebot review triggers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from mergebot.dashboard.constants import REVIEW_TRIGGERS_MARKER
from mergebot.review_triggers import ReviewTriggerState

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from mergebot.dashboard.dashboard_manager import DashboardManager

PLACEHOLDER = "_No review triggers recorded_"


def _strip_fence(text: str) -> str:
    if not text:
        return text
    t = text.strip()
    if not t.startswith("```"):
        if "```" not in t:
            return t
        t = t[t.index("```") :]
    lines = t.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _fenced_json(payload: dict[str, Any]) -> str:
    return "```json\n" + json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n```"


class DashboardReviewTracker:
    """Persist review-trigger snapshots inside the dashboard issue body."""

    def __init__(self, manager: "DashboardManager"):
        self.manager = manager

    def load(self) -> dict[str, ReviewTriggerState]:
        dashboard = self.manager.get_or_create_dashboard()
        section = self.manager.extract_custom_section(dashboard["body"], REVIEW_TRIGGERS_MARKER)
        if not section or section.strip() == PLACEHOLDER:
            return {}
        try:
            content = _strip_fence(section)
            raw = json.loads(content)
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        snapshots: dict[str, ReviewTriggerState] = {}
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            snapshots[key] = ReviewTriggerState.from_mapping(value)
        return snapshots

    def save(self, snapshots: dict[str, ReviewTriggerState]) -> None:
        dashboard = self.manager.get_or_create_dashboard()
        state = {
            str(k): v.to_dict()
            for k, v in snapshots.items()
            if v and isinstance(v, ReviewTriggerState) and v.has_active_data()
        }
        if not state:
            payload = PLACEHOLDER
        else:
            payload = _fenced_json(state)
        updated = self.manager.replace_custom_section(
            dashboard["body"], REVIEW_TRIGGERS_MARKER, payload
        )
        self.manager.api.update_issue(dashboard["id"], updated)
