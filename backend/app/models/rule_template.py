"""
RuleTemplate Model - SQLAlchemy ORM model for DQ rule templates

Pre-built canonical rule definitions with smart defaults covering all 8 DQ dimensions.
"""

from uuid import uuid4

from sqlalchemy import TIMESTAMP, Boolean, Column, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from app.models.user import Base


class RuleTemplate(Base):
    """Pre-built rule template for common data quality check patterns"""

    __tablename__ = "rule_templates"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    dimension = Column(String(50), nullable=False, index=True)
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text, nullable=False)
    category = Column(String(100), nullable=False, index=True)
    tags = Column(JSONB, default=list)
    canonical_rule_template = Column(JSONB, nullable=False)
    default_severity = Column(String(20), nullable=False, default="high")
    default_threshold_pass = Column(Float, nullable=False, default=98.0)
    default_threshold_warn = Column(Float, nullable=True)
    use_count = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
