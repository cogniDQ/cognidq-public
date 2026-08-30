"""Schemas for multi-stage disambiguation sessions (F124 P01)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from app.schemas.nl_rule_builder import StructuredIntermediateRepresentation
from app.schemas.resolution import EntityResolution


class AmbiguityCategory(str, Enum):
    ENTITY = "entity"
    DATASET_SCOPE = "dataset_scope"
    OPERATOR = "operator"
    THRESHOLD = "threshold"
    CHECK_TYPE = "check_type"


class AmbiguitySeverity(str, Enum):
    BLOCKING = "blocking"
    MAJOR = "major"
    MINOR = "minor"


class ClarificationAnswerType(str, Enum):
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    FREE_TEXT = "free_text"
    NUMERIC = "numeric"


class DisambiguationSessionStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class AmbiguityOption(BaseModel):
    option_id: str = Field(..., min_length=1, max_length=200)
    label: str = Field(..., min_length=1, max_length=500)
    value: str = Field(..., min_length=1, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AmbiguityItem(BaseModel):
    ambiguity_id: str = Field(..., min_length=1, max_length=200)
    category: AmbiguityCategory
    severity: AmbiguitySeverity
    reason_code: str = Field(..., min_length=1, max_length=120)
    entity_key: str | None = Field(None, max_length=100)
    confidence: float = Field(..., ge=0.0, le=1.0)
    alternatives: list[AmbiguityOption] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ClarificationQuestion(BaseModel):
    question_id: str = Field(..., min_length=1, max_length=200)
    ambiguity_id: str = Field(..., min_length=1, max_length=200)
    prompt: str = Field(..., min_length=1, max_length=2000)
    answer_type: ClarificationAnswerType
    options: list[AmbiguityOption] = Field(default_factory=list)
    required: bool = True
    rationale: str = Field("", max_length=2000)

    @field_validator("options")
    @classmethod
    def validate_options_for_answer_type(cls, options: list[AmbiguityOption], info):
        answer_type = info.data.get("answer_type")
        if (
            answer_type
            in {ClarificationAnswerType.SINGLE_SELECT, ClarificationAnswerType.MULTI_SELECT}
            and not options
        ):
            raise ValueError("options are required for select-based question types")
        return options


class ClarificationAnswer(BaseModel):
    question_id: str = Field(..., min_length=1, max_length=200)
    selected_option_ids: list[str] = Field(default_factory=list)
    value_text: str | None = Field(None, max_length=5000)
    value_number: float | None = None


class DisambiguationSession(BaseModel):
    session_id: UUID = Field(default_factory=uuid4)
    workspace_id: UUID
    user_id: UUID
    request_text: str = Field(..., min_length=1, max_length=5000)
    parsed_rule_snapshot: dict[str, Any] = Field(default_factory=dict)
    ambiguities: list[AmbiguityItem] = Field(default_factory=list)
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    answers: dict[str, ClarificationAnswer] = Field(default_factory=dict)
    status: DisambiguationSessionStatus = DisambiguationSessionStatus.OPEN
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def register_answer(self, answer: ClarificationAnswer) -> None:
        self.answers[answer.question_id] = answer
        self.updated_at = datetime.now(UTC)

    def cancel(self) -> None:
        self.status = DisambiguationSessionStatus.CANCELLED
        self.updated_at = datetime.now(UTC)

    def resolve(self) -> None:
        self.status = DisambiguationSessionStatus.RESOLVED
        self.updated_at = datetime.now(UTC)


class DisambiguationStartRequest(BaseModel):
    request_text: str = Field(..., min_length=1, max_length=5000)
    parsed_rule: StructuredIntermediateRepresentation
    subject_resolution: EntityResolution | None = None
    object_resolution: EntityResolution | None = None


class DisambiguationStartResponse(BaseModel):
    session: DisambiguationSession
    next_questions: list[ClarificationQuestion] = Field(default_factory=list)


class DisambiguationAnswerRequest(BaseModel):
    answers: list[ClarificationAnswer] = Field(default_factory=list)


class DisambiguationAnswerResponse(BaseModel):
    session_id: UUID
    session_status: DisambiguationSessionStatus
    can_resume_pipeline: bool
    pending_required_question_ids: list[str] = Field(default_factory=list)
    answered_question_ids: list[str] = Field(default_factory=list)


class DisambiguationSessionResponse(BaseModel):
    session: DisambiguationSession
