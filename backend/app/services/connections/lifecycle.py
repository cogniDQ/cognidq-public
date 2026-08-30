"""
F-CONN-CORE — Connection lifecycle state machine.

Implements the connection lifecycle defined in
``documentation/planning/full_p0_p1_structured_data_connections_spec.md`` §11.

This module is intentionally **opt-in**: existing repositories continue to set
status fields with raw strings. Code paths that drive a *transition* (e.g. test
connection, run discovery, archive) call :func:`assert_transition` to refuse
illegal jumps.

Persisted on disk as the lowercase ``snake_case`` value of the enum (matches
the CHECK constraint added by migration 042).

Lifecycle (spec §11):

    draft
    └→ created
       ├→ test_failed   ──→ created (retry) / archived
       └→ test_successful
          └→ discovery_available
             └→ active
                ├→ disabled  ──→ active (re-enable) / archived
                └→ archived

Plus convenience: any state may transition to ``archived`` (terminal).
"""

from __future__ import annotations

from enum import Enum


class ConnectionState(str, Enum):
    DRAFT = "draft"
    CREATED = "created"
    TEST_FAILED = "test_failed"
    TEST_SUCCESSFUL = "test_successful"
    DISCOVERY_AVAILABLE = "discovery_available"
    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


# Allowed forward transitions (excluding the universal ``→ archived``).
_TRANSITIONS: dict[ConnectionState, frozenset[ConnectionState]] = {
    ConnectionState.DRAFT: frozenset({ConnectionState.CREATED}),
    ConnectionState.CREATED: frozenset(
        {ConnectionState.TEST_FAILED, ConnectionState.TEST_SUCCESSFUL}
    ),
    ConnectionState.TEST_FAILED: frozenset(
        {ConnectionState.CREATED, ConnectionState.TEST_SUCCESSFUL}
    ),
    ConnectionState.TEST_SUCCESSFUL: frozenset(
        {ConnectionState.DISCOVERY_AVAILABLE, ConnectionState.ACTIVE}
    ),
    ConnectionState.DISCOVERY_AVAILABLE: frozenset({ConnectionState.ACTIVE}),
    ConnectionState.ACTIVE: frozenset({ConnectionState.DISABLED}),
    ConnectionState.DISABLED: frozenset({ConnectionState.ACTIVE}),
    ConnectionState.ARCHIVED: frozenset(),  # terminal
}


class IllegalConnectionTransitionError(ValueError):
    """Raised when an illegal status transition is attempted."""

    def __init__(self, current: ConnectionState, target: ConnectionState) -> None:
        super().__init__(
            f"Illegal connection state transition: {current.value!r} → {target.value!r}"
        )
        self.current = current
        self.target = target


def _coerce(value) -> ConnectionState:
    if isinstance(value, ConnectionState):
        return value
    try:
        return ConnectionState(value)
    except ValueError as exc:  # pragma: no cover — defensive
        raise ValueError(f"Unknown connection state: {value!r}") from exc


def can_transition(current, target) -> bool:
    """Return True if *current* may transition to *target*."""
    cur = _coerce(current)
    tgt = _coerce(target)
    if cur == tgt:
        return True  # idempotent
    if tgt is ConnectionState.ARCHIVED:
        return cur is not ConnectionState.ARCHIVED  # archived is terminal
    return tgt in _TRANSITIONS[cur]


def assert_transition(current, target) -> ConnectionState:
    """Raise :class:`IllegalConnectionTransitionError` if the move is illegal.

    Returns the validated target state on success (so callers can write
    ``row.status = assert_transition(row.status, target).value``).
    """
    cur = _coerce(current)
    tgt = _coerce(target)
    if not can_transition(cur, tgt):
        raise IllegalConnectionTransitionError(cur, tgt)
    return tgt


def allowed_next(current) -> frozenset[ConnectionState]:
    """Return the set of states reachable from *current* in one hop."""
    cur = _coerce(current)
    if cur is ConnectionState.ARCHIVED:
        return frozenset()
    return _TRANSITIONS[cur] | {ConnectionState.ARCHIVED}


__all__ = [
    "ConnectionState",
    "IllegalConnectionTransitionError",
    "allowed_next",
    "assert_transition",
    "can_transition",
]
