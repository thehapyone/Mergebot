import re
from typing import Any

from mergebot.services.common import ServiceError, async_retry
from mergebot.tools.common import (
    GetPullRequestStatusTool,
    MergePullOrMergeRequestTool,
)
from mergebot.validator.logging_config import logger


def _ensure_text_response(result) -> str:
    """
    Normalize wrapper responses:
      - Return string on success
      - Raise ServiceError on failure
    """
    if isinstance(result, dict) and result.get("error"):
        msg = result.get("error") or str(result)
        raise ServiceError(msg, status_code=None, retryable=True)
    text = str(result or "").strip()
    if text.lower().startswith("failed to"):
        raise ServiceError(text, status_code=None, retryable=True)
    return text


def _ensure_dict_response(result) -> dict[str, Any]:
    """
    Ensure a dict status is returned; raise on tool-level error strings.
    """
    if isinstance(result, str):
        txt = result.strip()
        if txt.lower().startswith("failed to"):
            raise ServiceError(txt, status_code=None, retryable=True)
        # Non-error string is unexpected here; wrap it
        return {"error": txt}
    if isinstance(result, dict):
        if result.get("error"):
            raise ServiceError(result.get("error"), status_code=None, retryable=True)
        return result
    return {"error": f"Unexpected status result type: {type(result)}"}


def parse_first_float(value: str) -> float | None:
    """
    Extract first float-like number from a string. Returns None if not found.
    """
    if value is None:
        return None
    m = re.search(r"[-+]?\d*\.?\d+", str(value))
    if not m:
        return None
    try:
        return float(m.group())
    except Exception:
        return None


def evaluate_rules(
    status: dict[str, Any],
    rules: dict[str, bool],
    enforce_never_merge_draft: bool = True,
) -> tuple[bool, list[str]]:
    """
    Evaluate pre-merge guardrails against a status dict and rules flags.
    Returns (allowed, reasons[])
    """
    reasons: list[str] = []

    # Hard block: never merge Draft/WIP
    if enforce_never_merge_draft and status.get("draft") is True:
        reasons.append("Draft/WIP")

    if rules.get("mergeable", True) and status.get("mergeable") is not True:
        reasons.append("Not mergeable (conflicts or unknown)")

    if rules.get("ci_passed", True):
        ci_passed = status.get("ci_passed")
        ci_state = status.get("ci_state", "").lower()
        ci_strict = bool(rules.get("ci_strict", False))
        if ci_passed is False:
            if ci_state == "pending":
                reasons.append("CI pending")
            else:
                reasons.append("CI failing")
        elif ci_passed is None and ci_strict:
            # Only treat unknown/no CI as a blocker when ci_strict is enabled
            reasons.append(f"CI state: {ci_state}")

    if rules.get("approval_state", True) and status.get("approval_state") is not True:
        reasons.append("Approval state not satisfied")

    if rules.get("no_changes_requested", True):
        reviews = status.get("reviews", {}) or {}
        if (reviews.get("changes_requested") or 0) > 0:
            reasons.append("Changes requested")

    return (len(reasons) == 0, reasons)


@async_retry(max_attempts=2, base_delay=1.0, factor=2.0, max_delay=8.0, jitter=0.5)
async def get_status(pr_number: int) -> dict[str, Any]:
    """
    Fetch a structured PR/MR status for pre-merge decision making.
    """
    logger.info(f"Fetching PR/MR structured status for #{pr_number}")
    try:
        result = GetPullRequestStatusTool().run(pr_number=pr_number)
        return _ensure_dict_response(result)
    except ServiceError:
        raise
    except Exception as e:
        raise ServiceError(f"Unexpected error fetching status: {e}", retryable=True) from e


@async_retry(max_attempts=2, base_delay=1.0, factor=2.0, max_delay=8.0, jitter=0.5)
async def merge_change(pr_number: int, strategy: str = "repo_default") -> str:
    """
    Perform the merge operation using the underlying platform.
    """
    logger.info(f"Merging change for #{pr_number} with strategy={strategy}")
    try:
        text = _ensure_text_response(
            MergePullOrMergeRequestTool().run(pr_number=pr_number, strategy=strategy)
        )
        return text
    except ServiceError:
        raise
    except Exception as e:
        raise ServiceError(f"Unexpected error merging change: {e}", retryable=True) from e
