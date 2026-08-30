"""
Data Quality Rule Models
SQLAlchemy models for DQ rules, executions, and violations.
"""

import uuid

from sqlalchemy import (
    ARRAY,
    DECIMAL,
    TIMESTAMP,
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.user import Base


class DQRule(Base):
    """Data Quality Rule model."""

    __tablename__ = "dq_rules"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Workspace relationship
    workspace_id = Column(UUID(as_uuid=True), nullable=False)

    # Basic info
    name = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(50))  # completeness, validity, conformity, etc.
    rule_type = Column(String(50))  # null_check, regex_check, range_check, etc.

    # Rule definitions
    canonical_rule = Column(JSONB, nullable=False)  # Platform-agnostic JSON
    compiled_sql = Column(Text)  # Generic SQL
    compiled_postgres = Column(Text)  # PostgreSQL-specific
    compiled_mysql = Column(Text)  # MySQL-specific
    compiled_snowflake = Column(Text)  # Snowflake-specific
    compiled_spark = Column(Text)  # PySpark code

    # Target configuration
    data_source_id = Column(UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="SET NULL"))
    target_schema = Column(String(255))
    target_table = Column(String(255))
    target_columns = Column(ARRAY(Text))

    # Status and activation
    status = Column(String(50), default="draft")  # draft, active, inactive, archived
    is_active = Column(Boolean, default=True)

    # Scheduling
    schedule = Column(JSONB)  # Cron expression and config

    # Configuration
    threshold_config = Column(JSONB)  # Pass/fail thresholds
    notification_config = Column(JSONB)  # Notification settings

    # Metadata
    tags = Column(ARRAY(Text))
    meta_data = Column("meta_data", JSONB)  # Using alias to avoid SQLAlchemy reserved word

    # Audit fields
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    data_source = relationship("DataSource", backref="dq_rules")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    owner = relationship("User", foreign_keys=[owner_user_id])
    executions = relationship("RuleExecution", back_populates="rule", cascade="all, delete-orphan")


class RuleExecution(Base):
    """Rule Execution model - tracks each execution of a rule."""

    __tablename__ = "rule_executions"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Rule relationship
    rule_id = Column(
        UUID(as_uuid=True), ForeignKey("dq_rules.id", ondelete="CASCADE"), nullable=False
    )

    # Execution metadata
    execution_type = Column(String(50), nullable=False)  # manual, scheduled, triggered, test

    # Status
    status = Column(String(50), default="pending")  # pending, running, completed, failed, cancelled
    started_at = Column(TIMESTAMP)
    completed_at = Column(TIMESTAMP)
    duration_seconds = Column(Integer)

    # Results
    rows_scanned = Column(BigInteger, default=0)
    rows_passed = Column(BigInteger, default=0)
    rows_failed = Column(BigInteger, default=0)
    pass_rate = Column(DECIMAL(5, 2))  # 0.00 - 100.00

    # Error handling
    error_message = Column(Text)
    error_details = Column(JSONB)

    # Detailed results
    result_details = Column(JSONB)
    execution_params = Column(JSONB)
    environment = Column(JSONB)

    # Audit fields
    executed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    rule = relationship("DQRule", back_populates="executions")
    executor = relationship("User")
    violations = relationship(
        "RuleViolation", back_populates="execution", cascade="all, delete-orphan"
    )


class RuleViolation(Base):
    """Rule Violation model - individual row violations."""

    __tablename__ = "rule_violations"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Execution relationship
    execution_id = Column(
        UUID(as_uuid=True), ForeignKey("rule_executions.id", ondelete="CASCADE"), nullable=False
    )

    # Violation identification
    row_identifier = Column(Text)  # Primary key or unique identifier
    row_number = Column(BigInteger)

    # Violation details
    violation_details = Column(JSONB, nullable=False)

    # Categorization
    severity = Column(String(50))  # blocker, critical, major, minor, info
    category = Column(String(50))

    # Sample flag
    is_sample = Column(Boolean, default=False)

    # Metadata
    meta_data = Column("meta_data", JSONB)
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    execution = relationship("RuleExecution", back_populates="violations")
