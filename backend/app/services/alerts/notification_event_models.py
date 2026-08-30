"""
F045 — Notification Event Pydantic Models
==========================================

Request / response schemas for notification event CRUD.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, validator

VALID_STATUSES = frozenset({"pending", "sent", "failed", "retrying"})


class CreateNotificationEventRequest(BaseModel):
    alert_rule_id: UUID
    alert_channel_id: UUID
    recipient: str
    payload: dict[str, Any] | None = None
    status: str = "pending"
    max_retries: int = 3

    @validator("recipient")
    def recipient_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("recipient must not be blank")
        return v.strip()

    @validator("status")
    def status_valid(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        return v

    @validator("max_retries")
    def max_retries_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("max_retries must be >= 0")
        return v


class UpdateNotificationEventStatusRequest(BaseModel):
    status: str
    last_error: str | None = None
    retry_count: int | None = None

    @validator("status")
    def status_valid(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        return v


class NotificationEventResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    alert_rule_id: UUID
    alert_channel_id: UUID
    recipient: str
    status: str
    payload: dict[str, Any] | None
    retry_count: int
    max_retries: int
    last_error: str | None
    sent_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NotificationEventSummary(BaseModel):
    pending: int = 0
    sent: int = 0
    failed: int = 0
    retrying: int = 0
