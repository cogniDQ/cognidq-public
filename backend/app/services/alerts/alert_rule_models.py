"""
F043 Alert Rule Pydantic Schemas
=================================

Request / response models for alert rule CRUD.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

VALID_TRIGGER_TYPES = frozenset(
    {
        "execution_failed",
        "execution_completed",
        "rule_failed",  # F10 — direct rule execution produced rows_failed > 0
        "check_failed",  # F10 — a flow check node produced rows_failed > 0
        "issue_created",
        "issue_overdue",
        "incident_created",
        "incident_status_changed",
    }
)


class CreateAlertRuleRequest(BaseModel):
    """Payload for POST /workspaces/{ws}/alert-rules."""

    name: str
    trigger_type: str
    conditions: dict | None = None
    recipient_user_ids: list[UUID]
    channel_ids: list[UUID] | None = None
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 200:
            raise ValueError("name must be 1–200 characters")
        return v

    @field_validator("trigger_type")
    @classmethod
    def _trigger_type_valid(cls, v: str) -> str:
        if v not in VALID_TRIGGER_TYPES:
            raise ValueError(f"trigger_type must be one of {sorted(VALID_TRIGGER_TYPES)}")
        return v

    @field_validator("recipient_user_ids")
    @classmethod
    def _recipients_not_empty(cls, v: list[UUID]) -> list[UUID]:
        if not v:
            raise ValueError("recipient_user_ids must contain at least one user")
        return v


class UpdateAlertRuleRequest(BaseModel):
    """Payload for PATCH /workspaces/{ws}/alert-rules/{id}."""

    name: str | None = None
    trigger_type: str | None = None
    conditions: dict | None = None
    recipient_user_ids: list[UUID] | None = None
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v or len(v) > 200:
                raise ValueError("name must be 1–200 characters")
        return v

    @field_validator("trigger_type")
    @classmethod
    def _trigger_type_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_TRIGGER_TYPES:
            raise ValueError(f"trigger_type must be one of {sorted(VALID_TRIGGER_TYPES)}")
        return v

    @field_validator("recipient_user_ids")
    @classmethod
    def _recipients_not_empty(cls, v: list[UUID] | None) -> list[UUID] | None:
        if v is not None and not v:
            raise ValueError("recipient_user_ids must contain at least one user")
        return v


class AlertRuleResponse(BaseModel):
    """Serialised alert rule returned to API callers."""

    id: UUID
    workspace_id: UUID
    name: str
    trigger_type: str
    conditions: dict | None = None
    recipient_user_ids: list[str]
    channel_ids: list[str] = []
    enabled: bool
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
