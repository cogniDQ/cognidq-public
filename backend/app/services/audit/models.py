"""
F052 Audit Domain Models
========================

Dataclasses used by the audit service to represent audit entries and
the actor/request context surrounding a mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.services.audit.constants import SENSITIVE_FIELDS

# ---------------------------------------------------------------------------
# AuditEntry — the data written to the audit log
# ---------------------------------------------------------------------------


@dataclass
class AuditEntry:
    """One audit log row to be persisted.

    Required fields are positional; optional fields have defaults.
    """

    tenant_id: UUID
    action_type: str
    target_entity_type: str
    target_entity_id: UUID
    after_state: dict[str, Any]
    actor_type: str = "user"
    actor_role: str = ""
    workspace_id: UUID | None = None
    actor_id: UUID | None = None
    before_state: dict[str, Any] | None = None
    request_id: UUID | None = None
    source_ip: str | None = None


# ---------------------------------------------------------------------------
# AuditContext — caller identity + request metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditContext:
    """Immutable snapshot of the actor and request metadata.

    Constructed once per request and threaded through the service layer.
    """

    tenant_id: UUID
    actor_id: UUID | None
    actor_type: str  # "user" | "system"
    actor_role: str
    request_id: UUID | None
    source_ip: str | None

    @classmethod
    def from_workspace_actor(
        cls,
        actor: Any,  # WorkspaceActorContext — Any to avoid circular import
        request_id: UUID | None = None,
        source_ip: str | None = None,
    ) -> AuditContext:
        """Build context from a ``WorkspaceActorContext`` (user-initiated)."""
        return cls(
            tenant_id=actor.tenant_id,
            actor_id=actor.actor_id,
            actor_type="user",
            actor_role=actor.actor_role,
            request_id=request_id,
            source_ip=source_ip,
        )

    @classmethod
    def for_system(cls, tenant_id: UUID) -> AuditContext:
        """Build context for a system-initiated action (no human actor)."""
        return cls(
            tenant_id=tenant_id,
            actor_id=None,
            actor_type="system",
            actor_role="system",
            request_id=None,
            source_ip=None,
        )


# ---------------------------------------------------------------------------
# Utility: compute_audit_diff
# ---------------------------------------------------------------------------


def compute_audit_diff(
    before: dict[str, Any],
    after: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return ``(before_changes, after_changes)`` containing only fields that differ.

    Returns ``(None, {})`` when *before* and *after* are identical (no-op).
    """
    changed_before: dict[str, Any] = {}
    changed_after: dict[str, Any] = {}

    all_keys = set(before) | set(after)
    for key in all_keys:
        old_val = before.get(key)
        new_val = after.get(key)
        if old_val != new_val:
            changed_before[key] = old_val
            changed_after[key] = new_val

    if not changed_after:
        return None, {}

    return changed_before, changed_after


# ---------------------------------------------------------------------------
# Utility: strip_sensitive_fields
# ---------------------------------------------------------------------------


def strip_sensitive_fields(
    data: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Recursively remove keys in ``SENSITIVE_FIELDS`` from *data*.

    Returns ``None`` when *data* is ``None``.
    """
    if data is None:
        return None

    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if key in SENSITIVE_FIELDS:
            continue
        if isinstance(value, dict):
            cleaned[key] = strip_sensitive_fields(value)
        else:
            cleaned[key] = value
    return cleaned
