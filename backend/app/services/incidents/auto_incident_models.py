"""
F039 — Automatic Incident Policy Models
==========================================

Defines the policy configuration and severity helpers for automatic
incident creation based on issue severity, recurrence, and SLA criteria.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

# Severity ordering (lower number = more severe)
_SEVERITY_RANK = {
    "critical": 0,
    "major": 1,
    "minor": 2,
    "informational": 3,
}

# Default priority mapping by severity
_SEVERITY_PRIORITY = {
    "critical": "P1",
    "major": "P2",
    "minor": "P3",
    "informational": "P4",
}


@dataclass(slots=True, frozen=True)
class IncidentPolicy:
    """Workspace-level policy for automatic incident creation.

    When ``enabled`` is True, the system evaluates newly-created (or grouped)
    issues and auto-creates an incident when all non-None thresholds are met.
    """

    enabled: bool = False
    min_severity: str = "critical"
    recurrence_threshold: int = 1
    auto_priority: str | None = None  # None = derive from severity
    auto_owner_user_id: UUID | None = None

    def severity_met(self, issue_severity: str) -> bool:
        """Return True if the issue's severity meets or exceeds the minimum."""
        issue_rank = _SEVERITY_RANK.get(issue_severity, 99)
        min_rank = _SEVERITY_RANK.get(self.min_severity, 0)
        return issue_rank <= min_rank

    def recurrence_met(self, failure_count: int) -> bool:
        """Return True when the issue's failure_count >= threshold."""
        return failure_count >= self.recurrence_threshold

    def derive_priority(self, issue_severity: str) -> str:
        """Return the priority to assign to an auto-created incident."""
        if self.auto_priority:
            return self.auto_priority
        return _SEVERITY_PRIORITY.get(issue_severity, "P3")


# Module-level dataclass default — DISABLED. Used by
# `AutoIncidentService.evaluate_and_create(policy=None)` so that callers that
# explicitly omit a policy do not auto-create incidents (preserves the
# unit-test contract that an absent policy is a no-op).
DEFAULT_INCIDENT_POLICY = IncidentPolicy()

# Shipping default — ENABLED with a sane threshold (major+ severity, single
# occurrence). Used by the workspace settings layer when a workspace has
# never explicitly configured an incident policy. Operators can still
# override per workspace via PATCH /workspaces/{id}/settings.
SHIPPING_DEFAULT_INCIDENT_POLICY = IncidentPolicy(
    enabled=True,
    min_severity="major",
    recurrence_threshold=1,
)
