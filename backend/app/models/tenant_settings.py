"""
Tenant Settings ORM Model

Maps to the ``control.tenant_settings`` table created by migration
044_tenant_settings.sql. Holds tenant-scoped configurable external service
credentials (currently SMTP for alert email delivery).
"""

from sqlalchemy import TIMESTAMP, Boolean, Column, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from app.models.database import Base


class TenantSettings(Base):
    """Tenant-scoped configuration for external services."""

    __tablename__ = "tenant_settings"
    __table_args__ = {"schema": "control"}

    tenant_id = Column(PG_UUID(as_uuid=True), primary_key=True)

    # SMTP block
    smtp_enabled = Column(Boolean, nullable=False, default=False)
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, nullable=True)
    smtp_username = Column(String(255), nullable=True)
    smtp_password_enc = Column(LargeBinary, nullable=True)
    smtp_use_tls = Column(Boolean, nullable=False, default=True)
    smtp_from_address = Column(String(255), nullable=True)
    smtp_last_tested_at = Column(TIMESTAMP(timezone=True), nullable=True)
    smtp_last_test_ok = Column(Boolean, nullable=True)
    smtp_last_test_error = Column(String(2000), nullable=True)

    # Audit
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(PG_UUID(as_uuid=True), nullable=True)
    updated_by = Column(PG_UUID(as_uuid=True), nullable=True)
    version = Column(Integer, nullable=False, default=0)
