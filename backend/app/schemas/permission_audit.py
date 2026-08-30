"""
F008 — Permission Audit Visibility — Pydantic Schemas
======================================================

Schemas for the permission audit read endpoints:
  - PermissionAuditQueryParams  : validated query parameters for list and export
  - PermissionAuditEntry        : one audit log row returned to the caller
  - PermissionAuditPage         : paginated list response envelope
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Access-control action type subset
# ---------------------------------------------------------------------------
# Imported by service and repository to enforce the constant in one place.
ACCESS_CONTROL_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "role_assigned",
        "role_revoked",
        "user_profile_updated",
        "user_password_changed",
        "team_member_added",
        "team_member_updated",
        "team_member_removed",
        "team_created",
        "team_updated",
        "team_deleted",
    }
)

_SORTED_ACCESS_CONTROL_TYPES = sorted(ACCESS_CONTROL_ACTION_TYPES)


# ---------------------------------------------------------------------------
# Query parameters
# ---------------------------------------------------------------------------


class PermissionAuditQueryParams(BaseModel):
    actor_id: UUID | None = Field(None, description="Filter by actor (user) UUID")
    action_type: str | None = Field(None, description="Filter by access-control action type")
    target_entity_id: UUID | None = Field(None, description="Filter by target entity UUID")
    target_entity_type: str | None = Field(
        None, max_length=50, description="Filter by target entity type"
    )
    from_date: datetime | None = Field(None, description="Inclusive lower bound on occurred_at")
    to_date: datetime | None = Field(None, description="Inclusive upper bound on occurred_at")
    sort_dir: str = Field("desc", description="Sort direction: 'asc' or 'desc'")
    page: int = Field(1, ge=1, description="Page number (1-based)")
    page_size: int = Field(25, ge=1, le=100, description="Items per page (1–100)")

    @field_validator("action_type", mode="before")
    @classmethod
    def validate_action_type(cls, v: str | None) -> str | None:
        if v is not None and v not in ACCESS_CONTROL_ACTION_TYPES:
            raise ValueError(
                f"Invalid action_type '{v}'. Must be one of: "
                + ", ".join(_SORTED_ACCESS_CONTROL_TYPES)
            )
        return v

    @field_validator("sort_dir", mode="before")
    @classmethod
    def validate_sort_dir(cls, v: str) -> str:
        if v not in ("asc", "desc"):
            raise ValueError("sort_dir must be 'asc' or 'desc'")
        return v

    @model_validator(mode="after")
    def validate_date_range(self) -> PermissionAuditQueryParams:
        if (
            self.from_date is not None
            and self.to_date is not None
            and self.to_date < self.from_date
        ):
            raise ValueError("to_date must not be earlier than from_date")
        return self


class PermissionAuditExportQueryParams(BaseModel):
    """Filter parameters for the export endpoint (no page/page_size/sort_dir)."""

    actor_id: UUID | None = None
    action_type: str | None = None
    target_entity_id: UUID | None = None
    target_entity_type: str | None = Field(None, max_length=50)
    from_date: datetime | None = None
    to_date: datetime | None = None

    @field_validator("action_type", mode="before")
    @classmethod
    def validate_action_type(cls, v: str | None) -> str | None:
        if v is not None and v not in ACCESS_CONTROL_ACTION_TYPES:
            raise ValueError(
                f"Invalid action_type '{v}'. Must be one of: "
                + ", ".join(_SORTED_ACCESS_CONTROL_TYPES)
            )
        return v

    @model_validator(mode="after")
    def validate_date_range(self) -> PermissionAuditExportQueryParams:
        if (
            self.from_date is not None
            and self.to_date is not None
            and self.to_date < self.from_date
        ):
            raise ValueError("to_date must not be earlier than from_date")
        return self


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class PermissionAuditEntry(BaseModel):
    log_id: UUID
    occurred_at: datetime
    action_type: str
    actor_id: UUID | None
    actor_display_name: str | None
    actor_role: str
    actor_type: str
    target_entity_type: str | None
    target_entity_id: UUID | None
    target_display_name: str | None
    workspace_id: UUID | None
    request_id: UUID | None

    class Config:
        from_attributes = True


class PermissionAuditPage(BaseModel):
    items: list[PermissionAuditEntry]
    total: int
    page: int
    page_size: int
    has_next: bool
