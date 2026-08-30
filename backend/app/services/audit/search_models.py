"""
F053 — Audit Log Search Models
================================

Pydantic query-param and response models for the general audit log search.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, validator

from app.services.audit.constants import VALID_ACTION_TYPES, VALID_ENTITY_TYPES


class AuditLogQueryParams(BaseModel):
    """Validated query parameters for the paginated audit-log search."""

    action_type: str | None = None
    entity_type: str | None = None
    actor_id: UUID | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
    sort_dir: str = "desc"
    page: int = 1
    page_size: int = 50

    @validator("action_type")
    def _validate_action_type(cls, v):  # noqa: N805
        if v is not None and v not in VALID_ACTION_TYPES:
            raise ValueError(f"Invalid action_type: {v}")
        return v

    @validator("entity_type")
    def _validate_entity_type(cls, v):  # noqa: N805
        if v is not None and v not in VALID_ENTITY_TYPES:
            raise ValueError(f"Invalid entity_type: {v}")
        return v

    @validator("to_date")
    def _validate_date_range(cls, v, values):  # noqa: N805
        from_date = values.get("from_date")
        if from_date and v and v < from_date:
            raise ValueError("to_date must be after from_date")
        return v


class AuditLogEntry(BaseModel):
    """Single audit-log row returned to the client."""

    log_id: UUID
    occurred_at: datetime
    action_type: str
    actor_id: UUID | None = None
    actor_role: str | None = None
    actor_type: str | None = None
    actor_display_name: str | None = None
    target_entity_type: str | None = None
    target_entity_id: UUID | None = None
    workspace_id: UUID | None = None
    request_id: UUID | None = None


class AuditLogPage(BaseModel):
    """Paginated response envelope."""

    items: list[AuditLogEntry]
    total: int
    page: int
    page_size: int
    has_next: bool
