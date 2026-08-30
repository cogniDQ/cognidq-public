"""
Issue ORM Model — F031 Automatic Issue Creation

Maps to the `public.issues` table created by migration 013_f031_issues.sql.
CHECK constraints are enforced at the database layer; the ORM does not duplicate them.
"""

from uuid import uuid4

from sqlalchemy import TIMESTAMP, Boolean, Column, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class Issue(Base):
    """Automatic data-quality issue raised during flow execution."""

    __tablename__ = "issues"

    # --- Primary key ---
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # --- Tenant scope (cross-schema FK enforced in migration; bare column here) ---
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False)

    # --- Workspace (cross-schema FK enforced in migration; bare column here) ---
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # --- Execution FK (nullable: rule-only executions have no FlowExecution; F6) ---
    flow_execution_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("flow_executions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # --- Optional node-result FK ---
    flow_node_result_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("flow_node_results.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # --- Optional rule FK ---
    rule_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("dq_rules.id", ondelete="SET NULL"),
        nullable=True,
    )

    # --- Optional dataset FK (cross-schema; bare column) ---
    dataset_id = Column(PG_UUID(as_uuid=True), nullable=True)

    # --- Optional assignee FK ---
    assignee_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # --- Classification ---
    issue_type = Column(String(50), nullable=False)
    severity = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False, default="open")

    # --- Content ---
    title = Column(String(500), nullable=False)
    impact_summary = Column(Text, nullable=True)
    resolution_summary = Column(Text, nullable=True)

    # --- Metrics ---
    failure_count = Column(Integer, nullable=True)
    rows_scanned = Column(Integer, nullable=True)
    pass_rate = Column(Numeric(5, 2), nullable=True)

    # --- Timestamps ---
    due_at = Column(TIMESTAMP(timezone=True), nullable=True)
    opened_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    last_seen_at = Column(TIMESTAMP(timezone=True), nullable=True)  # F032
    resolved_at = Column(TIMESTAMP(timezone=True), nullable=True)
    closed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # --- External ticketing (F060) ---
    external_ticket_id = Column(String(255), nullable=True)
    external_ticket_url = Column(Text, nullable=True)
    external_system = Column(String(100), nullable=True)

    # --- Relationships ---
    execution = relationship("FlowExecution", back_populates=None, foreign_keys=[flow_execution_id])
    node_result = relationship(
        "FlowNodeResult", back_populates=None, foreign_keys=[flow_node_result_id]
    )
    rule = relationship("DQRule", back_populates=None, foreign_keys=[rule_id])
    assignee = relationship("User", back_populates=None, foreign_keys=[assignee_id])


class IssueSample(Base):
    """Bounded sample of failing records captured at issue-creation time — F034."""

    __tablename__ = "issue_record_samples"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    issue_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("issues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False)
    captured_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    sample_count = Column(Integer, nullable=False, default=0)
    rows = Column(JSONB, nullable=False, default=list)
    masking_applied = Column(Boolean, nullable=False, default=False)
    masking_threshold = Column(String(20), nullable=True)
