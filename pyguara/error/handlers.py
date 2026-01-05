"""Decorators and utilities for error handling."""

import functools
import time
import logging
from typing import Any, Callable, Dict, Optional, TypeVar


T = TypeVar("T")


def safe_execute(
    logger: Optional[logging.Logger] = None,
    default_return: Any = None,
    reraise: bool = False,
    context: Optional[Dict[str, Any]] = None,
) -> Callable:
    """Decorate a function to wrap it in a try/except block.

    Args:
        logger: Logger to record the error.
        default_return: Value to return if exception occurs (if not reraising).
        reraise: If True, re-raises the exception after logging.
        context: Static context data to add to the log.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(
            *args: Any, **kwargs: Any
        ) -> Any:  # Returns Any because of default_return
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # 1. Setup Logger
                log = logger or logging.getLogger("pyguara.error")

                # 2. Build Context
                debug_ctx = {"function": func.__name__, "args": args, "kwargs": kwargs}
                if context:
                    debug_ctx.update(context)

                # 3. Log
                log.error(
                    f"Error in {func.__name__}: {e}", extra={"context": debug_ctx}
                )

                # 4. Handle
                if reraise:
                    raise e
                return default_return

        return wrapper

    return decorator


class RetryPolicy:
    """Simple configuration for retry logic."""

    def __init__(
        self, max_attempts: int = 3, delay: float = 0.1, backoff: float = 2.0
    ) -> None:
        """Initialize the retry policy settings."""
        self.max_attempts = max_attempts
        self.delay = delay
        self.backoff = backoff


def retry(policy: Optional[RetryPolicy] = None) -> Callable:
    """Decorate function to retry failing operations (good for IO/Network)."""
    if policy is None:
        policy = RetryPolicy()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            current_delay = policy.delay
            # We assert policy is not None here because of the check above
            # but Mypy within nested scopes can be tricky.
            # However, the outer check ensures it.

            local_policy = policy  # Capture for closure safety
            if local_policy is None:
                # Should satisfy static analysis safety
                raise RuntimeError("Retry policy is missing")

            last_error: Optional[Exception] = None

            for attempt in range(local_policy.max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    # Wait unless it's the last attempt
                    if attempt < local_policy.max_attempts - 1:
                        time.sleep(current_delay)
                        current_delay *= local_policy.backoff

            # If we exhausted retries, raise the last error
            if last_error:
                raise last_error

            # This path is theoretically unreachable if max_attempts > 0,
            # but needed to satisfy return type T
            raise RuntimeError(f"Retry failed for {func.__name__} (Unknown Error)")

        return wrapper

    return decorator
