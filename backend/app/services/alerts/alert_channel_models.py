"""
F044 Alert Channel Pydantic Schemas
=====================================

Request / response models for alert channel CRUD.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

VALID_CHANNEL_TYPES = frozenset({"email", "webhook", "slack"})


class CreateAlertChannelRequest(BaseModel):
    """Payload for POST /workspaces/{ws}/alert-channels."""

    name: str
    channel_type: str
    configuration: dict = {}
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 200:
            raise ValueError("name must be 1–200 characters")
        return v

    @field_validator("channel_type")
    @classmethod
    def _channel_type_valid(cls, v: str) -> str:
        if v not in VALID_CHANNEL_TYPES:
            raise ValueError(f"channel_type must be one of {sorted(VALID_CHANNEL_TYPES)}")
        return v


class UpdateAlertChannelRequest(BaseModel):
    """Payload for PATCH /workspaces/{ws}/alert-channels/{id}."""

    name: str | None = None
    channel_type: str | None = None
    configuration: dict | None = None
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v or len(v) > 200:
                raise ValueError("name must be 1–200 characters")
        return v

    @field_validator("channel_type")
    @classmethod
    def _channel_type_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_CHANNEL_TYPES:
            raise ValueError(f"channel_type must be one of {sorted(VALID_CHANNEL_TYPES)}")
        return v


class AlertChannelResponse(BaseModel):
    """Serialised alert channel returned to API callers."""

    id: UUID
    workspace_id: UUID
    name: str
    channel_type: str
    configuration: dict
    enabled: bool
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
