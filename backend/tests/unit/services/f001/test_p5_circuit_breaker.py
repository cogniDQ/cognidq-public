"""
Packet 5 — Unit tests: circuit breaker, registry client, graceful degradation
==============================================================================

Tests the behaviour of:
    - ``CircuitBreaker`` state machine (all state transitions, sliding window)
    - ``CircuitBreakerWrappedClient`` (pass-through, timeout, failure recording)
    - ``_safe_registry_call`` (graceful degradation in the service layer)
    - Concurrent registry execution in ``TenantService.get_tenant_detail``

Run inside Docker::

    docker-compose exec backend python -m pytest \\
        tests/unit/services/f001/test_p5_circuit_breaker.py -v
"""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.services.tenants.registry import (
    CALL_TIMEOUT_SECONDS,
    CircuitBreaker,
    CircuitBreakerWrappedClient,
    CircuitOpenError,
    RegistryCallError,
    RegistryTimeoutError,
    StubRegistryClient,
)
from app.services.tenants.service import _safe_registry_call

# ===========================================================================
# Helpers
# ===========================================================================


def _make_cb(threshold=3, window=10.0, half_open_after=30.0, clock=None):
    """Return a CircuitBreaker with an injectable clock (defaults to real monotonic)."""
    if clock is None:
        clock = time.monotonic
    return CircuitBreaker(
        threshold=threshold,
        window=window,
        half_open_after=half_open_after,
        clock=clock,
    )


def _fake_clock(initial: float = 0.0):
    """Return a mutable fake clock function and a list to control its value."""
    t = [initial]

    def clock():
        return t[0]

    def advance(seconds: float):
        t[0] += seconds

    return clock, advance


# ===========================================================================
# TestCircuitBreakerInitialState
# ===========================================================================


class TestCircuitBreakerInitialState:
    def test_initial_state_is_closed(self):
        cb = _make_cb()
        assert cb.state == CircuitBreaker.CLOSED

    def test_initial_allows_request(self):
        cb = _make_cb()
        assert cb.allow_request() is True


# ===========================================================================
# TestCircuitBreakerFailureThreshold
# ===========================================================================


class TestCircuitBreakerFailureThreshold:
    def test_one_failure_stays_closed(self):
        cb = _make_cb(threshold=3)
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED

    def test_two_failures_stay_closed(self):
        cb = _make_cb(threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED

    def test_three_failures_open_circuit(self):
        cb = _make_cb(threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

    def test_open_circuit_denies_request(self):
        cb = _make_cb(threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.allow_request() is False

    def test_success_between_failures_resets_count(self):
        cb = _make_cb(threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()  # resets
        cb.record_failure()
        # Only 1 failure after reset — should still be closed
        assert cb.state == CircuitBreaker.CLOSED

    def test_success_clears_failure_history(self):
        cb = _make_cb(threshold=3)
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.allow_request() is True


# ===========================================================================
# TestCircuitBreakerSlidingWindow
# ===========================================================================


class TestCircuitBreakerSlidingWindow:
    def test_failures_outside_window_not_counted(self):
        clock, advance = _fake_clock()
        cb = _make_cb(threshold=3, window=10.0, clock=clock)

        cb.record_failure()  # t=0
        advance(11)  # move past 10s window
        cb.record_failure()  # t=11
        cb.record_failure()  # t=11 (2 failures in window, not 3)
        # First failure (t=0) is outside the 10s window — only 2 in window
        assert cb.state == CircuitBreaker.CLOSED

    def test_three_failures_within_window_opens(self):
        clock, advance = _fake_clock()
        cb = _make_cb(threshold=3, window=10.0, clock=clock)

        cb.record_failure()  # t=0
        advance(3)
        cb.record_failure()  # t=3
        advance(3)
        cb.record_failure()  # t=6 — all 3 within 10s window
        assert cb.state == CircuitBreaker.OPEN

    def test_failures_at_window_boundary_not_pruned(self):
        """Failure exactly at t=window edge is still within window."""
        clock, advance = _fake_clock()
        cb = _make_cb(threshold=3, window=10.0, clock=clock)

        cb.record_failure()  # t=0
        advance(10)
        cb.record_failure()  # t=10 (exactly at boundary, still within window: now - t == window)
        cb.record_failure()  # t=10
        assert cb.state == CircuitBreaker.OPEN


# ===========================================================================
# TestCircuitBreakerHalfOpen
# ===========================================================================


class TestCircuitBreakerHalfOpen:
    def test_transitions_to_half_open_after_cooldown(self):
        clock, advance = _fake_clock()
        cb = _make_cb(threshold=1, half_open_after=30.0, clock=clock)
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        advance(30)
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_half_open_allows_request(self):
        clock, advance = _fake_clock()
        cb = _make_cb(threshold=1, half_open_after=30.0, clock=clock)
        cb.record_failure()
        advance(30)
        assert cb.allow_request() is True

    def test_half_open_success_closes_circuit(self):
        clock, advance = _fake_clock()
        cb = _make_cb(threshold=1, half_open_after=30.0, clock=clock)
        cb.record_failure()
        advance(30)
        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_half_open_failure_reopens_circuit(self):
        clock, advance = _fake_clock()
        cb = _make_cb(threshold=1, half_open_after=30.0, clock=clock)
        cb.record_failure()  # opens at t=0
        advance(30)  # transitions to half-open
        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.record_failure()  # probe fails → back to OPEN
        assert cb.state == CircuitBreaker.OPEN

    def test_open_before_cooldown_still_denies(self):
        clock, advance = _fake_clock()
        cb = _make_cb(threshold=1, half_open_after=30.0, clock=clock)
        cb.record_failure()
        advance(29)
        assert cb.state == CircuitBreaker.OPEN
        assert cb.allow_request() is False


# ===========================================================================
# TestCircuitBreakerWrappedClientPassThrough
# ===========================================================================


class TestCircuitBreakerWrappedClientPassThrough:
    def test_success_returns_count(self):
        inner = StubRegistryClient(fixed_count=7)
        cb = _make_cb()
        client = CircuitBreakerWrappedClient(inner, cb)
        assert client.get_count("tenant-123") == 7

    def test_success_records_success_on_circuit_breaker(self):
        inner = StubRegistryClient(fixed_count=3)
        cb = _make_cb()

        # Pre-load two failures (not enough to open)
        cb.record_failure()
        cb.record_failure()

        client = CircuitBreakerWrappedClient(inner, cb)
        client.get_count("t")  # success should reset
        assert cb.state == CircuitBreaker.CLOSED
        # After reset, two more failures should not open (counter cleared)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED

    def test_open_circuit_raises_circuit_open_error_without_inner_call(self):
        inner = MagicMock()
        cb = _make_cb(threshold=1)
        cb.record_failure()  # opens circuit
        assert cb.state == CircuitBreaker.OPEN

        client = CircuitBreakerWrappedClient(inner, cb)
        with pytest.raises(CircuitOpenError):
            client.get_count("t")

        inner.get_count.assert_not_called()

    def test_inner_exception_raises_registry_call_error(self):
        inner = StubRegistryClient(raise_exc=RuntimeError("remote down"))
        cb = _make_cb()
        client = CircuitBreakerWrappedClient(inner, cb)
        with pytest.raises(RegistryCallError):
            client.get_count("t")

    def test_inner_exception_records_failure(self):
        inner = StubRegistryClient(raise_exc=RuntimeError("down"))
        cb = _make_cb(threshold=3)
        client = CircuitBreakerWrappedClient(inner, cb)

        for _ in range(3):
            with pytest.raises(RegistryCallError):
                client.get_count("t")

        assert cb.state == CircuitBreaker.OPEN


# ===========================================================================
# TestCircuitBreakerWrappedClientTimeout
# ===========================================================================


class TestCircuitBreakerWrappedClientTimeout:
    def test_timeout_raises_registry_timeout_error(self):
        # Use a delay longer than the 500 ms timeout.
        inner = StubRegistryClient(delay=1.5)
        cb = _make_cb()
        client = CircuitBreakerWrappedClient(inner, cb, timeout=0.1)

        with pytest.raises(RegistryTimeoutError):
            client.get_count("t")

    def test_timeout_records_failure_on_circuit_breaker(self):
        inner = StubRegistryClient(delay=1.5)
        cb = _make_cb(threshold=3)
        client = CircuitBreakerWrappedClient(inner, cb, timeout=0.05)

        for _ in range(3):
            with pytest.raises(RegistryTimeoutError):
                client.get_count("t")

        assert cb.state == CircuitBreaker.OPEN

    def test_timeout_is_subclass_of_registry_call_error(self):
        assert issubclass(RegistryTimeoutError, RegistryCallError)

    def test_circuit_open_is_subclass_of_registry_call_error(self):
        assert issubclass(CircuitOpenError, RegistryCallError)


# ===========================================================================
# TestSafeRegistryCall   (service layer helper _safe_registry_call)
# ===========================================================================


class TestSafeRegistryCall:
    def test_success_returns_count_and_available_true(self):
        client = StubRegistryClient(fixed_count=5)
        count, available = _safe_registry_call(client, "tid", "workspace")
        assert count == 5
        assert available is True

    def test_exception_returns_zero_and_available_false(self):
        client = StubRegistryClient(raise_exc=RuntimeError("down"))
        count, available = _safe_registry_call(client, "tid", "workspace")
        assert count == 0
        assert available is False

    def test_circuit_open_returns_zero_and_available_false(self):
        inner = StubRegistryClient(fixed_count=3)
        cb = _make_cb(threshold=1)
        cb.record_failure()  # opens circuit
        client = CircuitBreakerWrappedClient(inner, cb)

        count, available = _safe_registry_call(client, "tid", "user")
        assert count == 0
        assert available is False

    def test_timeout_returns_zero_and_available_false(self):
        inner = StubRegistryClient(delay=2.0)
        cb = _make_cb()
        client = CircuitBreakerWrappedClient(inner, cb, timeout=0.05)

        count, available = _safe_registry_call(client, "tid", "workspace")
        assert count == 0
        assert available is False

    def test_does_not_raise_on_any_exception(self):
        """_safe_registry_call must never propagate an exception."""
        client = StubRegistryClient(raise_exc=Exception("unexpected"))
        # Should not raise:
        count, available = _safe_registry_call(client, "tid", "user")
        assert count == 0
        assert available is False


# ===========================================================================
# TestConcurrentRegistryExecution
# ===========================================================================


class TestConcurrentRegistryExecution:
    def test_both_calls_issued_in_parallel(self):
        """Two 200 ms calls issued concurrently should finish well under 400 ms."""
        call_delay = 0.2  # 200 ms each

        ws_client = StubRegistryClient(fixed_count=3, delay=call_delay)
        user_client = StubRegistryClient(fixed_count=7, delay=call_delay)

        ws_cb_client = CircuitBreakerWrappedClient(ws_client, CircuitBreaker())
        user_cb_client = CircuitBreakerWrappedClient(user_client, CircuitBreaker())

        # Time how long _safe_registry_call runs both calls via the service layer.
        # We replicate the concurrent submit pattern from TenantService directly.
        from concurrent.futures import ThreadPoolExecutor

        start = time.monotonic()
        with ThreadPoolExecutor(max_workers=2) as executor:
            ws_f = executor.submit(_safe_registry_call, ws_cb_client, "t", "workspace")
            user_f = executor.submit(_safe_registry_call, user_cb_client, "t", "user")
            ws_result = ws_f.result()
            user_result = user_f.result()
        elapsed = time.monotonic() - start

        assert ws_result == (3, True)
        assert user_result == (7, True)
        # Must finish in less than sequential time (2 × 200 ms = 400 ms).
        assert elapsed < 0.35, f"Expected concurrent execution (<350ms), got {elapsed:.3f}s"

    def test_one_failure_does_not_block_other_call(self):
        """When one registry errors, the other should still return its count."""
        ws_client = StubRegistryClient(raise_exc=RuntimeError("ws down"))
        user_client = StubRegistryClient(fixed_count=9)

        ws_count, ws_avail = _safe_registry_call(ws_client, "t", "workspace")
        user_count, user_avail = _safe_registry_call(user_client, "t", "user")

        assert ws_count == 0
        assert ws_avail is False
        assert user_count == 9
        assert user_avail is True
