"""
F-CONN-CORE — Dataset lifecycle state machine.

Implements the dataset lifecycle defined in
``documentation/planning/full_p0_p1_structured_data_connections_spec.md`` §12.

This module is intentionally **opt-in**: existing repositories continue to set
status fields with raw strings. Code paths that drive a *transition* (e.g.
register a discovered asset, run a check, mark inaccessible, archive) call
:func:`assert_transition` to refuse illegal jumps.

Lifecycle (spec §12):

    discovered
    └→ registered
       └→ active
          ├→ checked       (re-enters ``active`` after a check completes)
          ├→ inaccessible  ──→ active (recovers) / archived
          └→ archived

Plus convenience: any non-archived state may transition to ``archived``.

Legacy values (``draft``, ``inactive``) are accepted as input for backwards
compatibility with existing F005 rows but cannot be the *target* of a
transition driven by this state machine — new code should use the spec states.
"""

from __future__ import annotations

from enum import Enum


class DatasetState(str, Enum):
    # Spec §12
    DISCOVERED = "discovered"
    REGISTERED = "registered"
    ACTIVE = "active"
    CHECKED = "checked"
    INACCESSIBLE = "inaccessible"
    ARCHIVED = "archived"
    # Legacy — accepted as `current` but not as forward target.
    DRAFT = "draft"
    INACTIVE = "inactive"


_TRANSITIONS: dict[DatasetState, frozenset[DatasetState]] = {
    DatasetState.DISCOVERED: frozenset({DatasetState.REGISTERED}),
    DatasetState.REGISTERED: frozenset({DatasetState.ACTIVE}),
    DatasetState.ACTIVE: frozenset({DatasetState.CHECKED, DatasetState.INACCESSIBLE}),
    DatasetState.CHECKED: frozenset({DatasetState.ACTIVE, DatasetState.INACCESSIBLE}),
    DatasetState.INACCESSIBLE: frozenset({DatasetState.ACTIVE}),
    DatasetState.ARCHIVED: frozenset(),  # terminal
    # Legacy bridge: existing 'draft'/'inactive' rows can be promoted into the
    # new lifecycle by registering or activating them.
    DatasetState.DRAFT: frozenset({DatasetState.REGISTERED, DatasetState.ACTIVE}),
    DatasetState.INACTIVE: frozenset({DatasetState.ACTIVE}),
}


class IllegalDatasetTransitionError(ValueError):
    """Raised when an illegal status transition is attempted."""

    def __init__(self, current: DatasetState, target: DatasetState) -> None:
        super().__init__(f"Illegal dataset state transition: {current.value!r} → {target.value!r}")
        self.current = current
        self.target = target


def _coerce(value) -> DatasetState:
    if isinstance(value, DatasetState):
        return value
    try:
        return DatasetState(value)
    except ValueError as exc:  # pragma: no cover — defensive
        raise ValueError(f"Unknown dataset state: {value!r}") from exc


def can_transition(current, target) -> bool:
    """Return True if *current* may transition to *target*."""
    cur = _coerce(current)
    tgt = _coerce(target)
    if cur == tgt:
        return True
    if tgt is DatasetState.ARCHIVED:
        return cur is not DatasetState.ARCHIVED
    return tgt in _TRANSITIONS[cur]


def assert_transition(current, target) -> DatasetState:
    cur = _coerce(current)
    tgt = _coerce(target)
    if not can_transition(cur, tgt):
        raise IllegalDatasetTransitionError(cur, tgt)
    return tgt


def allowed_next(current) -> frozenset[DatasetState]:
    cur = _coerce(current)
    if cur is DatasetState.ARCHIVED:
        return frozenset()
    return _TRANSITIONS[cur] | {DatasetState.ARCHIVED}


__all__ = [
    "DatasetState",
    "IllegalDatasetTransitionError",
    "allowed_next",
    "assert_transition",
    "can_transition",
]
