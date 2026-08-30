"""
F038 Incident Pydantic Schemas
==============================

Request / response models for manual incident creation.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

VALID_SEVERITIES = frozenset({"critical", "major", "minor", "informational"})
VALID_PRIORITIES = frozenset({"P1", "P2", "P3", "P4"})


class CreateIncidentRequest(BaseModel):
    """Payload for POST /workspaces/{ws}/incidents."""

    title: str
    severity: str
    priority: str
    impact_summary: str | None = None
    owner_id: UUID | None = None
    issue_ids: list[UUID]

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 500:
            raise ValueError("title must be 1–500 characters")
        return v

    @field_validator("severity")
    @classmethod
    def _severity_valid(cls, v: str) -> str:
        if v not in VALID_SEVERITIES:
            raise ValueError(f"severity must be one of {sorted(VALID_SEVERITIES)}")
        return v

    @field_validator("priority")
    @classmethod
    def _priority_valid(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
        return v

    @field_validator("issue_ids")
    @classmethod
    def _issue_ids_not_empty(cls, v: list[UUID]) -> list[UUID]:
        if not v:
            raise ValueError("issue_ids must contain at least one issue")
        return v


class IncidentResponse(BaseModel):
    """Serialised incident returned to API callers."""

    id: UUID
    workspace_id: UUID
    title: str
    severity: str
    priority: str
    status: str
    impact_summary: str | None = None
    resolution_summary: str | None = None
    owner_id: UUID | None = None
    owner_name: str | None = None
    created_by_user_id: UUID | None = None
    created_by_name: str | None = None
    issue_count: int
    opened_at: datetime


class UpdateIncidentRequest(BaseModel):
    """Payload for PATCH /workspaces/{ws}/incidents/{id}."""

    status: str | None = None
    owner_id: UUID | None = None
    impact_summary: str | None = None
    resolution_summary: str | None = None


class LinkIssuesRequest(BaseModel):
    """Payload for POST/DELETE /workspaces/{ws}/incidents/{id}/links."""

    issue_ids: list[UUID]

    @field_validator("issue_ids")
    @classmethod
    def _issue_ids_not_empty(cls, v: list[UUID]) -> list[UUID]:
        if not v:
            raise ValueError("issue_ids must contain at least one issue ID")
        return v


class LinkOperationResponse(BaseModel):
    """Response for link add/remove operations."""

    incident_id: UUID
    issue_count: int
    linked_issue_ids: list[UUID]


class IncidentListItem(BaseModel):
    """Single row in the incident list (F042)."""

    id: UUID
    title: str
    severity: str
    priority: str
    status: str
    impact_summary: str | None = None
    owner_id: UUID | None = None
    owner_name: str | None = None
    created_by_name: str | None = None
    issue_count: int
    has_sla_breach: bool = False
    earliest_due_at: datetime | None = None
    opened_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None


class IncidentPage(BaseModel):
    """Paginated incident list (F042)."""

    items: list[IncidentListItem]
    total: int
    page: int
    page_size: int
    has_next: bool
