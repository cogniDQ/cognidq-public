"""RBAC service for roles, permissions, and access control."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.rbac import Permission, Role, UserRoleAssignment, role_permissions
from app.models.user import User
from app.schemas.rbac import (
    AssignRoleRequest,
    CheckPermissionRequest,
    CheckPermissionResponse,
    CreateRoleRequest,
    PermissionResponse,
    RoleWithPermissions,
    UpdateRoleRequest,
    UserPermissionsResponse,
)


class RBACService:
    """Service for role-based access control operations."""

    @staticmethod
    async def get_all_permissions(db: Session) -> list[Permission]:
        """Get all available permissions in the system."""
        return db.query(Permission).all()

    @staticmethod
    async def create_role(
        db: Session, workspace_id: UUID, request: CreateRoleRequest, user_id: UUID
    ) -> Role:
        """Create a custom role for a workspace."""
        # Check if role name already exists in this workspace
        existing = (
            db.query(Role)
            .filter(Role.workspace_id == workspace_id, Role.name == request.name)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Role '{request.name}' already exists in this organization",
            )

        # Verify all permissions exist
        if request.permission_ids:
            permissions = (
                db.query(Permission).filter(Permission.id.in_(request.permission_ids)).all()
            )
            if len(permissions) != len(request.permission_ids):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="One or more permission IDs are invalid",
                )

        # Create role
        role = Role(
            workspace_id=workspace_id,
            name=request.name,
            description=request.description,
            scope=request.scope,
            is_system=False,
            metadata=request.metadata or {},
        )
        db.add(role)
        db.flush()  # Get role ID

        # Assign permissions
        if request.permission_ids:
            for perm_id in request.permission_ids:
                stmt = role_permissions.insert().values(role_id=role.id, permission_id=perm_id)
                db.execute(stmt)

        db.commit()
        db.refresh(role)
        return role

    @staticmethod
    async def get_roles(db: Session, workspace_id: UUID, include_system: bool = True) -> list[Role]:
        """Get all roles for an organization."""
        query = db.query(Role).filter(
            or_(
                Role.workspace_id == workspace_id,
                and_(Role.workspace_id.is_(None), Role.is_system == True)
                if include_system
                else False,
            )
        )
        return query.all()

    @staticmethod
    async def get_role(db: Session, role_id: UUID, workspace_id: UUID) -> Role:
        """Get a specific role by ID."""
        role = (
            db.query(Role)
            .filter(
                Role.id == role_id,
                or_(
                    Role.workspace_id == workspace_id,
                    and_(Role.workspace_id.is_(None), Role.is_system == True),
                ),
            )
            .first()
        )
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        return role

    @staticmethod
    async def update_role(
        db: Session, role_id: UUID, workspace_id: UUID, request: UpdateRoleRequest
    ) -> Role:
        """Update a custom role."""
        role = await RBACService.get_role(db, role_id, workspace_id)

        # Can't update system roles
        if role.is_system:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify system roles"
            )

        # Check name uniqueness if being updated
        if request.name and request.name != role.name:
            existing = (
                db.query(Role)
                .filter(
                    Role.workspace_id == workspace_id, Role.name == request.name, Role.id != role_id
                )
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Role '{request.name}' already exists",
                )

        # Update basic fields
        update_data = request.dict(exclude_unset=True, exclude={"permission_ids"})
        for field, value in update_data.items():
            setattr(role, field, value)

        # Update permissions if provided
        if request.permission_ids is not None:
            # Verify all permissions exist
            permissions = (
                db.query(Permission).filter(Permission.id.in_(request.permission_ids)).all()
            )
            if len(permissions) != len(request.permission_ids):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="One or more permission IDs are invalid",
                )

            # Remove existing permissions
            db.execute(role_permissions.delete().where(role_permissions.c.role_id == role_id))

            # Add new permissions
            for perm_id in request.permission_ids:
                stmt = role_permissions.insert().values(role_id=role_id, permission_id=perm_id)
                db.execute(stmt)

        db.commit()
        db.refresh(role)
        return role

    @staticmethod
    async def delete_role(db: Session, role_id: UUID, workspace_id: UUID) -> None:
        """Delete a custom role."""
        role = await RBACService.get_role(db, role_id, workspace_id)

        # Can't delete system roles
        if role.is_system:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete system roles"
            )

        # Check if role is assigned to any users
        assignments = (
            db.query(UserRoleAssignment).filter(UserRoleAssignment.role_id == role_id).count()
        )
        if assignments > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete role: {assignments} user(s) still have this role assigned",
            )

        db.delete(role)
        db.commit()

    @staticmethod
    async def assign_role(
        db: Session, workspace_id: UUID, request: AssignRoleRequest, assigned_by: UUID
    ) -> UserRoleAssignment:
        """Assign a role to a user."""
        # Verify user exists
        user = db.query(User).filter(User.id == request.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Verify role exists
        await RBACService.get_role(db, request.role_id, workspace_id)

        # Check for existing assignment
        existing = (
            db.query(UserRoleAssignment)
            .filter(
                UserRoleAssignment.user_id == request.user_id,
                UserRoleAssignment.role_id == request.role_id,
                UserRoleAssignment.workspace_id == workspace_id,
                UserRoleAssignment.domain_id == request.domain_id,
                UserRoleAssignment.team_id == request.team_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already has this role assignment",
            )

        # Create assignment
        assignment = UserRoleAssignment(
            user_id=request.user_id,
            role_id=request.role_id,
            workspace_id=workspace_id,
            domain_id=request.domain_id,
            team_id=request.team_id,
            assigned_by=assigned_by,
        )
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        return assignment

    @staticmethod
    async def revoke_role(db: Session, assignment_id: UUID, workspace_id: UUID) -> None:
        """Revoke a role assignment."""
        assignment = (
            db.query(UserRoleAssignment)
            .filter(
                UserRoleAssignment.id == assignment_id,
                UserRoleAssignment.workspace_id == workspace_id,
            )
            .first()
        )
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Role assignment not found"
            )

        db.delete(assignment)
        db.commit()

    @staticmethod
    async def get_user_permissions(
        db: Session, user_id: UUID, workspace_id: UUID
    ) -> UserPermissionsResponse:
        """Get all permissions for a user (aggregated from all role assignments)."""
        # Get all role assignments for user in this organization
        assignments = (
            db.query(UserRoleAssignment)
            .filter(
                UserRoleAssignment.user_id == user_id,
                UserRoleAssignment.workspace_id == workspace_id,
            )
            .all()
        )

        # Collect unique roles and permissions
        role_ids = set(a.role_id for a in assignments)
        roles = db.query(Role).filter(Role.id.in_(role_ids)).all()

        # Get all permissions from all roles
        permission_codes: set[str] = set()
        roles_with_perms = []

        for role in roles:
            role_perms = (
                db.execute(
                    select(Permission)
                    .join(role_permissions, Permission.id == role_permissions.c.permission_id)
                    .where(role_permissions.c.role_id == role.id)
                )
                .scalars()
                .all()
            )

            permission_codes.update(p.code for p in role_perms)

            roles_with_perms.append(
                RoleWithPermissions(
                    id=role.id,
                    workspace_id=role.workspace_id,
                    name=role.name,
                    description=role.description,
                    is_system=role.is_system,
                    scope=role.scope,
                    metadata=role.metadata,
                    created_at=role.created_at,
                    updated_at=role.updated_at,
                    permissions_count=len(role_perms),
                    permissions=[
                        PermissionResponse(
                            id=p.id,
                            resource=p.resource,
                            action=p.action,
                            description=p.description,
                            created_at=p.created_at,
                            code=p.code,
                        )
                        for p in role_perms
                    ],
                )
            )

        return UserPermissionsResponse(
            user_id=user_id,
            workspace_id=workspace_id,
            roles=roles_with_perms,
            permissions=sorted(list(permission_codes)),
        )

    @staticmethod
    async def check_permission(
        db: Session, user_id: UUID, workspace_id: UUID, request: CheckPermissionRequest
    ) -> CheckPermissionResponse:
        """Check if a user has a specific permission."""
        # Get user permissions
        user_perms = await RBACService.get_user_permissions(db, user_id, workspace_id)

        # Check if permission exists in user's permission list
        required_perm = f"{request.resource}:{request.action}"
        has_permission = required_perm in user_perms.permissions

        reason = None
        if not has_permission:
            reason = f"User does not have permission '{required_perm}'"

        return CheckPermissionResponse(has_permission=has_permission, reason=reason)

    @staticmethod
    async def seed_system_roles(db: Session) -> None:
        """Seed default system roles (called during initialization)."""
        # This would be called during app startup or migration
        # Implementation would create default Admin, Editor, Viewer roles
        pass
