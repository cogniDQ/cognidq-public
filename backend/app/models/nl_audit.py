"""
NL Rule Audit Trail — SQLAlchemy ORM models.
"""

from uuid import uuid4

from sqlalchemy import (
    TIMESTAMP,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.models.user import Base


class RuleGenerationAudit(Base):
    __tablename__ = "rule_generation_audit"
    __table_args__ = {"schema": "control"}

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False)
    user_id = Column(PG_UUID(as_uuid=True), nullable=False)
    rule_text = Column(Text, nullable=False)
    parse_request_id = Column(PG_UUID(as_uuid=True))
    parsed_sir = Column(JSONB)
    resolution_candidates = Column(JSONB)
    selected_mappings = Column(JSONB)
    user_overrides = Column(JSONB)
    compiled_config = Column(JSONB)
    flow_id = Column(PG_UUID(as_uuid=True))
    compilation_status = Column(String(50))
    model_version = Column(String(100))
    metadata_snapshot_version = Column(Integer, default=1)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())


class RuleUserFeedback(Base):
    __tablename__ = "rule_user_feedback"
    __table_args__ = {"schema": "control"}

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    audit_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("control.rule_generation_audit.id", ondelete="CASCADE"),
        nullable=False,
    )
    feedback_type = Column(String(50), nullable=False)
    entity_role = Column(String(20), nullable=False)
    original_candidate = Column(JSONB)
    selected_candidate = Column(JSONB)
    confidence_at_decision = Column(Float)
    user_comment = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
