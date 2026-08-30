"""
F134 P03 — Admin approve/reject/list Pydantic schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, model_validator

from app.services.sandbox.validation.approval_validation import (
    validate_approval,
)
from app.services.sandbox.validation.rejection_validation import validate_rejection


class ApproveRequestBody(BaseModel):
    """POST /api/v1/admin/demo-requests/{id}/approve"""

    template_id: str
    duration_days: int = 7
    access_profile_code: str = "mvp_default"
    tags: list[str] | None = None
    internal_note: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> ApproveRequestBody:
        errors = validate_approval(
            template_id=self.template_id,
            duration_days=self.duration_days,
            access_profile_code=self.access_profile_code,
            tags=self.tags,
        )
        if errors:
            msg = "; ".join(f"{f}: {m}" for f, m in errors)
            raise ValueError(msg)
        return self


class RejectRequestBody(BaseModel):
    """POST /api/v1/admin/demo-requests/{id}/reject"""

    reason: str
    internal_note: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> RejectRequestBody:
        errors = validate_rejection(reason=self.reason)
        if errors:
            raise ValueError(errors[0][1])
        return self


class DemoRequestAdminListItem(BaseModel):
    """Row in GET /api/v1/admin/demo-requests list response."""

    id: UUID
    status: str
    work_email: str
    first_name: str
    last_name: str
    company_name: str
    team_size: str
    country: str | None
    is_personal_email: bool
    admin_tags: list[str]
    created_at: datetime
    decided_at: datetime | None

    model_config = {"from_attributes": True}


class DemoRequestAdminDetail(DemoRequestAdminListItem):
    """Full detail for GET /api/v1/admin/demo-requests/{id}."""

    job_title: str | None
    primary_use_case: str
    stack: dict[str, Any] | None
    heard_about_us: str | None
    internal_note: str | None
    rejection_reason: str | None
    decided_by: UUID | None
    sandbox_id: UUID | None = None

    model_config = {"from_attributes": True}


class DemoRequestListResponse(BaseModel):
    """Paginated list of demo requests."""

    items: list[DemoRequestAdminListItem]
    total: int
    limit: int
    offset: int
