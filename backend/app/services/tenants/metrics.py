"""
F001 — Metric emission stubs  (TDD §8.1)
==========================================

Fire-and-forget counters.  A metric failure MUST NEVER propagate to the
caller — every function wraps its body in ``try/except Exception``.

In production these stubs are replaced by real Prometheus / StatsD counter
increments.  The fire-and-forget contract is identical regardless of the
underlying implementation.

All four counters defined in TDD §8.1 are implemented here:

| Metric name                         | Labels                    |
|-------------------------------------|---------------------------|
| ``tenant_create_success_count``     | region, plan, initial_status |
| ``tenant_create_failure_count``     | failure_reason            |
| ``tenant_status_change_count``      | from_status, to_status    |
| ``session_invalidation_sla_breach_count`` | tenant_id           |
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def emit_tenant_create_success(region: str, plan: str, initial_status: str) -> None:
    """Increment ``tenant_create_success_count`` (fire-and-forget)."""
    try:
        logger.debug(
            "metric: tenant_create_success_count region=%s plan=%s status=%s",
            region,
            plan,
            initial_status,
        )
    except Exception:  # pragma: no cover
        pass


def emit_tenant_create_failure(failure_reason: str) -> None:
    """Increment ``tenant_create_failure_count`` (fire-and-forget)."""
    try:
        logger.debug(
            "metric: tenant_create_failure_count reason=%s",
            failure_reason,
        )
    except Exception:  # pragma: no cover
        pass


def emit_tenant_status_change(from_status: str, to_status: str) -> None:
    """Increment ``tenant_status_change_count {from_status, to_status}`` (fire-and-forget).

    TDD §8.1: Counter with labels ``from_status`` and ``to_status``.
    Emitted after a status transition commits successfully.
    """
    try:
        logger.debug(
            "metric: tenant_status_change_count from=%s to=%s",
            from_status,
            to_status,
        )
    except Exception:  # pragma: no cover
        pass


def emit_session_invalidation_sla_breach(tenant_id: str) -> None:
    """Increment ``session_invalidation_sla_breach_count {tenant_id}`` (fire-and-forget).

    TDD §8.1: Counter with label ``tenant_id``.
    Emitted by the outbox poller when a ``TenantSuspendedEvent`` remains
    undelivered past the 30-second SLA window.
    """
    try:
        logger.warning(
            "metric: session_invalidation_sla_breach_count tenant_id=%s",
            tenant_id,
        )
    except Exception:  # pragma: no cover
        pass
