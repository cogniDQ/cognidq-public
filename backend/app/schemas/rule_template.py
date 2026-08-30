"""
RuleTemplate Schemas - Pydantic models for rule template API request/response validation.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# ---------- Response schemas ----------


class RuleTemplateListItem(BaseModel):
    """Template summary returned in list endpoints (excludes canonical_rule_template)."""

    id: UUID
    dimension: str
    name: str
    description: str
    category: str
    tags: list[str] = []
    default_severity: str
    default_threshold_pass: float
    default_threshold_warn: float | None = None
    use_count: int = 0
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class RuleTemplateDetail(RuleTemplateListItem):
    """Full template detail including canonical_rule_template."""

    canonical_rule_template: dict[str, Any]
    is_active: bool = True
    updated_at: datetime | None = None


class RuleTemplateListResponse(BaseModel):
    """Wrapper for template list endpoint."""

    templates: list[RuleTemplateListItem]
    total: int


# ---------- Request schemas ----------


class ApplyTemplateRequest(BaseModel):
    """Request body for POST /rule-templates/{id}/apply."""

    target_table: str = Field(..., min_length=1, description="Target table name")
    column_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Map of placeholder tokens to actual column names",
    )
    overrides: dict[str, Any] | None = Field(
        default=None,
        description="Optional overrides for threshold_pass, threshold_warn, severity",
    )


class ApplyTemplateResponse(BaseModel):
    """Response body for POST /rule-templates/{id}/apply."""

    canonical_rule: dict[str, Any]
    template_id: UUID
    template_name: str
