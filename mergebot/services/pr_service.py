from mergebot.project_registry import ProjectRuntime
from mergebot.services.common import ServiceError, async_retry
from mergebot.tools.common import GetPullOrMergeRequestTool
from mergebot.validator.logging_config import logger


def _ensure_text_details(result) -> str:
    """
    The underlying wrappers return:
      - Pretty-printed string on success
      - Dict with {"error": "..."} on failure (get_pull_request)
      - String starting with 'Failed to ...' on failure (comment/approve)

    Normalize to:
      - Return string on success
      - Raise ServiceError on failure
    """
    if isinstance(result, dict):
        # Error path from get_pull_request
        msg = result.get("error") or str(result)
        raise ServiceError(msg, status_code=None, retryable=True)

    text = str(result)
    if text.strip().lower().startswith("failed to"):
        # Failure as string
        raise ServiceError(text, status_code=None, retryable=True)
    return text


@async_retry(max_attempts=3, base_delay=1.0, factor=2.0, max_delay=8.0, jitter=0.5)
async def get_pull_or_merge_request_details(pr_number: int, runtime: ProjectRuntime) -> str:
    """
    Fetch PR/MR details as a pretty-printed text (for current analysis crews)
    using the existing GetPullOrMergeRequestTool outside of AI crews.

    Returns:
        str: Human-readable PR/MR summary text
    Raises:
        ServiceError on failure (retryable by default)
    """
    logger.info(f"Fetching PR/MR details for #{pr_number}")
    try:
        result = GetPullOrMergeRequestTool(runtime=runtime).run(pr_number=pr_number)
        return _ensure_text_details(result)
    except ServiceError:
        raise
    except Exception as e:
        # Unknown errors: let retry decorator handle
        raise ServiceError(f"Unexpected error fetching PR/MR details: {e}", retryable=True) from e
