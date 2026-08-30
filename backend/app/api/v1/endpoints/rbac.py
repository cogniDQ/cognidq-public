"""RBAC API endpoints for roles, permissions, and assignments."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.schemas.rbac import (
    AssignRoleRequest,
    CheckPermissionRequest,
    CheckPermissionResponse,
    CreateRoleRequest,
    PermissionResponse,
    RoleAssignmentResponse,
    RoleResponse,
    RoleWithPermissions,
    UpdateRoleRequest,
    UserPermissionsResponse,
)
from app.services.audit.hooks import build_rbac_audit_entry
from app.services.audit.models import AuditContext
from app.services.audit.service import AuditService
from app.services.auth.jwt import get_current_user
from app.services.rbac.service import RBACService

logger = logging.getLogger(__name__)
_audit_svc = AuditService()

# Main router for organization-scoped RBAC endpoints
router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["RBAC"])

# Global router for system-wide permissions
global_router = APIRouter(tags=["RBAC"])


# Global Permissions Endpoints (not scoped to organization)


@global_router.get("/permissions", response_model=list[PermissionResponse])
async def list_all_permissions(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """List all available permissions in the system."""
    permissions = await RBACService.get_all_permissions(db)

    return [
        PermissionResponse(
            id=p.id,
            resource=p.resource,
            action=p.action,
            description=p.description,
            created_at=p.created_at,
            code=p.code,
        )
        for p in permissions
    ]


# Roles Endpoints


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    workspace_id: UUID,
    request: CreateRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a custom role for an organization."""
    role = await RBACService.create_role(db, workspace_id, request, current_user.id)

    return RoleResponse(
        id=role.id,
        workspace_id=role.workspace_id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        scope=role.scope,
        metadata=role.meta_data,
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


@router.get("/roles", response_model=list[RoleWithPermissions])
async def list_roles(
    workspace_id: UUID,
    include_system: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all roles for an organization."""
    roles = await RBACService.get_roles(db, workspace_id, include_system)

    result = []
    for role in roles:
        # Get permissions for this role
        permissions = []
        for perm in role.permissions:
            permissions.append(
                PermissionResponse(
                    id=perm.id,
                    resource=perm.resource,
                    action=perm.action,
                    description=perm.description,
                    created_at=perm.created_at,
                    code=perm.code,
                )
            )

        result.append(
            RoleWithPermissions(
                id=role.id,
                workspace_id=role.workspace_id,
                name=role.name,
                description=role.description,
                is_system=role.is_system,
                scope=role.scope,
                metadata=role.meta_data,
                created_at=role.created_at,
                updated_at=role.updated_at,
                permissions_count=len(permissions),
                permissions=permissions,
            )
        )

    return result


@router.get("/roles/{role_id}", response_model=RoleWithPermissions)
async def get_role(
    workspace_id: UUID,
    role_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific role with permissions."""
    role = await RBACService.get_role(db, role_id, workspace_id)

    permissions = [
        PermissionResponse(
            id=p.id,
            resource=p.resource,
            action=p.action,
            description=p.description,
            created_at=p.created_at,
            code=p.code,
        )
        for p in role.permissions
    ]

    return RoleWithPermissions(
        id=role.id,
        workspace_id=role.workspace_id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        scope=role.scope,
        metadata=role.meta_data,
        created_at=role.created_at,
        updated_at=role.updated_at,
        permissions_count=len(permissions),
        permissions=permissions,
    )


@router.patch("/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    workspace_id: UUID,
    role_id: UUID,
    request: UpdateRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a custom role."""
    role = await RBACService.update_role(db, role_id, workspace_id, request)

    return RoleResponse(
        id=role.id,
        workspace_id=role.workspace_id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        scope=role.scope,
        metadata=role.meta_data,
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    workspace_id: UUID,
    role_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a custom role."""
    await RBACService.delete_role(db, role_id, workspace_id)
    return None


# Role Assignments Endpoints


@router.post(
    "/role-assignments", response_model=RoleAssignmentResponse, status_code=status.HTTP_201_CREATED
)
async def assign_role(
    workspace_id: UUID,
    request: AssignRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assign a role to a user."""
    assignment = await RBACService.assign_role(db, workspace_id, request, current_user.id)

    # Determine scope
    scope = "organization"
    if assignment.team_id:
        scope = "team"
    elif assignment.domain_id:
        scope = "domain"

    # F052 audit hook (best-effort)
    try:
        tenant_id = current_user.tenant_id or workspace_id
        _audit_svc.write(
            db,
            build_rbac_audit_entry(
                ctx=AuditContext(
                    tenant_id=tenant_id,
                    actor_id=current_user.id,
                    actor_type="user",
                    actor_role=current_user.platform_role or "user",
                    request_id=None,
                    source_ip=None,
                ),
                action="role_assigned",
                workspace_id=workspace_id,
                user_id=assignment.user_id,
                after_state={
                    "role_id": str(assignment.role_id),
                    "role_name": assignment.role.name,
                    "workspace_id": str(workspace_id),
                    "scope": scope,
                },
            ),
        )
        db.commit()
    except Exception:
        logger.warning(
            "audit_write_failed action_type=role_assigned user_id=%s", assignment.user_id
        )

    return RoleAssignmentResponse(
        id=assignment.id,
        user_id=assignment.user_id,
        role_id=assignment.role_id,
        role_name=assignment.role.name,
        workspace_id=assignment.workspace_id,
        domain_id=assignment.domain_id,
        team_id=assignment.team_id,
        assigned_by=assignment.assigned_by,
        assigned_at=assignment.assigned_at,
        scope=scope,
    )


@router.delete("/role-assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_role(
    workspace_id: UUID,
    assignment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke a role assignment."""
    await RBACService.revoke_role(db, assignment_id, workspace_id)

    # F052 audit hook (best-effort)
    try:
        tenant_id = current_user.tenant_id or workspace_id
        _audit_svc.write(
            db,
            build_rbac_audit_entry(
                ctx=AuditContext(
                    tenant_id=tenant_id,
                    actor_id=current_user.id,
                    actor_type="user",
                    actor_role=current_user.platform_role or "user",
                    request_id=None,
                    source_ip=None,
                ),
                action="role_revoked",
                workspace_id=workspace_id,
                user_id=assignment_id,
                after_state={"revoked": True, "workspace_id": str(workspace_id)},
            ),
        )
        db.commit()
    except Exception:
        logger.warning(
            "audit_write_failed action_type=role_revoked assignment_id=%s", assignment_id
        )

    return None


# User Permissions Endpoints


@router.get("/users/{user_id}/permissions", response_model=UserPermissionsResponse)
async def get_user_permissions(
    workspace_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all permissions for a user (aggregated from role assignments)."""
    return await RBACService.get_user_permissions(db, user_id, workspace_id)


@router.post("/check-permission", response_model=CheckPermissionResponse)
async def check_permission(
    workspace_id: UUID,
    request: CheckPermissionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check if current user has a specific permission."""
    return await RBACService.check_permission(db, current_user.id, workspace_id, request)
