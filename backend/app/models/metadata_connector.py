"""
F108 — Metadata Connector Configuration — SQLAlchemy ORM models.
"""

from uuid import uuid4

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.models.user import Base


class MetadataConnectorConfig(Base):
    __tablename__ = "metadata_connector_configs"
    __table_args__ = {"schema": "control"}

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False)
    connector_type = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    connection_config = Column(JSONB, nullable=False, default={})
    sync_mode = Column(String(20), nullable=False, default="hybrid")
    sync_schedule = Column(String(100))
    is_active = Column(Boolean, nullable=False, default=True)
    trust_priority = Column(Integer, nullable=False, default=50)
    last_sync_at = Column(TIMESTAMP(timezone=True))
    last_sync_status = Column(String(20))
    last_sync_error = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class MetadataConnectorSyncHistory(Base):
    __tablename__ = "metadata_connector_sync_history"
    __table_args__ = {"schema": "control"}

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    connector_config_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("control.metadata_connector_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    completed_at = Column(TIMESTAMP(timezone=True))
    status = Column(String(20), nullable=False, default="pending")
    assets_created = Column(Integer, nullable=False, default=0)
    assets_updated = Column(Integer, nullable=False, default=0)
    terms_created = Column(Integer, nullable=False, default=0)
    terms_updated = Column(Integer, nullable=False, default=0)
    error = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
