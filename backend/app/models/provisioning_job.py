"""
F134 — Demo Sandbox Provisioning
ProvisioningJob ORM model (control.provisioning_jobs)
"""

import enum
from uuid import uuid4

from sqlalchemy import TIMESTAMP, Column, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class ProvisioningJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProvisioningJob(Base):
    """Tracks a single provisioning Celery task execution."""

    __tablename__ = "provisioning_jobs"
    __table_args__ = {"schema": "control"}

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    demo_request_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)
    sandbox_id = Column(PGUUID(as_uuid=True), nullable=True)
    status = Column(String(20), nullable=False, server_default="pending")
    attempt_count = Column(SmallInteger, nullable=False, server_default="0")
    last_error = Column(Text, nullable=True)
    started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    finished_at = Column(TIMESTAMP(timezone=True), nullable=True)
    celery_task_id = Column(String(120), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    demo_request = relationship(
        "DemoRequest",
        back_populates="provisioning_jobs",
        foreign_keys=[demo_request_id],
        primaryjoin="ProvisioningJob.demo_request_id == DemoRequest.id",
    )
    sandbox_environment = relationship(
        "SandboxEnvironment",
        back_populates="provisioning_jobs",
        foreign_keys=[sandbox_id],
        primaryjoin="ProvisioningJob.sandbox_id == SandboxEnvironment.id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ProvisioningJob id={self.id} status={self.status!r}>"
