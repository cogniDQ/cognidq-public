"""
F134 — Demo Sandbox Provisioning
DemoRequest ORM model (control.demo_requests)
"""

from __future__ import annotations

import enum
from uuid import uuid4

from sqlalchemy import CHAR, TIMESTAMP, Boolean, Column, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class DemoRequestStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROVISIONED = "provisioned"
    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"
    CONVERTED = "converted"


class DemoRequest(Base):
    """Public-intake request for a demo sandbox."""

    __tablename__ = "demo_requests"
    __table_args__ = {"schema": "control"}

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    # VARCHAR in DB; stored as plain string (not DB enum) for migration simplicity
    status = Column(String(30), nullable=False, server_default="submitted")
    public_status_token = Column(String(80), nullable=False, unique=True)
    work_email = Column(String(254), nullable=False)
    first_name = Column(String(60), nullable=False)
    last_name = Column(String(60), nullable=False)
    company_name = Column(String(120), nullable=False)
    job_title = Column(String(120), nullable=True)
    team_size = Column(String(20), nullable=False)
    country = Column(CHAR(2), nullable=True)
    primary_use_case = Column(Text, nullable=False)
    stack = Column(JSONB, nullable=False, server_default="{}")
    heard_about_us = Column(String(80), nullable=True)
    consent = Column(Boolean, nullable=False, server_default="false")
    is_personal_email = Column(Boolean, nullable=False, server_default="false")
    source_ip = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    admin_tags = Column(JSONB, nullable=False, server_default="[]")
    internal_note = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    decided_by = Column(PGUUID(as_uuid=True), nullable=True)
    decided_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    sandbox_environment = relationship(
        "SandboxEnvironment",
        back_populates="demo_request",
        uselist=False,
        cascade="all, delete-orphan",
        foreign_keys="[SandboxEnvironment.demo_request_id]",
        primaryjoin="DemoRequest.id == SandboxEnvironment.demo_request_id",
    )
    provisioning_jobs = relationship(
        "ProvisioningJob",
        back_populates="demo_request",
        cascade="all, delete-orphan",
        foreign_keys="[ProvisioningJob.demo_request_id]",
        primaryjoin="DemoRequest.id == ProvisioningJob.demo_request_id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DemoRequest id={self.id} status={self.status!r} email={self.work_email!r}>"
