"""
Helpers for detecting and tracking explicit review requests directed at Mergebot.

Two signal sources are supported:
1) Reviewer/assignee assignment targeting the Mergebot service account.
2) Text comments mentioning Mergebot explicitly or using the `/mergebot review` command.

The detection helpers are designed to work with both GitHub and GitLab via the existing
API wrappers. Tracking state is persisted inside the project dashboard to avoid
rerunning analyses repeatedly for the same request.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from mergebot.validator.logging_config import logger

MENTION_COMMANDS = {"mergebot review", "/mergebot review"}


@dataclass(slots=True)
class ReviewTriggerState:
    """
    Mutable snapshot of trigger state per PR/MR ID.

    Attributes:
        assigned (bool): Whether Mergebot is currently assigned/requested as a reviewer.
        last_comment_id (int | None): Highest comment/note identifier containing an explicit request.
    """

    assigned: bool = False
    last_comment_id: int | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, int | bool] | None) -> ReviewTriggerState:
        if not data:
            return cls()
        assigned = bool(data.get("assigned", False))
        last_comment_id = data.get("last_comment_id")
        try:
            last_comment_id = int(last_comment_id) if last_comment_id is not None else None
        except (TypeError, ValueError):
            last_comment_id = None
        return cls(assigned=assigned, last_comment_id=last_comment_id)

    def to_dict(self) -> dict[str, int | bool]:
        data: dict[str, int | bool] = {"assigned": self.assigned}
        if self.last_comment_id is not None:
            data["last_comment_id"] = int(self.last_comment_id)
        return data

    def has_active_data(self) -> bool:
        return self.assigned or self.last_comment_id is not None


def normalize_login(value: str | None) -> str:
    return (value or "").strip().lower()


def mentions_mergebot(body: str, bot_login: str) -> bool:
    """
    Returns True when the comment body explicitly requests Mergebot to review.
    Supports "/mergebot review" command or "@mergebot" mentions (case-insensitive).
    """
    if not body:
        return False
    lowered = body.strip().lower()
    if any(cmd in lowered for cmd in MENTION_COMMANDS):
        return True
    normalized_login = normalize_login(bot_login)
    if not normalized_login:
        return False
    mention_variants = {
        f"@{normalized_login}",
        f"@{normalized_login}/review",
    }
    return any(token in lowered for token in mention_variants)


def detect_assignment(assignments: Iterable[Mapping[str, str]], bot_login: str) -> bool:
    """
    Returns True when assignments contain the Mergebot account.
    Works for both GitHub and GitLab where the mapping exposes login/username.
    """
    normalized = normalize_login(bot_login)
    if not normalized:
        return False
    for assignee in assignments or []:
        for key in ("login", "username"):
            if normalize_login(assignee.get(key)) == normalized:
                return True
    return False


def compute_triggers(
    *,
    assignments: Iterable[Mapping[str, str]] | None,
    comments: Iterable[tuple[int, str]] | None,
    bot_login: str,
    previous: ReviewTriggerState | None = None,
    require_assignment_drop: bool = False,
) -> tuple[ReviewTriggerState, bool]:
    """
    Compare current signals with previous dashboard snapshot and detect transitions.

    Returns:
        (new_state, triggered)
    where triggered = True when Mergebot should analyze this PR.
    """
    state = ReviewTriggerState.from_mapping(previous.to_dict() if previous else None)
    triggered = False

    # Reviewer assignment transition
    currently_assigned = detect_assignment(assignments or [], bot_login)
    if currently_assigned and not state.assigned:
        triggered = True
    elif not currently_assigned and state.assigned and require_assignment_drop:
        # Clear cached comment state if users explicitly unassign Mergebot. This prevents
        # stale comment IDs from suppressing future triggers when the bot is re-requested.
        state.last_comment_id = None
    state.assigned = currently_assigned

    # Latest commands addressed to Mergebot
    latest_comment_id = state.last_comment_id or -1
    for comment_id, body in comments or []:
        if comment_id is None:
            continue
        try:
            current_id = int(comment_id)
        except (TypeError, ValueError):
            continue
        if current_id <= latest_comment_id:
            continue
        if mentions_mergebot(body or "", bot_login):
            latest_comment_id = current_id
            triggered = True

    state.last_comment_id = None if latest_comment_id < 0 else latest_comment_id
    return state, triggered


def _pr_identifier(pr) -> str:
    for attr in ("iid", "number", "id"):
        val = getattr(pr, attr, None)
        if val is not None:
            return str(val)
    return "?"


def collect_assignments(pr, platform_type: str) -> list[dict[str, str]]:
    assignments: list[dict[str, str]] = []
    try:
        if platform_type == "github":
            for reviewer in getattr(pr, "requested_reviewers", []) or []:
                assignments.append({"login": getattr(reviewer, "login", "")})
            for assignee in getattr(pr, "assignees", []) or []:
                assignments.append({"login": getattr(assignee, "login", "")})
        elif platform_type == "gitlab":
            for assignee in getattr(pr, "assignees", []) or []:
                username = (
                    assignee.get("username")
                    if isinstance(assignee, dict)
                    else getattr(assignee, "username", "")
                )
                assignments.append({"username": username})
            for reviewer in getattr(pr, "reviewers", []) or []:
                username = (
                    reviewer.get("username")
                    if isinstance(reviewer, dict)
                    else getattr(reviewer, "username", "")
                )
                assignments.append({"username": username})
    except Exception as exc:  # pragma: no cover - external API path
        logger.warning(
            "[ReviewTriggers] Failed to collect assignments for PR/MR %s: %s",
            _pr_identifier(pr),
            exc,
        )
    return assignments


def collect_comments(pr, platform_type: str, bot_login: str) -> list[tuple[int, str]]:
    comments: list[tuple[int, str]] = []
    normalized_bot = normalize_login(bot_login)
    try:
        if platform_type == "github":
            iterator = pr.get_issue_comments()
            for comment in iterator:
                comment_id = getattr(comment, "id", None)
                body = getattr(comment, "body", "")
                author = getattr(getattr(comment, "user", None), "login", "")
                if normalized_bot and normalize_login(author) == normalized_bot:
                    continue
                comments.append((comment_id, body))
        elif platform_type == "gitlab":
            notes = pr.notes.list(all=True)
            for note in notes:
                comment_id = getattr(note, "id", None)
                body = getattr(note, "body", getattr(note, "note", ""))
                author = getattr(note, "author", {}) or {}
                if isinstance(author, dict):
                    author_username = author.get("username") or author.get("name") or ""
                else:
                    author_username = getattr(author, "username", "")
                if normalized_bot and normalize_login(author_username) == normalized_bot:
                    continue
                comments.append((comment_id, body))
    except Exception as exc:  # pragma: no cover - external API path
        logger.warning(
            "[ReviewTriggers] Failed to collect comments for PR/MR %s: %s",
            _pr_identifier(pr),
            exc,
        )
    return comments
