"""
F134 — Demo Sandbox Provisioning
SandboxExtension ORM model (control.sandbox_extensions)
"""

from uuid import uuid4

from sqlalchemy import TIMESTAMP, Column, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class SandboxExtension(Base):
    """Record of a sandbox lifetime extension (max 2 per sandbox, 3 days each)."""

    __tablename__ = "sandbox_extensions"
    __table_args__ = {"schema": "control"}

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    sandbox_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)
    extended_by = Column(PGUUID(as_uuid=True), nullable=True)
    extension_days = Column(SmallInteger, nullable=False, server_default="3")
    note = Column(Text, nullable=False)
    previous_expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    new_expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    sandbox_environment = relationship(
        "SandboxEnvironment",
        back_populates="sandbox_extensions",
        foreign_keys=[sandbox_id],
        primaryjoin="SandboxExtension.sandbox_id == SandboxEnvironment.id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SandboxExtension sandbox_id={self.sandbox_id} days={self.extension_days}>"
