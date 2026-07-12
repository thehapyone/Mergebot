import asyncio
from dataclasses import dataclass, field

from mergebot.project_registry import ProjectRuntime
from mergebot.services.common import ServiceError, async_retry
from mergebot.tools.api_base import PullRequestDetails
from mergebot.tools.common import build_api_wrapper
from mergebot.validator.logging_config import logger
from mergebot.workspace.manager import PrRef


@dataclass
class PrFetchResult:
    """PR/MR details for one review: text renders, typed metadata, and the git token.

    `details` is the exact blob the analysis crews consume today; `details_no_patch`
    is the same render with per-file patches omitted; `ref` and `git_token` feed
    workspace provisioning and are None when unavailable (degraded to diff-only).
    The token must never be logged or stored in flow state.
    """

    details: str
    details_no_patch: str
    ref: PrRef | None = None
    git_token: str | None = field(default=None, repr=False)


def _ensure_details(result) -> PullRequestDetails:
    """
    The underlying wrappers return:
      - PullRequestDetails on success
      - Dict with {"error": "..."} on failure (get_pull_request_with_ref)
      - String starting with 'Failed to ...' on failure (comment/approve)

    Normalize to:
      - Return PullRequestDetails on success
      - Raise ServiceError on failure
    """
    if isinstance(result, PullRequestDetails):
        return result
    if isinstance(result, dict):
        # Error path from get_pull_request_with_ref
        msg = result.get("error") or str(result)
        raise ServiceError(msg, status_code=None, retryable=True)

    text = str(result)
    if text.strip().lower().startswith("failed to"):
        # Failure as string
        raise ServiceError(text, status_code=None, retryable=True)
    return PullRequestDetails(details=text, details_no_patch=text, ref=None)


@async_retry(max_attempts=3, base_delay=1.0, factor=2.0, max_delay=8.0, jitter=0.5)
async def get_pull_or_merge_request(pr_number: int, runtime: ProjectRuntime) -> PrFetchResult:
    """
    Fetch PR/MR details (pretty-printed text plus typed `PrRef` metadata and the
    platform git token) using the platform API wrapper outside of AI crews.

    Returns:
        PrFetchResult
    Raises:
        ServiceError on failure (retryable by default)
    """
    logger.info(f"Fetching PR/MR details for #{pr_number}")

    def fetch() -> PrFetchResult:
        wrapper = build_api_wrapper(runtime)
        details = _ensure_details(wrapper.get_pull_request_with_ref(pr_number))
        return PrFetchResult(
            details=details.details,
            details_no_patch=details.details_no_patch,
            ref=details.ref,
            git_token=wrapper.resolve_git_token(),
        )

    try:
        return await asyncio.to_thread(fetch)
    except ServiceError:
        raise
    except Exception as e:
        # Unknown errors: let retry decorator handle
        raise ServiceError(f"Unexpected error fetching PR/MR details: {e}", retryable=True) from e


async def get_pull_or_merge_request_details(pr_number: int, runtime: ProjectRuntime) -> str:
    """
    Fetch PR/MR details as a pretty-printed text (for current analysis crews).

    Thin compatibility delegate over `get_pull_or_merge_request`.
    """
    return (await get_pull_or_merge_request(pr_number, runtime)).details
