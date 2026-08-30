"""
F134 — Demo Sandbox Provisioning
SandboxEnvironment ORM model (control.sandbox_environments)
"""

from __future__ import annotations

import enum
from uuid import uuid4

from sqlalchemy import TIMESTAMP, Column, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class SandboxEnvironmentStatus(str, enum.Enum):
    PROVISIONING = "provisioning"
    PROVISIONING_FAILED = "provisioning_failed"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    ARCHIVED = "archived"
    DELETED = "deleted"


class SandboxEnvironment(Base):
    """A live sandbox tenant provisioned from a demo request."""

    __tablename__ = "sandbox_environments"
    __table_args__ = {"schema": "control"}

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    demo_request_id = Column(PGUUID(as_uuid=True), nullable=False, unique=True)
    tenant_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)
    workspace_id = Column(PGUUID(as_uuid=True), nullable=False)
    template_id = Column(String(64), nullable=False)
    access_profile_id = Column(PGUUID(as_uuid=True), nullable=False)
    status = Column(String(30), nullable=False, server_default="provisioning")
    provisioned_at = Column(TIMESTAMP(timezone=True), nullable=True)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=True, index=True)
    suspended_at = Column(TIMESTAMP(timezone=True), nullable=True)
    archived_at = Column(TIMESTAMP(timezone=True), nullable=True)
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)
    extension_count = Column(SmallInteger, nullable=False, server_default="0")
    grace_period_days = Column(SmallInteger, nullable=False, server_default="3")
    retention_policy = Column(String(40), nullable=False, server_default="retain_metadata_only")
    engagement_score = Column(String(10), nullable=False, server_default="unknown")
    last_activity_at = Column(TIMESTAMP(timezone=True), nullable=True)
    session_count = Column(Integer, nullable=False, server_default="0")
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    demo_request = relationship(
        "DemoRequest",
        back_populates="sandbox_environment",
        foreign_keys=[demo_request_id],
        primaryjoin="SandboxEnvironment.demo_request_id == DemoRequest.id",
    )
    template = relationship(
        "DemoTemplate",
        back_populates="sandbox_environments",
        foreign_keys=[template_id],
        primaryjoin="SandboxEnvironment.template_id == DemoTemplate.id",
    )
    access_profile = relationship(
        "AccessProfile",
        back_populates="sandbox_environments",
        foreign_keys=[access_profile_id],
        primaryjoin="SandboxEnvironment.access_profile_id == AccessProfile.id",
    )
    sandbox_users = relationship(
        "SandboxUser",
        back_populates="sandbox_environment",
        cascade="all, delete-orphan",
        foreign_keys="[SandboxUser.sandbox_id]",
        primaryjoin="SandboxEnvironment.id == SandboxUser.sandbox_id",
    )
    sandbox_extensions = relationship(
        "SandboxExtension",
        back_populates="sandbox_environment",
        cascade="all, delete-orphan",
        foreign_keys="[SandboxExtension.sandbox_id]",
        primaryjoin="SandboxEnvironment.id == SandboxExtension.sandbox_id",
    )
    provisioning_jobs = relationship(
        "ProvisioningJob",
        back_populates="sandbox_environment",
        cascade="all, delete-orphan",
        foreign_keys="[ProvisioningJob.sandbox_id]",
        primaryjoin="SandboxEnvironment.id == ProvisioningJob.sandbox_id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SandboxEnvironment id={self.id} status={self.status!r}>"
