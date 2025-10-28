import re

from mergebot.project_registry import ProjectRuntime
from mergebot.services.common import ServiceError, async_retry
from mergebot.tools.common import ApprovePullOrMergeRequestTool, PostCommentTool
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


def sanitize_comment_body(body: str) -> str:
    """
    Ensure the posted comment does NOT start with triple backtick markdown fences.
    If the entire body is wrapped in a fenced code block (``` or ```markdown/```md/etc),
    unwrap it. Also trims any leading fence line or trailing closing fence.
    """
    if body is None:
        return ""
    text = str(body).strip()

    # If entire body is enclosed in a fenced code block, unwrap it
    m = re.match(r"^\s*```[a-zA-Z0-9_-]*\s*\n(.*)\n\s*```\s*$", text, re.DOTALL)
    if m:
        return m.group(1).strip()

    # If it starts with a fence line, drop just the leading fence line
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            text = "\n".join(lines[1:]).strip()

    # If it ends with a closing fence, drop it
    if text.endswith("```"):
        text = text[:-3].rstrip()

    return text


@async_retry(max_attempts=2, base_delay=1.0, factor=2.0, max_delay=8.0, jitter=0.5)
async def post_comment(pr_number: int, body: str, runtime: ProjectRuntime) -> str:
    """
    Post a general comment to PR/MR. Returns the permalink URL if available, else empty string.
    """
    logger.info(f"Posting comment on #{pr_number}")
    try:
        safe_body = sanitize_comment_body(body)
        text = _ensure_text_response(
            PostCommentTool(runtime=runtime).run(pr_number=pr_number, message=safe_body)
        )
        return _extract_url(text)
    except ServiceError:
        raise
    except Exception as e:
        raise ServiceError(f"Unexpected error posting comment: {e}", retryable=True) from e


@async_retry(max_attempts=2, base_delay=1.0, factor=2.0, max_delay=8.0, jitter=0.5)
async def approve_change(pr_number: int, runtime: ProjectRuntime) -> str:
    """
    Approve the PR/MR. Returns response text; URL may be embedded for GitHub.
    """
    logger.info(f"Approving change for #{pr_number}")
    try:
        text = _ensure_text_response(
            ApprovePullOrMergeRequestTool(runtime=runtime).run(pr_number=pr_number)
        )
        return text
    except ServiceError:
        raise
    except Exception as e:
        raise ServiceError(f"Unexpected error approving change: {e}", retryable=True) from e
