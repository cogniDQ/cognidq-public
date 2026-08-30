"""
F134 — Demo Sandbox Provisioning
AccessProfile ORM model (control.access_profiles)
"""

from uuid import uuid4

from sqlalchemy import TIMESTAMP, Boolean, Column, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class AccessProfile(Base):
    """Feature-flag bundles that govern what a sandbox tenant can do."""

    __tablename__ = "access_profiles"
    __table_args__ = {"schema": "control"}

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code = Column(String(64), nullable=False, unique=True)
    display_name = Column(String(120), nullable=False)
    flags = Column(JSONB, nullable=False, server_default="{}")
    default_role = Column(String(40), nullable=False, server_default="sandbox_admin")
    is_enabled = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    sandbox_environments = relationship(
        "SandboxEnvironment",
        back_populates="access_profile",
        cascade="all, delete-orphan",
        foreign_keys="[SandboxEnvironment.access_profile_id]",
        primaryjoin="AccessProfile.id == SandboxEnvironment.access_profile_id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AccessProfile code={self.code!r}>"
