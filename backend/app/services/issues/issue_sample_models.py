"""
Pydantic domain models for F034 — Record Sample Capture and Masking.

Service-layer contract; independent of ORM for pure-unit testability.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class SampleDomain(BaseModel):
    """Full domain representation of a captured record sample."""

    id: UUID | None = None
    issue_id: UUID
    workspace_id: UUID
    captured_at: datetime | None = None
    sample_count: int = 0
    rows: list[dict[str, Any]] = []
    masking_applied: bool = False
    masking_threshold: str | None = None

    model_config = {"from_attributes": True}
