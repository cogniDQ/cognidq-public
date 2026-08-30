"""
F001 — External registry clients + circuit breaker  (Packet 5)
===============================================================

Provides:
    RegistryClient               — Protocol defining the interface every
                                   registry client must satisfy.
    StubRegistryClient           — In-process stub used in tests and as the
                                   default development implementation.
    CircuitBreaker               — Thread-safe state machine per TDD §3.4:
                                   CLOSED → OPEN (3 failures / 10 s window)
                                   → HALF_OPEN (30 s cooldown) → CLOSED.
    CircuitBreakerWrappedClient  — Wraps any RegistryClient with circuit-
                                   breaker logic and a 500 ms hard timeout.

    RegistryCallError            — Base exception; all registry failures.
    RegistryTimeoutError         — Per-call 500 ms timeout exceeded.
    CircuitOpenError             — Fast-fail; circuit is OPEN.

    get_workspace_registry_client() — FastAPI dependency (workspace registry).
    get_user_registry_client()      — FastAPI dependency (user registry).

Circuit breaker parameters (TDD §3.4 — authoritative over §9 which differs):
    FAILURE_THRESHOLD = 3  (consecutive failures in window → OPEN)
    WINDOW_SECONDS    = 10 (sliding failure window)
    HALF_OPEN_AFTER   = 30 (seconds after OPEN before allowing a probe)

Timeout:
    CALL_TIMEOUT_SECONDS = 0.5  (500 ms hard timeout per call)

Design notes:
    • ``CircuitBreakerWrappedClient`` submits each call to a module-level
      ``ThreadPoolExecutor`` so the FastAPI threadpool thread is not blocked
      indefinitely; ``future.result(timeout=…)`` enforces the timeout.
    • One ``CircuitBreakerWrappedClient`` instance per registry is created
      at module import time and injected via FastAPI dependencies.
    • ``StubRegistryClient`` is the default inner client; replace with real
      HTTP clients without changing any call-site code.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Protocol

from sqlalchemy import text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RegistryCallError(Exception):
    """Base exception raised when a registry call fails for any reason."""


class RegistryTimeoutError(RegistryCallError):
    """Raised when a registry call exceeds CALL_TIMEOUT_SECONDS."""


class CircuitOpenError(RegistryCallError):
    """Raised immediately when the circuit breaker is OPEN (fast-fail path)."""


# ---------------------------------------------------------------------------
# Registry client protocol
# ---------------------------------------------------------------------------


class RegistryClient(Protocol):
    """Interface every concrete registry client must implement.

    Implementations make an outbound call (HTTP or otherwise) and return the
    aggregate count of entities linked to the tenant.  Callers must handle
    ``RegistryCallError`` and its subclasses.
    """

    def get_count(self, tenant_id: str) -> int:
        """Return the aggregate count for ``tenant_id``.

        Args:
            tenant_id: UUID string of the tenant.

        Returns:
            Non-negative integer.

        Raises:
            RegistryCallError: On any remote or network error.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Stub client (default / test double)
# ---------------------------------------------------------------------------


class StubRegistryClient:
    """In-process stub for testing and development.

    Configurable to:
    - return a fixed count (default 0),
    - raise a specified exception (for error-path tests),
    - introduce an artificial delay (for timeout tests).

    Attributes:
        fixed_count: Returned by ``get_count`` when not raising.
        raise_exc:   If not None, ``get_count`` raises this instead of returning.
        delay:       Seconds to sleep before acting (tests timeout behaviour).
    """

    def __init__(
        self,
        fixed_count: int = 0,
        raise_exc: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self.fixed_count = fixed_count
        self.raise_exc = raise_exc
        self.delay = delay

    def get_count(self, tenant_id: str) -> int:  # noqa: ARG002
        if self.delay > 0:
            time.sleep(self.delay)
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.fixed_count


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

_CB_FAILURE_THRESHOLD: int = 3
_CB_WINDOW_SECONDS: float = 10.0
_CB_HALF_OPEN_AFTER: float = 30.0


class CircuitBreaker:
    """Thread-safe circuit breaker state machine (TDD §3.4).

    States:
        CLOSED    — Normal path.  Failures are tracked in a sliding window.
        OPEN      — Fast-fail mode.  No calls are attempted until the cooldown
                    expires.
        HALF_OPEN — Cooldown elapsed.  One probe call is allowed through;
                    success → CLOSED, failure → OPEN (fresh cooldown).

    Parameters:
        threshold:       Failures within ``window`` seconds that trigger OPEN.
        window:          Sliding window duration (seconds).
        half_open_after: Seconds after OPEN before transitioning to HALF_OPEN.
        clock:           Monotonic clock callable; injectable for unit-testing.
    """

    CLOSED: str = "CLOSED"
    OPEN: str = "OPEN"
    HALF_OPEN: str = "HALF_OPEN"

    def __init__(
        self,
        threshold: int = _CB_FAILURE_THRESHOLD,
        window: float = _CB_WINDOW_SECONDS,
        half_open_after: float = _CB_HALF_OPEN_AFTER,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = threshold
        self._window = window
        self._half_open_after = half_open_after
        self._clock = clock

        self._state: str = self.CLOSED
        self._failure_times: list[float] = []
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        """Current state (accounts for time-based OPEN → HALF_OPEN transition)."""
        with self._lock:
            return self._effective_state()

    def allow_request(self) -> bool:
        """Return True if a call should be attempted.

        CLOSED and HALF_OPEN → True.
        OPEN → False.
        """
        with self._lock:
            return self._effective_state() != self.OPEN

    def record_success(self) -> None:
        """Record a successful call; clears failure history and closes circuit."""
        with self._lock:
            self._failure_times.clear()
            self._opened_at = None
            self._state = self.CLOSED

    def record_failure(self) -> None:
        """Record a failed call; may transition CLOSED → OPEN."""
        with self._lock:
            now = self._clock()
            self._failure_times.append(now)

            # Prune failures that have fallen outside the sliding window.
            self._failure_times = [t for t in self._failure_times if now - t <= self._window]

            if len(self._failure_times) >= self._threshold:
                self._state = self.OPEN
                self._opened_at = now

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _effective_state(self) -> str:
        """Compute the real current state.  Must be called with ``_lock`` held."""
        if self._state == self.OPEN and self._opened_at is not None:
            if self._clock() - self._opened_at >= self._half_open_after:
                self._state = self.HALF_OPEN
        return self._state


# ---------------------------------------------------------------------------
# Module-level timeout executor
# ---------------------------------------------------------------------------

# Small, dedicated thread pool used only to enforce per-call timeouts.
# Kept separate from FastAPI's own threadpool to avoid contention.
_TIMEOUT_EXECUTOR: ThreadPoolExecutor = ThreadPoolExecutor(
    max_workers=8,
    thread_name_prefix="registry-call",
)

CALL_TIMEOUT_SECONDS: float = 0.5


# ---------------------------------------------------------------------------
# Circuit-breaker-wrapped client
# ---------------------------------------------------------------------------


class CircuitBreakerWrappedClient:
    """Wraps a ``RegistryClient`` with circuit-breaker logic and per-call timeout.

    Call behaviour:
    - OPEN circuit  → raises ``CircuitOpenError`` immediately (no inner call).
    - CLOSED / HALF_OPEN → submits inner call to the timeout executor.
    - Call returns within timeout  → records success; returns count.
    - Timeout exceeded             → records failure; raises ``RegistryTimeoutError``.
    - Inner raises any exception   → records failure; raises ``RegistryCallError``.
    """

    def __init__(
        self,
        inner: RegistryClient,
        circuit_breaker: CircuitBreaker,
        timeout: float = CALL_TIMEOUT_SECONDS,
    ) -> None:
        self._inner = inner
        self._cb = circuit_breaker
        self._timeout = timeout

    def get_count(self, tenant_id: str) -> int:
        """Attempt a registry call with circuit-breaker and timeout protection.

        Raises:
            CircuitOpenError:     Circuit is OPEN; no call was made.
            RegistryTimeoutError: Call exceeded the 500 ms timeout.
            RegistryCallError:    Any other failure from the inner client.
        """
        if not self._cb.allow_request():
            raise CircuitOpenError("Circuit breaker is OPEN — registry call fast-failed.")

        future: Future = _TIMEOUT_EXECUTOR.submit(self._inner.get_count, tenant_id)
        try:
            result: int = future.result(timeout=self._timeout)
        except FuturesTimeoutError:
            future.cancel()
            self._cb.record_failure()
            logger.warning(
                "Registry call timed out after %.1fs for tenant %s",
                self._timeout,
                tenant_id,
            )
            raise RegistryTimeoutError(f"Registry call timed out after {self._timeout}s.")
        except CircuitOpenError:
            raise
        except RegistryCallError:
            self._cb.record_failure()
            raise
        except Exception as exc:
            self._cb.record_failure()
            logger.warning(
                "Registry call failed for tenant %s: %s",
                tenant_id,
                exc,
            )
            raise RegistryCallError(f"Registry call failed: {exc}") from exc
        else:
            self._cb.record_success()
            return result


# ---------------------------------------------------------------------------
# DB-backed registry clients  (F133 P02 — BUG-021)
# ---------------------------------------------------------------------------


class DbWorkspaceRegistryClient:
    """Counts active workspaces belonging to a tenant directly from the DB.

    Creates its own short-lived session so it is safe to call from any thread
    (including the ThreadPoolExecutor used in ``get_tenant_detail``).
    """

    def get_count(self, tenant_id: str) -> int:  # noqa: D102
        from app.models.database import SessionLocal  # local import to avoid cycles

        db = SessionLocal()
        try:
            result = db.execute(
                text(
                    "SELECT COUNT(*) FROM control.workspaces"
                    " WHERE tenant_id = :tid AND status != 'archived'"
                ),
                {"tid": tenant_id},
            )
            row = result.fetchone()
            return int(row[0]) if row else 0
        finally:
            db.close()


class DbUserRegistryClient:
    """Counts distinct users with a workspace role in any of a tenant's workspaces.

    Creates its own short-lived session so it is safe to call from any thread.
    """

    def get_count(self, tenant_id: str) -> int:  # noqa: D102
        from app.models.database import SessionLocal  # local import to avoid cycles

        db = SessionLocal()
        try:
            result = db.execute(
                text(
                    "SELECT COUNT(DISTINCT wra.user_id)"
                    " FROM control.workspace_role_assignments wra"
                    " JOIN control.workspaces w ON w.workspace_id = wra.workspace_id"
                    " WHERE w.tenant_id = :tid AND w.status != 'archived'"
                ),
                {"tid": tenant_id},
            )
            row = result.fetchone()
            return int(row[0]) if row else 0
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Application-level singleton instances
# ---------------------------------------------------------------------------

_workspace_inner = DbWorkspaceRegistryClient()
_workspace_cb = CircuitBreaker()
_default_workspace_client = CircuitBreakerWrappedClient(_workspace_inner, _workspace_cb)

_user_inner = DbUserRegistryClient()
_user_cb = CircuitBreaker()
_default_user_client = CircuitBreakerWrappedClient(_user_inner, _user_cb)


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


def get_workspace_registry_client() -> CircuitBreakerWrappedClient:
    """FastAPI dependency — returns the application workspace registry client."""
    return _default_workspace_client


def get_user_registry_client() -> CircuitBreakerWrappedClient:
    """FastAPI dependency — returns the application user registry client."""
    return _default_user_client
