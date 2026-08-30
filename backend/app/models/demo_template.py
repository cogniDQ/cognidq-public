"""
F134 — Demo Sandbox Provisioning
DemoTemplate ORM model (control.demo_templates)
"""

from sqlalchemy import TIMESTAMP, Boolean, Column, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class DemoTemplate(Base):
    """Registry of available sandbox templates. Rows are seed-only."""

    __tablename__ = "demo_templates"
    __table_args__ = {"schema": "control"}

    id = Column(String(64), primary_key=True)
    display_name = Column(String(120), nullable=False)
    description = Column(Text, nullable=False, server_default="")
    seeder_module = Column(String(200), nullable=False)
    default_duration_days = Column(Integer, nullable=False, server_default="7")
    is_enabled = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    sandbox_environments = relationship(
        "SandboxEnvironment",
        back_populates="template",
        cascade="all, delete-orphan",
        foreign_keys="[SandboxEnvironment.template_id]",
        primaryjoin="DemoTemplate.id == SandboxEnvironment.template_id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DemoTemplate id={self.id!r}>"
