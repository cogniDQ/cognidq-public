"""
F134 — Demo Sandbox Provisioning
SandboxUser ORM model (control.sandbox_users)
"""

from uuid import uuid4

from sqlalchemy import CHAR, TIMESTAMP, Column
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class SandboxUser(Base):
    """Links a platform user to a sandbox environment."""

    __tablename__ = "sandbox_users"
    __table_args__ = {"schema": "control"}

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    sandbox_id = Column(PGUUID(as_uuid=True), nullable=True, index=True)
    user_id = Column(PGUUID(as_uuid=True), nullable=True, index=True)
    invitation_token_hash = Column(CHAR(64), nullable=True)
    invitation_expires_at = Column(TIMESTAMP(timezone=True), nullable=True)
    invitation_accepted_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    sandbox_environment = relationship(
        "SandboxEnvironment",
        back_populates="sandbox_users",
        foreign_keys=[sandbox_id],
        primaryjoin="SandboxUser.sandbox_id == SandboxEnvironment.id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SandboxUser id={self.id} sandbox_id={self.sandbox_id}>"
