"""
F055 — Ownership History Models
==================================

Pydantic query-param and response models for the ownership history endpoint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class OwnershipHistoryQueryParams(BaseModel):
    """Validated query parameters for ownership history."""

    entity_type: str | None = None  # e.g. "issue", "incident", "role_assignment"
    entity_id: UUID | None = None  # Filter to a specific entity
    action_type: str | None = None  # Further narrow to one action type
    page: int = 1
    page_size: int = 25


class OwnershipEvent(BaseModel):
    """Single ownership/accountability event from the audit log."""

    log_id: UUID
    occurred_at: datetime
    action_type: str
    target_entity_type: str | None = None
    target_entity_id: UUID | None = None
    actor_id: UUID | None = None
    actor_role: str | None = None
    actor_type: str | None = None
    actor_display_name: str | None = None
    previous_data: dict[str, Any] | None = None
    new_data: dict[str, Any] | None = None
    request_id: UUID | None = None


class OwnershipHistoryPage(BaseModel):
    """Paginated response envelope for ownership history."""

    items: list[OwnershipEvent]
    total: int
    page: int
    page_size: int
    has_next: bool
