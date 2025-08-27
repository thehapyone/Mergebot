import asyncio
import random
from functools import wraps
from typing import Any, Callable, Coroutine, Optional, TypeVar

from mergebot.validator.logging_config import logger

T = TypeVar("T")


class ServiceError(Exception):
    """
    Standardized service-layer exception.

    Attributes:
        message: Human-readable message
        status_code: Optional HTTP-like status to hint retry policy
        retryable: Whether this error should be retried by the caller/decorator
    """

    def __init__(
        self, message: str, status_code: Optional[int] = None, retryable: bool = True
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.retryable = retryable

    def __str__(self) -> str:
        code = f" (status={self.status_code})" if self.status_code is not None else ""
        return f"{self.message}{code} | retryable={self.retryable}"


def is_retryable_status(status_code: Optional[int]) -> bool:
    """
    Decide if a status code is retryable based on common semantics.
    """
    if status_code is None:
        return True
    if status_code in {408, 409, 423, 425, 429}:
        return True
    if 500 <= status_code <= 599:
        return True
    return False


def _compute_backoff_delay(
    base_delay: float, factor: float, attempt: int, max_delay: float, jitter: float
) -> float:
    pure = base_delay * (factor ** (attempt - 1))
    delay = min(pure, max_delay)
    # Full jitter
    return max(0.0, delay + random.uniform(-jitter, jitter))


def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    factor: float = 2.0,
    max_delay: float = 8.0,
    jitter: float = 0.5,
):
    """
    Decorator for retrying async service functions using exponential backoff with jitter.

    Retries when:
      - ServiceError with retryable=True
      - Any other Exception (treated as retryable)

    Notes:
      - Use judiciously around short, idempotent operations (GET, comment post, approve).
      - Do not use for large, non-idempotent writes without safeguards.
    """

    def decorator(func: Callable[..., Coroutine[Any, Any, T]]):
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            attempt = 1
            while True:
                try:
                    return await func(*args, **kwargs)
                except ServiceError as e:
                    should_retry = e.retryable or is_retryable_status(e.status_code)
                    if attempt >= max_attempts or not should_retry:
                        logger.error(f"ServiceError (final) in {func.__name__}: {e}")
                        raise
                    delay = _compute_backoff_delay(
                        base_delay, factor, attempt, max_delay, jitter
                    )
                    logger.warning(
                        f"ServiceError in {func.__name__} (attempt {attempt}/{max_attempts}), retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                except Exception as e:
                    if attempt >= max_attempts:
                        logger.error(
                            f"Unhandled exception (final) in {func.__name__}: {e}"
                        )
                        raise
                    delay = _compute_backoff_delay(
                        base_delay, factor, attempt, max_delay, jitter
                    )
                    logger.warning(
                        f"Unhandled exception in {func.__name__} (attempt {attempt}/{max_attempts}), retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    attempt += 1

        return wrapper

    return decorator
