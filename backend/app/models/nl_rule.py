"""
NL Rule Builder Models
SQLAlchemy models for natural language rule parse requests and results.
"""

import uuid

from sqlalchemy import TIMESTAMP, Boolean, Column, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.user import Base


class NLRuleRequest(Base):
    """Natural language rule parse request."""

    __tablename__ = "nl_rule_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), nullable=False)
    rule_text = Column(Text, nullable=False)
    context = Column(JSONB, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    severity = Column(String(20), nullable=True, default="medium")
    tags = Column(JSONB, nullable=True, default=list)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Relationship
    parse_result = relationship(
        "NLRuleParseResult", back_populates="request", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<NLRuleRequest(id={self.id}, status={self.status})>"


class NLRuleParseResult(Base):
    """Parse result containing the Structured Intermediate Representation."""

    __tablename__ = "nl_rule_parse_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("nl_rule_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    sir_json = Column(JSONB, nullable=False)
    rule_type = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=False)
    requires_disambiguation = Column(Boolean, nullable=False, default=False)
    parse_warnings = Column(JSONB, nullable=True)
    model_version = Column(String(100), nullable=False)
    schema_version = Column(String(10), nullable=False, default="1.0")
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Validation workflow
    validated = Column(Boolean, nullable=False, default=False)
    validated_at = Column(TIMESTAMP(timezone=True), nullable=True)
    validated_by = Column(UUID(as_uuid=True), nullable=True)
    user_adjustments = Column(JSONB, nullable=True)

    # Full check config output
    compiled_config = Column(JSONB, nullable=True)
    check_configs = Column(JSONB, nullable=True)
    detected_datasets = Column(JSONB, nullable=True)
    detected_columns = Column(JSONB, nullable=True)

    # Relationship
    request = relationship("NLRuleRequest", back_populates="parse_result")

    def __repr__(self):
        return f"<NLRuleParseResult(id={self.id}, rule_type={self.rule_type}, confidence={self.confidence})>"
