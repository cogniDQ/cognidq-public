"""
F060 — External Ticketing Integration Hooks — ORM Model
=========================================================

Maps to the table created by migration 025_f060_external_ticketing.sql:
  - ticketing_integration_configs

External ticket reference columns added to issues and incidents are
lightweight ALTER TABLE additions — those tables' existing ORM models
are extended in this module via declared mixin-like approach, but in
practice the columns are accessed at the service layer via raw SQL or
by augmenting the existing models. See issues.py / incidents.py for
the actual ORM models.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from app.models.database import Base


class TicketingIntegrationConfig(Base):
    """Workspace-level configuration for an external ticketing system.

    One workspace can have at most one config per ``system_name``
    (Jira, Linear, GitHub, ServiceNow, PagerDuty, or custom).
    """

    __tablename__ = "ticketing_integration_configs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False)
    system_name = Column(String(100), nullable=False)
    display_name = Column(String(255), nullable=False)
    base_url = Column(Text, nullable=True)
    project_key = Column(String(100), nullable=True)
    default_issue_type = Column(String(100), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    config_json = Column(JSONB, nullable=True)
    created_by = Column(PG_UUID(as_uuid=True), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
