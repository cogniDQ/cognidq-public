"""
F007 — Workspace RBAC Pydantic schemas
=======================================

Request/response models for workspace role management endpoints
and the permission check endpoint.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

# Build the known permission action set from the fixed role map
from app.services.workspaces.rbac import FIXED_ROLE_PERMISSIONS, VALID_ROLE_NAMES

_ALL_KNOWN_ACTIONS: frozenset[str] = frozenset(
    action for perms in FIXED_ROLE_PERMISSIONS.values() for action in perms
)


# ---------------------------------------------------------------------------
# Role assignment
# ---------------------------------------------------------------------------


class AssignRoleRequest(BaseModel):
    """Request body for PUT /workspaces/{id}/members/{user_id}/role."""

    role_name: str

    @field_validator("role_name")
    @classmethod
    def role_name_must_be_valid(cls, v: str) -> str:
        # Accept built-in role names verbatim; custom roles are validated at
        # the service layer (must exist in the same workspace).
        if not v or not v.strip():
            raise ValueError("role_name must not be empty")
        return v.strip()


class RoleAssignmentResponse(BaseModel):
    """Response body for role assignment endpoints."""

    workspace_id: UUID
    user_id: UUID
    role_name: str
    granted_by: UUID | None
    granted_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Permission check
# ---------------------------------------------------------------------------


class PermissionCheckRequest(BaseModel):
    """Request body for POST /workspaces/{id}/permissions/check."""

    action: str

    @field_validator("action")
    @classmethod
    def action_must_be_known(cls, v: str) -> str:
        if v not in _ALL_KNOWN_ACTIONS:
            raise ValueError(
                f"Unknown permission action '{v}'. "
                f"Must be one of the defined workspace permissions."
            )
        return v


class PermissionCheckResponse(BaseModel):
    """Response body for POST /workspaces/{id}/permissions/check."""

    allowed: bool
    role_name: str | None
    action: str


# ---------------------------------------------------------------------------
# Member list + user search (F078)
# ---------------------------------------------------------------------------


class WorkspaceMemberItem(BaseModel):
    """Single member entry in the workspace members list."""

    user_id: UUID
    email: str
    display_name: str
    role_name: str
    granted_by: UUID | None
    granted_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceMembersResponse(BaseModel):
    """Response body for GET /workspaces/{id}/members."""

    workspace_id: UUID
    members: list[WorkspaceMemberItem]
    total: int


class UserSearchItem(BaseModel):
    """Single user entry from the non-member search results."""

    user_id: UUID
    email: str
    display_name: str

    model_config = {"from_attributes": True}


class UserSearchResponse(BaseModel):
    """Response body for GET /workspaces/{id}/users/search."""

    users: list[UserSearchItem]


# ---------------------------------------------------------------------------
# Custom roles
# ---------------------------------------------------------------------------

import re

_CUSTOM_ROLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,59}$")


class CustomRoleBase(BaseModel):
    display_name: str
    description: str | None = None
    permissions: list[str]

    @field_validator("display_name")
    @classmethod
    def display_name_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("display_name must not be empty")
        if len(v) > 120:
            raise ValueError("display_name too long (max 120)")
        return v.strip()

    @field_validator("permissions")
    @classmethod
    def permissions_must_be_known(cls, v: list[str]) -> list[str]:
        unknown = [p for p in v if p not in _ALL_KNOWN_ACTIONS]
        if unknown:
            raise ValueError(f"Unknown permissions: {sorted(unknown)}")
        # Deduplicate while preserving order
        seen: set[str] = set()
        out: list[str] = []
        for p in v:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out


class CustomRoleCreateRequest(CustomRoleBase):
    name: str

    @field_validator("name")
    @classmethod
    def name_format(cls, v: str) -> str:
        if v in VALID_ROLE_NAMES:
            raise ValueError(f"Role name '{v}' is reserved by a built-in role.")
        if not _CUSTOM_ROLE_NAME_RE.match(v):
            raise ValueError(
                "name must be 3–60 chars, lowercase letters/digits/underscore, "
                "starting with a letter."
            )
        return v


class CustomRoleUpdateRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None

    @field_validator("permissions")
    @classmethod
    def permissions_must_be_known(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        unknown = [p for p in v if p not in _ALL_KNOWN_ACTIONS]
        if unknown:
            raise ValueError(f"Unknown permissions: {sorted(unknown)}")
        seen: set[str] = set()
        out: list[str] = []
        for p in v:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out


class CustomRoleResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    display_name: str
    description: str | None
    permissions: list[str]
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CustomRolesListResponse(BaseModel):
    workspace_id: UUID
    roles: list[CustomRoleResponse]


class KnownPermissionsResponse(BaseModel):
    """Lists every permission action that may be granted to a custom role."""

    permissions: list[str]
