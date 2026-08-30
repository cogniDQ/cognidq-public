"""
F007/F078 — Workspace Role Management API
==========================================

Implements:
    GET    /workspaces/{workspace_id}/members                       — list members (F078)
    GET    /workspaces/{workspace_id}/users/search                  — search non-members (F078)
    GET    /workspaces/{workspace_id}/members/{user_id}/role        — get role
    PUT    /workspaces/{workspace_id}/members/{user_id}/role        — assign role
    DELETE /workspaces/{workspace_id}/members/{user_id}/role        — revoke role
    POST   /workspaces/{workspace_id}/permissions/check             — check permission

Auth: All endpoints require a valid Bearer JWT. Permission checks are
enforced by ``require_workspace_permission`` dependency factory (F007 P03).

Error format: {"error": {"code": ..., "message": ..., "fields": null}}
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.schemas.workspace_roles import (
    AssignRoleRequest,
    CustomRoleCreateRequest,
    CustomRoleResponse,
    CustomRolesListResponse,
    CustomRoleUpdateRequest,
    KnownPermissionsResponse,
    PermissionCheckRequest,
    PermissionCheckResponse,
    RoleAssignmentResponse,
    UserSearchResponse,
    WorkspaceMembersResponse,
)
from app.services.workspaces.exceptions import (
    LastWorkspaceAdministratorError,
    RoleAssignmentNotFoundError,
    RoleGrantFailedError,
    WorkspaceMemberNotFoundError,
)
from app.services.workspaces.rbac import WorkspaceRBACService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["workspace-roles"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _error(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "fields": None}},
    )


def _get_rbac_service() -> WorkspaceRBACService:
    return WorkspaceRBACService()


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/members/{user_id}/role
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/members/{user_id}/role",
    summary="Get workspace member role",
    response_model=RoleAssignmentResponse,
    status_code=200,
)
async def get_member_role(
    workspace_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("roles:read")),
    svc: WorkspaceRBACService = Depends(_get_rbac_service),
):
    """
    Return the current workspace role assigned to *user_id* in *workspace_id*.

    Requires ``roles:read`` permission.
    """
    assignment = svc.get_member_role(workspace_id, user_id, db)
    if assignment is None:
        return _error(
            "ROLE_ASSIGNMENT_NOT_FOUND",
            f"User {user_id} has no role assignment in workspace {workspace_id}.",
            404,
        )
    return JSONResponse(
        status_code=200,
        content={
            "workspace_id": str(assignment["workspace_id"]),
            "user_id": str(assignment["user_id"]),
            "role_name": assignment["role_name"],
            "granted_by": str(assignment["granted_by"]) if assignment["granted_by"] else None,
            "granted_at": assignment["granted_at"].isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# PUT /workspaces/{workspace_id}/members/{user_id}/role
# ---------------------------------------------------------------------------


@router.put(
    "/{workspace_id}/members/{user_id}/role",
    summary="Assign or update workspace member role",
    response_model=RoleAssignmentResponse,
    status_code=200,
)
async def assign_member_role(
    workspace_id: UUID,
    user_id: UUID,
    body: AssignRoleRequest,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("roles:assign")),
    svc: WorkspaceRBACService = Depends(_get_rbac_service),
):
    """
    Assign *role_name* to *user_id* in *workspace_id*.

    Replaces any existing role (upsert). Idempotent if the same role is assigned.

    Requires ``roles:assign`` permission (workspace_administrator only).

    Raises HTTP 409 if the operation would remove the last workspace administrator.
    """
    try:
        assignment = svc.assign_role(workspace_id, user_id, body.role_name, actor.actor_id, db)
    except ValueError as exc:
        return _error("INVALID_ROLE", str(exc), 422)
    except LastWorkspaceAdministratorError as exc:
        return _error("LAST_WORKSPACE_ADMINISTRATOR", str(exc), 409)
    except WorkspaceMemberNotFoundError as exc:
        return _error("WORKSPACE_MEMBER_NOT_FOUND", str(exc), 404)
    except RoleGrantFailedError as exc:
        logger.error("assign_role failed: %s", exc)
        return _error("ROLE_GRANT_FAILED", "Failed to assign role due to a server error.", 500)

    db.commit()
    return JSONResponse(
        status_code=200,
        content={
            "workspace_id": str(assignment["workspace_id"]),
            "user_id": str(assignment["user_id"]),
            "role_name": assignment["role_name"],
            "granted_by": str(assignment["granted_by"]) if assignment["granted_by"] else None,
            "granted_at": assignment["granted_at"].isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# DELETE /workspaces/{workspace_id}/members/{user_id}/role
# ---------------------------------------------------------------------------


@router.delete(
    "/{workspace_id}/members/{user_id}/role",
    summary="Revoke workspace member role",
    status_code=204,
)
async def revoke_member_role(
    workspace_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("roles:assign")),
    svc: WorkspaceRBACService = Depends(_get_rbac_service),
):
    """
    Revoke the workspace role from *user_id* in *workspace_id*.

    Requires ``roles:assign`` permission (workspace_administrator only).

    Raises HTTP 409 if the operation would remove the last workspace administrator.
    Raises HTTP 404 if the user has no current role assignment.
    """
    try:
        svc.revoke_role(workspace_id, user_id, actor.actor_id, db)
    except RoleAssignmentNotFoundError as exc:
        return _error("ROLE_ASSIGNMENT_NOT_FOUND", str(exc), 404)
    except LastWorkspaceAdministratorError as exc:
        return _error("LAST_WORKSPACE_ADMINISTRATOR", str(exc), 409)
    except RoleGrantFailedError as exc:
        logger.error("revoke_role failed: %s", exc)
        return _error("ROLE_GRANT_FAILED", "Failed to revoke role due to a server error.", 500)

    db.commit()
    return JSONResponse(status_code=204, content=None)


# ---------------------------------------------------------------------------
# POST /workspaces/{workspace_id}/permissions/check
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/permissions/check",
    summary="Check caller's permission for an action in a workspace",
    response_model=PermissionCheckResponse,
    status_code=200,
)
async def check_permission(
    workspace_id: UUID,
    body: PermissionCheckRequest,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("workspaces:read")),
    svc: WorkspaceRBACService = Depends(_get_rbac_service),
):
    """
    Check whether the authenticated caller has permission to perform *action*
    in *workspace_id*.

    Returns ``{"allowed": true/false, "role_name": ..., "action": ...}``.
    Any authenticated workspace member may call this endpoint.
    """
    assignment = svc.get_member_role(workspace_id, actor.actor_id, db)
    allowed = svc.check_permission(workspace_id, actor.actor_id, body.action, db)

    return JSONResponse(
        status_code=200,
        content={
            "allowed": allowed,
            "role_name": assignment["role_name"] if assignment else None,
            "action": body.action,
        },
    )


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/members   (F078)
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/members",
    summary="List all members of a workspace with their roles",
    response_model=WorkspaceMembersResponse,
    status_code=200,
)
async def list_workspace_members(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("members:read")),
    svc: WorkspaceRBACService = Depends(_get_rbac_service),
):
    """
    Return all users who have a role assignment in *workspace_id*.

    Requires ``members:read`` permission.
    """
    members = svc.list_members(workspace_id, db)
    return JSONResponse(
        status_code=200,
        content={
            "workspace_id": str(workspace_id),
            "members": [
                {
                    "user_id": str(m["user_id"]),
                    "email": m["email"],
                    "display_name": m["display_name"],
                    "role_name": m["role_name"],
                    "granted_by": str(m["granted_by"]) if m["granted_by"] else None,
                    "granted_at": m["granted_at"].isoformat(),
                }
                for m in members
            ],
            "total": len(members),
        },
    )


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/users/search   (F078)
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/users/search",
    summary="Search tenant users who are not yet members of this workspace",
    response_model=UserSearchResponse,
    status_code=200,
)
async def search_non_members(
    workspace_id: UUID,
    q: str = Query(..., min_length=1, max_length=100, description="Email prefix to search for"),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("members:read")),
    svc: WorkspaceRBACService = Depends(_get_rbac_service),
):
    """
    Search users within the actor's tenant by email prefix, excluding users
    who are already members of *workspace_id*.

    Requires ``members:read`` permission.
    """
    users = svc.search_non_members(
        workspace_id=workspace_id,
        tenant_id=actor.tenant_id,
        query=q,
        db=db,
    )
    return JSONResponse(
        status_code=200,
        content={
            "users": [
                {
                    "user_id": str(u["user_id"]),
                    "email": u["email"],
                    "display_name": u["display_name"],
                }
                for u in users
            ]
        },
    )


# ---------------------------------------------------------------------------
# Custom workspace roles
# ---------------------------------------------------------------------------


def _serialize_custom_role(workspace_id: UUID, row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "workspace_id": str(workspace_id),
        "name": row["name"],
        "display_name": row["display_name"],
        "description": row["description"],
        "permissions": row["permissions"],
        "created_by": str(row["created_by"]) if row["created_by"] else None,
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


@router.get(
    "/{workspace_id}/custom-roles",
    summary="List custom workspace roles",
    response_model=CustomRolesListResponse,
    status_code=200,
)
async def list_custom_roles(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("roles:read")),
    svc: WorkspaceRBACService = Depends(_get_rbac_service),
):
    """List every custom role defined in *workspace_id*. Requires ``roles:read``."""
    roles = svc.list_custom_roles(workspace_id, db)
    return JSONResponse(
        status_code=200,
        content={
            "workspace_id": str(workspace_id),
            "roles": [_serialize_custom_role(workspace_id, r) for r in roles],
        },
    )


@router.get(
    "/{workspace_id}/custom-roles/known-permissions",
    summary="List every assignable permission action",
    response_model=KnownPermissionsResponse,
    status_code=200,
)
async def list_known_permissions(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("roles:read")),
):
    """Return every permission action that may be granted to a custom role."""
    from app.services.workspaces.rbac import ALL_KNOWN_PERMISSIONS

    return JSONResponse(
        status_code=200,
        content={"permissions": sorted(ALL_KNOWN_PERMISSIONS)},
    )


@router.post(
    "/{workspace_id}/custom-roles",
    summary="Create a custom workspace role",
    response_model=CustomRoleResponse,
    status_code=201,
)
async def create_custom_role(
    workspace_id: UUID,
    body: CustomRoleCreateRequest,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("roles:write")),
    svc: WorkspaceRBACService = Depends(_get_rbac_service),
):
    """Create a new custom role in *workspace_id*. Requires ``roles:write``."""
    try:
        row = svc.create_custom_role(
            workspace_id=workspace_id,
            name=body.name,
            display_name=body.display_name,
            description=body.description,
            permissions=body.permissions,
            created_by=actor.actor_id,
            db=db,
        )
    except ValueError as exc:
        return _error("INVALID_CUSTOM_ROLE", str(exc), 422)

    db.commit()
    return JSONResponse(
        status_code=201,
        content=_serialize_custom_role(workspace_id, row),
    )


@router.put(
    "/{workspace_id}/custom-roles/{role_id}",
    summary="Update a custom workspace role",
    response_model=CustomRoleResponse,
    status_code=200,
)
async def update_custom_role(
    workspace_id: UUID,
    role_id: UUID,
    body: CustomRoleUpdateRequest,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("roles:write")),
    svc: WorkspaceRBACService = Depends(_get_rbac_service),
):
    """Update mutable fields of a custom role. Requires ``roles:write``."""
    from app.services.workspaces.exceptions import RoleAssignmentNotFoundError

    try:
        row = svc.update_custom_role(
            workspace_id=workspace_id,
            role_id=role_id,
            display_name=body.display_name,
            description=body.description,
            permissions=body.permissions,
            db=db,
        )
    except RoleAssignmentNotFoundError as exc:
        return _error("CUSTOM_ROLE_NOT_FOUND", str(exc), 404)
    except ValueError as exc:
        return _error("INVALID_CUSTOM_ROLE", str(exc), 422)

    db.commit()
    return JSONResponse(
        status_code=200,
        content=_serialize_custom_role(workspace_id, row),
    )


@router.delete(
    "/{workspace_id}/custom-roles/{role_id}",
    summary="Delete a custom workspace role",
    status_code=204,
)
async def delete_custom_role(
    workspace_id: UUID,
    role_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("roles:write")),
    svc: WorkspaceRBACService = Depends(_get_rbac_service),
):
    """Delete a custom role. Refuses if any member is assigned to it."""
    from app.services.workspaces.exceptions import RoleAssignmentNotFoundError

    try:
        svc.delete_custom_role(workspace_id, role_id, db)
    except RoleAssignmentNotFoundError as exc:
        return _error("CUSTOM_ROLE_NOT_FOUND", str(exc), 404)
    except ValueError as exc:
        return _error("CUSTOM_ROLE_IN_USE", str(exc), 409)

    db.commit()
    return JSONResponse(status_code=204, content=None)
