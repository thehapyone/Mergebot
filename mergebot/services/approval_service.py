import re

from mergebot.services.common import async_retry, ServiceError
from mergebot.tools.common import PostCommentTool, ApprovePullOrMergeRequestTool
from mergebot.validator.logging_config import logger


def _ensure_text_response(result) -> str:
    """
    Normalize wrapper responses:
      - Return string on success
      - Raise ServiceError on failure
    """
    if isinstance(result, dict):
        msg = result.get("error") or str(result)
        raise ServiceError(msg, status_code=None, retryable=True)
    text = str(result or "").strip()
    if text.lower().startswith("failed to"):
        raise ServiceError(text, status_code=None, retryable=True)
    return text


def _extract_url(text: str) -> str:
    m = re.search(r"https?://[^\s)\]]+", text or "")
    return m.group(0) if m else ""


@async_retry(max_attempts=2, base_delay=1.0, factor=2.0, max_delay=8.0, jitter=0.5)
async def post_comment(pr_number: int, body: str) -> str:
    """
    Post a general comment to PR/MR. Returns the permalink URL if available, else empty string.
    """
    logger.info(f"Posting comment on #{pr_number}")
    try:
        text = _ensure_text_response(
            PostCommentTool().run(pr_number=pr_number, message=body)
        )
        return _extract_url(text)
    except ServiceError:
        raise
    except Exception as e:
        raise ServiceError(f"Unexpected error posting comment: {e}", retryable=True)


@async_retry(max_attempts=2, base_delay=1.0, factor=2.0, max_delay=8.0, jitter=0.5)
async def approve_change(pr_number: int) -> str:
    """
    Approve the PR/MR. Returns response text; URL may be embedded for GitHub.
    """
    logger.info(f"Approving change for #{pr_number}")
    try:
        text = _ensure_text_response(
            ApprovePullOrMergeRequestTool().run(pr_number=pr_number)
        )
        return text
    except ServiceError:
        raise
    except Exception as e:
        raise ServiceError(f"Unexpected error approving change: {e}", retryable=True)
