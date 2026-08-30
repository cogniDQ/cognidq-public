"""Team model for organizing users within domains."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.database import Base

# Association table for team members
team_members = Table(
    "team_members",
    Base.metadata,
    Column(
        "team_id", UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("role", String(50), nullable=False, default="member"),
    Column("joined_at", DateTime, default=datetime.utcnow),
)


class Team(Base):
    """
    Team model representing a group of users within a domain.
    Teams can have multiple members and can be assigned roles and permissions.
    """

    __tablename__ = "teams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_id = Column(
        UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id = Column(UUID(as_uuid=True), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    slug = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    meta_data = Column("metadata", JSON, default={})
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    domain = relationship("Domain", back_populates="teams")
    members = relationship("User", secondary=team_members, back_populates="teams")
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<Team {self.name} (domain={self.domain_id})>"
