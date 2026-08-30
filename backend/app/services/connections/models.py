"""
F130 — Connections domain models (dataclasses).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Connection:
    """Represents a tenant-scoped data source (Connection)."""

    data_source_id: UUID
    tenant_id: UUID
    workspace_id: UUID | None  # legacy field; kept for backward compatibility
    source_name: str
    source_type: str
    connection_mode: str
    environment: str
    description: str | None
    status: str
    credential_reference: UUID | None
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None
    updated_by: UUID | None


@dataclass
class WorkspaceAssignment:
    """Represents a workspace assigned to a tenant-scoped connection."""

    connection_id: UUID
    workspace_id: UUID
    assigned_at: datetime
    assigned_by: UUID | None = None
