"""
AuditLog ORM Model — F052 Immutable Audit Logging

Maps to the ``control.workspace_audit_logs`` table.
Original 11 columns created by migration 007; extended with 3 new columns
(actor_type, target_entity_type, target_entity_id) by migration 015.

This table is append-only: the application role has INSERT + SELECT only.
"""

from uuid import uuid4

from sqlalchemy import TIMESTAMP, Column, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from app.models.database import Base


class AuditLog(Base):
    """Immutable audit log entry for any platform entity mutation."""

    __tablename__ = "workspace_audit_logs"
    __table_args__ = {"schema": "control"}

    # --- Primary key ---
    log_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # --- Tenant scope ---
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False)

    # --- Workspace scope (nullable for tenant-level events) ---
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=True)

    # --- Action ---
    action_type = Column(String(50), nullable=False)

    # --- Actor ---
    actor_id = Column(PG_UUID(as_uuid=True), nullable=True)
    actor_role = Column(String(50), nullable=False)
    actor_type = Column(String(20), nullable=False, server_default="user")

    # --- Target entity (F052 extensions) ---
    target_entity_type = Column(String(50), nullable=True)
    target_entity_id = Column(PG_UUID(as_uuid=True), nullable=True)

    # --- State snapshots ---
    previous_data = Column(JSONB, nullable=True)
    new_data = Column(JSONB, nullable=False)

    # --- Metadata ---
    occurred_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    request_id = Column(PG_UUID(as_uuid=True), nullable=True)
    source_ip = Column(String(45), nullable=True)
