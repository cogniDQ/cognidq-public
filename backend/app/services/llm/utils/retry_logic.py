"""
Retry logic with exponential backoff for LLM calls
"""

import asyncio
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError

logger = logging.getLogger(__name__)


class RetryConfig:
    """Configuration for retry behavior"""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 10.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt"""
        import random

        delay = min(self.initial_delay * (self.exponential_base**attempt), self.max_delay)

        if self.jitter:
            # Add random jitter ±25%
            delay = delay * (0.75 + random.random() * 0.5)

        return delay


def retry_on_error(
    retry_config: RetryConfig | None = None,
    retry_exceptions: tuple = (RateLimitError, APIError, APITimeoutError, APIConnectionError),
):
    """
    Decorator for retrying functions with exponential backoff

    Args:
        retry_config: Configuration for retry behavior
        retry_exceptions: Tuple of exception types to retry on
    """
    if retry_config is None:
        retry_config = RetryConfig()

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(retry_config.max_attempts):
                try:
                    return await func(*args, **kwargs)

                except retry_exceptions as e:
                    last_exception = e

                    if attempt < retry_config.max_attempts - 1:
                        delay = retry_config.get_delay(attempt)
                        logger.warning(
                            f"⚠️ Attempt {attempt + 1}/{retry_config.max_attempts} failed: {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"❌ All {retry_config.max_attempts} attempts failed. Last error: {e}"
                        )

                except Exception as e:
                    # Don't retry on other exceptions
                    logger.error(f"❌ Non-retryable error: {e}")
                    raise

            # All retries exhausted
            raise last_exception

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            import time

            last_exception = None

            for attempt in range(retry_config.max_attempts):
                try:
                    return func(*args, **kwargs)

                except retry_exceptions as e:
                    last_exception = e

                    if attempt < retry_config.max_attempts - 1:
                        delay = retry_config.get_delay(attempt)
                        logger.warning(
                            f"⚠️ Attempt {attempt + 1}/{retry_config.max_attempts} failed: {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"❌ All {retry_config.max_attempts} attempts failed. Last error: {e}"
                        )

                except Exception as e:
                    # Don't retry on other exceptions
                    logger.error(f"❌ Non-retryable error: {e}")
                    raise

            # All retries exhausted
            raise last_exception

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


class LLMRetryHandler:
    """Handler for LLM call retries with exponential backoff"""

    def __init__(self, retry_config: RetryConfig | None = None):
        self.retry_config = retry_config or RetryConfig(
            max_attempts=3, initial_delay=2.0, max_delay=10.0
        )

    async def call_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """
        Call function with retry logic

        Args:
            func: Async function to call
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function

        Returns:
            Result from function call

        Raises:
            Last exception if all retries fail
        """
        last_exception = None

        for attempt in range(self.retry_config.max_attempts):
            try:
                result = await func(*args, **kwargs)

                if attempt > 0:
                    logger.info(f"✅ Retry succeeded on attempt {attempt + 1}")

                return result

            except (RateLimitError, APIError, APITimeoutError, APIConnectionError) as e:
                last_exception = e

                if attempt < self.retry_config.max_attempts - 1:
                    delay = self.retry_config.get_delay(attempt)
                    logger.warning(
                        f"⚠️ LLM call failed (attempt {attempt + 1}/{self.retry_config.max_attempts}): {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"❌ LLM call failed after {self.retry_config.max_attempts} attempts. "
                        f"Last error: {e}"
                    )

            except Exception as e:
                # Don't retry on other exceptions
                logger.error(f"❌ Non-retryable LLM error: {e}")
                raise

        # All retries exhausted
        raise last_exception


class CircuitBreaker:
    """
    Circuit breaker pattern for LLM calls
    Prevents cascading failures by temporarily blocking calls after repeated failures
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type[Exception] = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if self.state == "open" and self.last_failure_time:
            import time

            return (time.time() - self.last_failure_time) >= self.recovery_timeout
        return False

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection

        Args:
            func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result from function call

        Raises:
            Exception if circuit is open or function fails
        """
        import time

        # Check if circuit should attempt reset
        if self._should_attempt_reset():
            self.state = "half_open"
            logger.info("🔄 Circuit breaker entering half-open state")

        # Block calls if circuit is open
        if self.state == "open":
            logger.error("🚫 Circuit breaker is OPEN - blocking call")
            raise Exception(
                f"Circuit breaker is open. "
                f"Service unavailable. Retry after {self.recovery_timeout}s"
            )

        try:
            result = await func(*args, **kwargs)

            # Success - reset circuit
            if self.state == "half_open":
                logger.info("✅ Circuit breaker reset to CLOSED state")

            self.failure_count = 0
            self.state = "closed"
            return result

        except self.expected_exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            logger.warning(
                f"⚠️ Circuit breaker failure {self.failure_count}/{self.failure_threshold}"
            )

            # Open circuit if threshold reached
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                logger.error(
                    f"🔴 Circuit breaker OPEN - "
                    f"threshold reached ({self.failure_threshold} failures)"
                )

            raise


# Singleton instances
default_retry_handler = LLMRetryHandler()
llm_circuit_breaker = CircuitBreaker(
    failure_threshold=5, recovery_timeout=60.0, expected_exception=(RateLimitError, APIError)
)
