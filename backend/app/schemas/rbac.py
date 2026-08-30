"""Pydantic schemas for RBAC (roles, permissions, assignments)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PermissionBase(BaseModel):
    """Base permission schema."""

    resource: str = Field(..., description="Resource type (e.g., datasources, rules, teams)")
    action: str = Field(..., description="Action (e.g., read, write, execute, delete)")
    description: str | None = None


class PermissionResponse(PermissionBase):
    """Response schema for permission."""

    id: UUID
    created_at: datetime
    code: str = Field(..., description="Permission code as 'resource:action'")

    class Config:
        from_attributes = True


class RoleBase(BaseModel):
    """Base role schema."""

    name: str = Field(..., min_length=1, max_length=100, description="Role name")
    description: str | None = None
    scope: str = Field(default="organization", description="Scope: organization, domain, or team")
    metadata: dict[str, Any] | None = Field(default_factory=dict)


class CreateRoleRequest(RoleBase):
    """Request schema for creating a role."""

    permission_ids: list[UUID] = Field(default_factory=list, description="List of permission IDs")


class UpdateRoleRequest(BaseModel):
    """Request schema for updating a role."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    metadata: dict[str, Any] | None = None
    permission_ids: list[UUID] | None = Field(
        None, description="List of permission IDs to replace current permissions"
    )


class RoleResponse(RoleBase):
    """Response schema for role."""

    id: UUID
    workspace_id: UUID | None
    is_system: bool
    created_at: datetime
    updated_at: datetime
    permissions_count: int | None = Field(None, description="Number of permissions assigned")

    class Config:
        from_attributes = True


class RoleWithPermissions(RoleResponse):
    """Role response with permissions included."""

    permissions: list[PermissionResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class AssignRoleRequest(BaseModel):
    """Request schema for assigning role to user."""

    user_id: UUID = Field(..., description="User ID to assign role to")
    role_id: UUID = Field(..., description="Role ID to assign")
    domain_id: UUID | None = Field(None, description="Domain scope (optional)")
    team_id: UUID | None = Field(None, description="Team scope (optional)")


class RoleAssignmentResponse(BaseModel):
    """Response schema for role assignment."""

    id: UUID
    user_id: UUID
    role_id: UUID
    role_name: str
    workspace_id: UUID
    domain_id: UUID | None
    team_id: UUID | None
    assigned_by: UUID | None
    assigned_at: datetime
    scope: str = Field(..., description="Effective scope: organization, domain, or team")

    class Config:
        from_attributes = True


class UserPermissionsResponse(BaseModel):
    """Response schema for user's aggregated permissions."""

    user_id: UUID
    workspace_id: UUID
    roles: list[RoleWithPermissions] = Field(
        default_factory=list, description="All roles assigned to user"
    )
    permissions: list[str] = Field(default_factory=list, description="Aggregated permission codes")

    class Config:
        from_attributes = True


class CheckPermissionRequest(BaseModel):
    """Request schema for checking if user has permission."""

    resource: str = Field(..., description="Resource type")
    action: str = Field(..., description="Action")
    domain_id: UUID | None = Field(None, description="Domain scope (optional)")
    team_id: UUID | None = Field(None, description="Team scope (optional)")


class CheckPermissionResponse(BaseModel):
    """Response schema for permission check."""

    has_permission: bool
    reason: str | None = Field(None, description="Reason if permission denied")
