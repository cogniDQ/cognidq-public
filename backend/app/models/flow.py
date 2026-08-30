"""
Flow Models - SQLAlchemy ORM models for Flow Builder

This module defines the database models for:
- DQFlow: Visual flow definitions
- FlowExecution: Flow execution records
- FlowNodeResult: Individual node execution results
- FlowTemplate: Pre-built flow templates
"""

from uuid import uuid4

from sqlalchemy import (
    ARRAY,
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class DQFlow(Base):
    """Visual flow definition for data quality checks"""

    __tablename__ = "dq_flows"

    # Primary key
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Workspace relationship
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False)

    # Flow metadata
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Flow definition (nodes + connections)
    flow_definition = Column(JSONB, nullable=False)
    # Structure: {
    #   "nodes": [
    #     { "id": "source-1", "type": "source", "config": {...}, "position": {"x": 100, "y": 100} },
    #     { "id": "check-1", "type": "check", "checkType": "completeness", "config": {...} }
    #   ],
    #   "connections": [
    #     { "id": "conn-1", "from": "source-1", "to": "check-1" }
    #   ]
    # }

    # Status and activation
    status = Column(
        String(50), default="draft", nullable=False
    )  # draft, active, inactive, archived
    is_active = Column(Boolean, default=True)

    # Scheduling
    schedule = Column(JSONB)  # { "enabled": true, "cron": "0 2 * * *", "timezone": "UTC" }

    # Metadata
    tags = Column(ARRAY(Text))
    version = Column(Integer, default=1)

    # Audit fields
    created_by = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    owner_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    owner = relationship("User", foreign_keys=[owner_user_id])
    executions = relationship("FlowExecution", back_populates="flow", cascade="all, delete-orphan")

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'inactive', 'archived')", name="check_flow_status"
        ),
        Index("idx_flows_workspace", "workspace_id"),
        Index("idx_flows_status", "status"),
        Index("idx_flows_created_by", "created_by"),
        Index("idx_flows_created_at", "created_at"),
        Index("idx_flows_tags", "tags", postgresql_using="gin"),
        Index("idx_flows_definition", "flow_definition", postgresql_using="gin"),
        # Unique constraint on flow name per organization
        # Note: This is handled in migration as CONSTRAINT unique_flow_name_per_org
    )

    def __repr__(self):
        return f"<DQFlow(id={self.id}, name='{self.name}', status='{self.status}')>"


class FlowExecution(Base):
    """Record of a flow execution"""

    __tablename__ = "flow_executions"

    # Primary key
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Flow relationship
    flow_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("dq_flows.id", ondelete="CASCADE"), nullable=False
    )

    # Execution type
    execution_type = Column(
        String(50), default="manual", nullable=False
    )  # manual, scheduled, triggered, test

    # Execution status
    status = Column(
        String(50), default="pending", nullable=False
    )  # pending, running, completed, failed, cancelled
    started_at = Column(TIMESTAMP)
    completed_at = Column(TIMESTAMP)
    duration_seconds = Column(Integer)

    # Execution metrics
    nodes_executed = Column(Integer, default=0)
    nodes_passed = Column(Integer, default=0)
    nodes_failed = Column(Integer, default=0)
    nodes_skipped = Column(Integer, default=0)

    # Execution configuration
    execution_config = Column(
        JSONB
    )  # { "sample_size": 1000, "parallel": true, "continue_on_error": false }

    # Results summary
    result_summary = Column(JSONB)
    # Structure: {
    #   "total_rows_scanned": 10000,
    #   "total_violations": 50,
    #   "overall_pass_rate": 99.5,
    #   "node_results": {...}
    # }

    # Error information
    error_message = Column(Text)
    error_details = Column(JSONB)

    # Audit fields
    executed_by = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    flow = relationship("DQFlow", back_populates="executions")
    executor = relationship("User", foreign_keys=[executed_by])
    node_results = relationship(
        "FlowNodeResult", back_populates="execution", cascade="all, delete-orphan"
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "execution_type IN ('manual', 'scheduled', 'triggered', 'test')",
            name="check_execution_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="check_execution_status",
        ),
        Index("idx_flow_exec_flow", "flow_id"),
        Index("idx_flow_exec_status", "status"),
        Index("idx_flow_exec_type", "execution_type"),
        Index("idx_flow_exec_started", "started_at"),
        Index("idx_flow_exec_user", "executed_by"),
        Index("idx_flow_exec_summary", "result_summary", postgresql_using="gin"),
    )

    def __repr__(self):
        return f"<FlowExecution(id={self.id}, flow_id={self.flow_id}, status='{self.status}')>"


class FlowNodeResult(Base):
    """Individual node execution result within a flow execution"""

    __tablename__ = "flow_node_results"

    # Primary key
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Execution relationship
    execution_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("flow_executions.id", ondelete="CASCADE"), nullable=False
    )

    # Node identification
    node_id = Column(String(100), nullable=False)
    node_type = Column(String(50), nullable=False)

    # Node execution status
    status = Column(
        String(50), default="pending", nullable=False
    )  # pending, running, completed, warning, failed, skipped
    started_at = Column(TIMESTAMP)
    completed_at = Column(TIMESTAMP)
    duration_seconds = Column(Integer)

    # Node results
    result_data = Column(JSONB)
    # Structure depends on node type, e.g., for completeness check:
    # {
    #   "rows_scanned": 1000,
    #   "rows_passed": 995,
    #   "rows_failed": 5,
    #   "pass_rate": 99.5,
    #   "violations": [...]
    # }

    # Error information
    error_message = Column(Text)
    error_details = Column(JSONB)

    # Execution order
    execution_order = Column(Integer)

    # Timestamp
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    execution = relationship("FlowExecution", back_populates="node_results")

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'warning', 'failed', 'skipped')",
            name="check_node_status",
        ),
        Index("idx_node_results_execution", "execution_id"),
        Index("idx_node_results_node_id", "node_id"),
        Index("idx_node_results_status", "status"),
        Index("idx_node_results_type", "node_type"),
        Index("idx_node_results_order", "execution_id", "execution_order"),
        Index("idx_node_results_data", "result_data", postgresql_using="gin"),
        # Unique constraint on node_id per execution
        # Note: This is handled in migration as CONSTRAINT unique_node_per_execution
    )

    def __repr__(self):
        return f"<FlowNodeResult(id={self.id}, node_id='{self.node_id}', status='{self.status}')>"


class FlowTemplate(Base):
    """Pre-built flow templates for common data quality patterns"""

    __tablename__ = "flow_templates"

    # Primary key
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Template metadata
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text)
    category = Column(String(100))

    # Template flow definition
    template_definition = Column(JSONB, nullable=False)

    # Preview
    preview_image_url = Column(Text)

    # Template metadata
    is_public = Column(Boolean, default=False)
    use_count = Column(Integer, default=0)

    # Audit fields
    created_by = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])

    # Table constraints
    __table_args__ = (
        Index("idx_templates_category", "category"),
        Index("idx_templates_public", "is_public"),
        Index("idx_templates_use_count", "use_count"),
    )

    def __repr__(self):
        return f"<FlowTemplate(id={self.id}, name='{self.name}', category='{self.category}')>"
