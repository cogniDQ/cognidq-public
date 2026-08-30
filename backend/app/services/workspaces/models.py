"""
F002 — Workspace domain models
================================

Defines the ``Workspace`` and ``WorkspaceAuditLog`` data classes and the
``WorkspaceStatus`` enum.  These are plain Python objects with no database
or HTTP dependencies; every layer from repository to controller uses them.

Design notes
------------
* ``@dataclass`` with ``slots=True`` (Python ≥ 3.10) is used for memory
  efficiency and attribute typo protection.  If the project targets Python
  3.9, remove ``slots=True``.
* All UUID fields are stored as ``uuid.UUID`` objects inside the domain
  model; the repository casts the string representation returned by
  PostgreSQL back to ``uuid.UUID`` at the boundary.
* ``workspace_name_lower`` is included so that the repository can write the
  column without extra computation.  It is **never** serialised into API
  responses (enforced at the HTTP layer).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


class WorkspaceStatus(str, enum.Enum):
    """Mirrors the ``workspace_status_enum`` PostgreSQL ENUM type."""

    active = "active"
    archived = "archived"
    suspended = "suspended"


@dataclass(slots=True)
class Workspace:
    """
    Domain model for a row in ``control.workspaces``.

    Field names and types mirror TDD §3.1.1 exactly.
    ``workspace_id`` is ``None`` until the repository assigns it on INSERT.
    """

    tenant_id: UUID
    workspace_name: str
    workspace_name_lower: str
    workspace_slug: str
    default_timezone: str
    created_at: datetime
    updated_at: datetime
    created_by: UUID
    updated_by: UUID
    # fields with defaults must come after fields without defaults
    workspace_id: UUID | None = None
    description: str | None = None
    status: WorkspaceStatus = WorkspaceStatus.active
    status_reason: str | None = None
    version: int = 0


@dataclass(slots=True)
class WorkspaceAuditLog:
    """
    Domain model for a row in ``control.workspace_audit_logs``.

    Field names and types mirror TDD §3.1.2 exactly.
    ``log_id`` is ``None`` until the repository assigns it on INSERT.

    ``previous_data`` is ``None`` for ``workspace_created`` events.
    ``new_data`` must never contain ``workspace_name_lower`` or ``version``
    — the ``AuditLogWriter`` strips those keys before writing (TDD §9.3).
    """

    tenant_id: UUID
    workspace_id: UUID
    action_type: str
    actor_id: UUID
    actor_role: str
    new_data: dict[str, Any]
    occurred_at: datetime
    log_id: UUID | None = None
    previous_data: dict[str, Any] | None = None
    request_id: UUID | None = None
    source_ip: str | None = None
