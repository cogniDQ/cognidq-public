"""Team API endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.schemas.team import (
    AddTeamMemberRequest,
    CreateTeamRequest,
    TeamMemberResponse,
    TeamResponse,
    UpdateTeamMemberRequest,
    UpdateTeamRequest,
)
from app.services.audit.hooks import build_team_audit_entry, build_team_membership_audit_entry
from app.services.audit.models import AuditContext
from app.services.audit.service import AuditService
from app.services.auth.jwt import get_current_user
from app.services.team.service import TeamService

logger = logging.getLogger(__name__)
_audit_svc = AuditService()

router = APIRouter(prefix="/workspaces/{workspace_id}/teams", tags=["Teams"])


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    workspace_id: UUID,
    request: CreateTeamRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new team in a domain."""
    team = await TeamService.create_team(db, workspace_id, request, current_user.id)

    # F052 audit hook (best-effort)
    try:
        tenant_id = current_user.tenant_id or workspace_id
        _audit_svc.write(
            db,
            build_team_audit_entry(
                ctx=AuditContext(
                    tenant_id=tenant_id,
                    actor_id=current_user.id,
                    actor_type="user",
                    actor_role=current_user.platform_role or "user",
                    request_id=None,
                    source_ip=None,
                ),
                action="team_created",
                team_id=team.id,
                after_state={"name": team.name, "workspace_id": str(workspace_id)},
                workspace_id=workspace_id,
            ),
        )
        db.commit()
    except Exception:
        logger.warning("audit_write_failed action_type=team_created id=%s", team.id)

    return TeamResponse(
        id=team.id,
        domain_id=team.domain_id,
        workspace_id=team.workspace_id,
        name=team.name,
        description=team.description,
        slug=team.slug,
        is_active=team.is_active,
        metadata=team.metadata,
        created_by=team.created_by,
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


@router.get("", response_model=list[TeamResponse])
async def list_teams(
    workspace_id: UUID,
    domain_id: UUID | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all teams in an organization or domain."""
    teams = await TeamService.get_teams(db, workspace_id, domain_id, skip, limit)

    return [
        TeamResponse(
            id=t.id,
            domain_id=t.domain_id,
            workspace_id=t.workspace_id,
            name=t.name,
            description=t.description,
            slug=t.slug,
            is_active=t.is_active,
            metadata=t.metadata,
            created_by=t.created_by,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in teams
    ]


@router.get("/hierarchy", response_model=dict)
async def get_hierarchy(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the complete organization → domain → team hierarchy."""
    return await TeamService.get_hierarchy(db, workspace_id)


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    workspace_id: UUID,
    team_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific team."""
    team = await TeamService.get_team(db, team_id, workspace_id)

    return TeamResponse(
        id=team.id,
        domain_id=team.domain_id,
        workspace_id=team.workspace_id,
        name=team.name,
        description=team.description,
        slug=team.slug,
        is_active=team.is_active,
        metadata=team.metadata,
        created_by=team.created_by,
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    workspace_id: UUID,
    team_id: UUID,
    request: UpdateTeamRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a team."""
    team = await TeamService.update_team(db, team_id, workspace_id, request)

    # F052 audit hook (best-effort)
    try:
        tenant_id = current_user.tenant_id or workspace_id
        _audit_svc.write(
            db,
            build_team_audit_entry(
                ctx=AuditContext(
                    tenant_id=tenant_id,
                    actor_id=current_user.id,
                    actor_type="user",
                    actor_role=current_user.platform_role or "user",
                    request_id=None,
                    source_ip=None,
                ),
                action="team_updated",
                team_id=team.id,
                after_state={"name": team.name},
                workspace_id=workspace_id,
            ),
        )
        db.commit()
    except Exception:
        logger.warning("audit_write_failed action_type=team_updated id=%s", team.id)

    return TeamResponse(
        id=team.id,
        domain_id=team.domain_id,
        workspace_id=team.workspace_id,
        name=team.name,
        description=team.description,
        slug=team.slug,
        is_active=team.is_active,
        metadata=team.metadata,
        created_by=team.created_by,
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    workspace_id: UUID,
    team_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a team."""
    await TeamService.delete_team(db, team_id, workspace_id)

    # F052 audit hook (best-effort)
    try:
        tenant_id = current_user.tenant_id or workspace_id
        _audit_svc.write(
            db,
            build_team_audit_entry(
                ctx=AuditContext(
                    tenant_id=tenant_id,
                    actor_id=current_user.id,
                    actor_type="user",
                    actor_role=current_user.platform_role or "user",
                    request_id=None,
                    source_ip=None,
                ),
                action="team_deleted",
                team_id=team_id,
                after_state={"deleted": True},
                workspace_id=workspace_id,
            ),
        )
        db.commit()
    except Exception:
        logger.warning("audit_write_failed action_type=team_deleted id=%s", team_id)

    return None


# Team Members Endpoints


@router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
async def add_team_member(
    workspace_id: UUID,
    team_id: UUID,
    request: AddTeamMemberRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a member to a team."""
    await TeamService.add_member(db, team_id, workspace_id, request)

    # F052 audit hook (best-effort)
    try:
        tenant_id = current_user.tenant_id or workspace_id
        _audit_svc.write(
            db,
            build_team_membership_audit_entry(
                ctx=AuditContext(
                    tenant_id=tenant_id,
                    actor_id=current_user.id,
                    actor_type="user",
                    actor_role=current_user.platform_role or "user",
                    request_id=None,
                    source_ip=None,
                ),
                action="team_member_added",
                team_id=team_id,
                member_user_id=request.user_id,
                after_state={"user_id": str(request.user_id)},
                workspace_id=workspace_id,
            ),
        )
        db.commit()
    except Exception:
        logger.warning("audit_write_failed action_type=team_member_added team_id=%s", team_id)

    return {"message": "Member added successfully"}


@router.get("/{team_id}/members", response_model=list[TeamMemberResponse])
async def list_team_members(
    workspace_id: UUID,
    team_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all members of a team."""
    return await TeamService.get_members(db, team_id, workspace_id)


@router.patch("/{team_id}/members/{user_id}")
async def update_team_member(
    workspace_id: UUID,
    team_id: UUID,
    user_id: UUID,
    request: UpdateTeamMemberRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a team member's role."""
    await TeamService.update_member_role(db, team_id, workspace_id, user_id, request)

    # F052 audit hook (best-effort)
    try:
        tenant_id = current_user.tenant_id or workspace_id
        _audit_svc.write(
            db,
            build_team_membership_audit_entry(
                ctx=AuditContext(
                    tenant_id=tenant_id,
                    actor_id=current_user.id,
                    actor_type="user",
                    actor_role=current_user.platform_role or "user",
                    request_id=None,
                    source_ip=None,
                ),
                action="team_member_updated",
                team_id=team_id,
                member_user_id=user_id,
                after_state={"updated": True},
                workspace_id=workspace_id,
            ),
        )
        db.commit()
    except Exception:
        logger.warning(
            "audit_write_failed action_type=team_member_updated team_id=%s user_id=%s",
            team_id,
            user_id,
        )

    return {"message": "Member role updated successfully"}


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    workspace_id: UUID,
    team_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a member from a team."""
    await TeamService.remove_member(db, team_id, workspace_id, user_id)

    # F052 audit hook (best-effort)
    try:
        tenant_id = current_user.tenant_id or workspace_id
        _audit_svc.write(
            db,
            build_team_membership_audit_entry(
                ctx=AuditContext(
                    tenant_id=tenant_id,
                    actor_id=current_user.id,
                    actor_type="user",
                    actor_role=current_user.platform_role or "user",
                    request_id=None,
                    source_ip=None,
                ),
                action="team_member_removed",
                team_id=team_id,
                member_user_id=user_id,
                after_state={"removed": True},
                workspace_id=workspace_id,
            ),
        )
        db.commit()
    except Exception:
        logger.warning(
            "audit_write_failed action_type=team_member_removed team_id=%s user_id=%s",
            team_id,
            user_id,
        )

    return None
