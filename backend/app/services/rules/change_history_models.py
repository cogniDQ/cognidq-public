"""
F054 — Rule Change History Models
====================================

Pydantic query-param and response models for rule change history.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class RuleChangeQueryParams(BaseModel):
    """Validated query parameters for rule change history."""

    action_type: str | None = None  # e.g. rule_created, rule_updated, rule_deleted
    page: int = 1
    page_size: int = 25


class RuleChangeEntry(BaseModel):
    """Single rule change event from the audit log."""

    log_id: int
    occurred_at: datetime
    action_type: str
    actor_id: UUID | None = None
    actor_role: str | None = None
    actor_type: str | None = None
    actor_display_name: str | None = None
    previous_data: dict[str, Any] | None = None
    new_data: dict[str, Any] | None = None
    request_id: str | None = None


class RuleChangePage(BaseModel):
    """Paginated response envelope for rule change history."""

    items: list[RuleChangeEntry]
    total: int
    page: int
    page_size: int
    has_next: bool
    rule_id: UUID
