"""
F036 Comment Pydantic Models
=============================

Domain objects, request/response schemas, and timeline structures for
issue comments and the unified activity timeline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class CreateCommentRequest(BaseModel):
    """POST body for adding a comment to an issue."""

    body: str

    @field_validator("body")
    @classmethod
    def body_must_be_valid_length(cls, v: str) -> str:
        stripped = v.strip() if v else ""
        if len(stripped) < 1:
            raise ValueError("Comment body must not be empty.")
        if len(stripped) > 10_000:
            raise ValueError("Comment body must not exceed 10,000 characters.")
        return stripped


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class CommentResponse(BaseModel):
    """Serialised comment returned from the API."""

    model_config = {"from_attributes": True}

    id: UUID
    issue_id: UUID
    author_id: UUID | None = None
    author_name: str | None = None
    body: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


class TimelineEntry(BaseModel):
    """Single entry in the unified issue timeline."""

    entry_type: str  # "comment" | "event"
    id: UUID
    timestamp: datetime
    actor_id: UUID | None = None
    actor_name: str | None = None
    content: dict[str, Any]


class TimelinePage(BaseModel):
    """Paginated timeline response."""

    items: list[TimelineEntry]
    total: int
    page: int
    page_size: int
    has_next: bool
