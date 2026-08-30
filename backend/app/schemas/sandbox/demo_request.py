"""
F134 P03 — Public intake Pydantic schemas for demo requests.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, model_validator

from app.services.sandbox.validation.demo_request_validation import (
    validate_company_name,
    validate_consent,
    validate_country,
    validate_name,
    validate_primary_use_case,
    validate_team_size,
    validate_work_email,
)


class DemoRequestCreate(BaseModel):
    """Request body for POST /api/v1/demo-requests."""

    work_email: str
    first_name: str
    last_name: str
    company_name: str
    job_title: str | None = None
    team_size: str
    country: str | None = None
    primary_use_case: str
    stack: dict[str, Any] | None = None
    heard_about_us: str | None = None
    consent: bool

    @model_validator(mode="after")
    def _run_validation(self) -> DemoRequestCreate:
        errors = []
        errors.extend(validate_work_email(self.work_email or ""))
        errors.extend(validate_name(self.first_name or "", "first_name"))
        errors.extend(validate_name(self.last_name or "", "last_name"))
        errors.extend(validate_company_name(self.company_name or ""))
        errors.extend(validate_team_size(self.team_size or ""))
        errors.extend(validate_primary_use_case(self.primary_use_case or ""))
        errors.extend(validate_consent(self.consent))
        errors.extend(validate_country(self.country))
        if errors:
            msg = "; ".join(f"{f}: {m}" for f, m in errors)
            raise ValueError(msg)
        return self


class DemoRequestStatusResponse(BaseModel):
    """Response for GET /api/v1/demo-request-status/{token}."""

    request_id: UUID
    status: str
    created_at: datetime
    decided_at: datetime | None = None
    is_personal_email: bool

    model_config = {"from_attributes": True}


class DemoRequestCreatedResponse(BaseModel):
    """Response for successful POST /api/v1/demo-requests."""

    request_id: UUID
    public_status_token: str
    status: str
    is_personal_email: bool

    model_config = {"from_attributes": True}


class DuplicateRequestResponse(BaseModel):
    """Response when a duplicate active request is detected."""

    status: str = "duplicate"
    request_id: UUID
