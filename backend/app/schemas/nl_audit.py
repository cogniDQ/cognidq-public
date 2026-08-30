"""
NL Rule Audit Trail Pydantic Schemas.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FeedbackType(str, enum.Enum):
    ACCEPTED_MATCH = "accepted_match"
    REJECTED_MATCH = "rejected_match"
    MANUAL_OVERRIDE = "manual_override"
    CORRECTED_RULE = "corrected_rule"


class EntityRole(str, enum.Enum):
    SUBJECT = "subject"
    OBJECT = "object"
    GENERAL = "general"


class AuditRecordCreate(BaseModel):
    rule_text: str = Field(..., min_length=1)
    parse_request_id: str | None = None
    parsed_sir: dict[str, Any] | None = None
    parse_explainability: list[dict[str, Any]] | None = None
    parse_trust_summary: dict[str, Any] | None = None
    resolution_candidates: dict[str, Any] | None = None
    selected_mappings: dict[str, Any] | None = None
    user_overrides: dict[str, Any] | None = None
    compiled_config: dict[str, Any] | None = None
    flow_id: str | None = None
    compilation_status: str | None = None
    model_version: str | None = None
    metadata_snapshot_version: int = 1


class AuditRecordResponse(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    rule_text: str
    parse_request_id: str | None = None
    parsed_sir: dict[str, Any] | None = None
    resolution_candidates: dict[str, Any] | None = None
    selected_mappings: dict[str, Any] | None = None
    user_overrides: dict[str, Any] | None = None
    compiled_config: dict[str, Any] | None = None
    flow_id: str | None = None
    compilation_status: str | None = None
    model_version: str | None = None
    metadata_snapshot_version: int = 1
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class FeedbackCreate(BaseModel):
    feedback_type: FeedbackType
    entity_role: EntityRole = EntityRole.GENERAL
    original_candidate: dict[str, Any] | None = None
    selected_candidate: dict[str, Any] | None = None
    confidence_at_decision: float | None = Field(None, ge=0.0, le=1.0)
    user_comment: str | None = Field(None, max_length=2000)


class FeedbackResponse(BaseModel):
    id: str
    audit_id: str
    feedback_type: str
    entity_role: str
    original_candidate: dict[str, Any] | None = None
    selected_candidate: dict[str, Any] | None = None
    confidence_at_decision: float | None = None
    user_comment: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class ExplainabilityEntry(BaseModel):
    entity_role: str
    column_name: str
    dataset_name: str | None = None
    reason: str
    signal_scores: list[dict[str, Any]] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    was_overridden: bool = False
    override_from: str | None = None
    override_to: str | None = None


class ExplainabilityResponse(BaseModel):
    audit_id: str
    rule_text: str
    parse_explainability: list[dict[str, Any]] = Field(default_factory=list)
    parse_trust_summary: dict[str, Any] | None = None
    explanations: list[ExplainabilityEntry] = Field(default_factory=list)
    feedbacks: list[FeedbackResponse] = Field(default_factory=list)


class AuditListResponse(BaseModel):
    items: list[AuditRecordResponse] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
