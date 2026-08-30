"""RBAC models for roles, permissions, and role assignments."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.database import Base

# Association table for role permissions
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "permission_id",
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Role(Base):
    """
    Role model representing a set of permissions.
    Roles can be system-defined or custom-created by organizations.
    """

    __tablename__ = "roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), nullable=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_system = Column(Boolean, default=False)
    scope = Column(String(50), default="organization")  # organization, domain, team
    meta_data = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles")
    user_assignments = relationship(
        "UserRoleAssignment", back_populates="role", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Role {self.name} (system={self.is_system})>"


class Permission(Base):
    """
    Permission model representing an action on a resource.
    Permissions are granular (e.g., 'datasources:read', 'rules:execute').
    """

    __tablename__ = "permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource = Column(
        String(100), nullable=False
    )  # datasources, glossary, rules, flows, teams, etc.
    action = Column(String(50), nullable=False)  # read, write, execute, delete, manage
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")

    def __repr__(self):
        return f"<Permission {self.resource}:{self.action}>"

    @property
    def code(self):
        """Return permission code as 'resource:action'."""
        return f"{self.resource}:{self.action}"


class UserRoleAssignment(Base):
    """
    User role assignment model for assigning roles to users at different scopes.
    A user can have different roles at organization, domain, or team level.
    """

    __tablename__ = "user_role_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), nullable=False)
    domain_id = Column(
        UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), nullable=True
    )
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="role_assignments")
    role = relationship("Role", back_populates="user_assignments")
    domain = relationship("Domain")
    team = relationship("Team")
    assigner = relationship("User", foreign_keys=[assigned_by])

    def __repr__(self):
        scope = "org"
        if self.team_id:
            scope = f"team={self.team_id}"
        elif self.domain_id:
            scope = f"domain={self.domain_id}"
        return f"<UserRoleAssignment user={self.user_id} role={self.role_id} scope={scope}>"
