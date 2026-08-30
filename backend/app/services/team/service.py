"""Team service for managing teams and team members."""

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.domain import Domain
from app.models.team import Team, team_members
from app.models.user import User
from app.schemas.team import (
    AddTeamMemberRequest,
    CreateTeamRequest,
    TeamMemberResponse,
    UpdateTeamMemberRequest,
    UpdateTeamRequest,
)


class TeamService:
    """Service for team management operations."""

    @staticmethod
    async def create_team(
        db: Session, workspace_id: UUID, request: CreateTeamRequest, user_id: UUID
    ) -> Team:
        """Create a new team in a domain."""
        # Check if domain exists and belongs to organization
        domain = (
            db.query(Domain)
            .filter(Domain.id == request.domain_id, Domain.workspace_id == workspace_id)
            .first()
        )
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found in this organization",
            )

        # Check if slug already exists in this domain
        existing = (
            db.query(Team)
            .filter(Team.domain_id == request.domain_id, Team.slug == request.slug)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Team with slug '{request.slug}' already exists in this domain",
            )

        # Create team
        team = Team(
            domain_id=request.domain_id,
            workspace_id=workspace_id,
            name=request.name,
            description=request.description,
            slug=request.slug,
            metadata=request.metadata or {},
            created_by=user_id,
        )
        db.add(team)
        db.commit()
        db.refresh(team)
        return team

    @staticmethod
    async def get_teams(
        db: Session,
        workspace_id: UUID,
        domain_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Team]:
        """Get all teams for an organization or domain."""
        query = db.query(Team).filter(Team.workspace_id == workspace_id)
        if domain_id:
            query = query.filter(Team.domain_id == domain_id)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    async def get_team(db: Session, team_id: UUID, workspace_id: UUID) -> Team:
        """Get a specific team by ID."""
        team = db.query(Team).filter(Team.id == team_id, Team.workspace_id == workspace_id).first()
        if not team:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
        return team

    @staticmethod
    async def update_team(
        db: Session, team_id: UUID, workspace_id: UUID, request: UpdateTeamRequest
    ) -> Team:
        """Update a team."""
        team = await TeamService.get_team(db, team_id, workspace_id)

        # Check slug uniqueness if being updated
        if request.slug and request.slug != team.slug:
            existing = (
                db.query(Team)
                .filter(
                    Team.domain_id == team.domain_id, Team.slug == request.slug, Team.id != team_id
                )
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Team with slug '{request.slug}' already exists in this domain",
                )

        # Update fields
        update_data = request.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(team, field, value)

        db.commit()
        db.refresh(team)
        return team

    @staticmethod
    async def delete_team(db: Session, team_id: UUID, workspace_id: UUID) -> None:
        """Delete a team."""
        team = await TeamService.get_team(db, team_id, workspace_id)
        db.delete(team)
        db.commit()

    @staticmethod
    async def add_member(
        db: Session, team_id: UUID, workspace_id: UUID, request: AddTeamMemberRequest
    ) -> None:
        """Add a member to a team."""
        await TeamService.get_team(db, team_id, workspace_id)

        # Check if user exists
        user = db.query(User).filter(User.id == request.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Check if already a member
        existing = db.execute(
            select(team_members).where(
                and_(team_members.c.team_id == team_id, team_members.c.user_id == request.user_id)
            )
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of this team",
            )

        # Add member
        stmt = team_members.insert().values(
            team_id=team_id, user_id=request.user_id, role=request.role
        )
        db.execute(stmt)
        db.commit()

    @staticmethod
    async def remove_member(db: Session, team_id: UUID, workspace_id: UUID, user_id: UUID) -> None:
        """Remove a member from a team."""
        await TeamService.get_team(db, team_id, workspace_id)

        # Check if user is a member
        existing = db.execute(
            select(team_members).where(
                and_(team_members.c.team_id == team_id, team_members.c.user_id == user_id)
            )
        ).first()
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User is not a member of this team"
            )

        # Remove member
        stmt = team_members.delete().where(
            and_(team_members.c.team_id == team_id, team_members.c.user_id == user_id)
        )
        db.execute(stmt)
        db.commit()

    @staticmethod
    async def update_member_role(
        db: Session,
        team_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        request: UpdateTeamMemberRequest,
    ) -> None:
        """Update a team member's role."""
        await TeamService.get_team(db, team_id, workspace_id)

        # Check if user is a member
        existing = db.execute(
            select(team_members).where(
                and_(team_members.c.team_id == team_id, team_members.c.user_id == user_id)
            )
        ).first()
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User is not a member of this team"
            )

        # Update role
        stmt = (
            team_members.update()
            .where(and_(team_members.c.team_id == team_id, team_members.c.user_id == user_id))
            .values(role=request.role)
        )
        db.execute(stmt)
        db.commit()

    @staticmethod
    async def get_members(
        db: Session, team_id: UUID, workspace_id: UUID
    ) -> list[TeamMemberResponse]:
        """Get all members of a team."""
        await TeamService.get_team(db, team_id, workspace_id)

        # Join team_members with users
        stmt = (
            select(
                team_members.c.user_id,
                team_members.c.role,
                team_members.c.joined_at,
                User.email,
                User.full_name,
            )
            .join(User, team_members.c.user_id == User.id)
            .where(team_members.c.team_id == team_id)
        )
        results = db.execute(stmt).all()

        return [
            TeamMemberResponse(
                user_id=row.user_id,
                role=row.role,
                joined_at=row.joined_at,
                email=row.email,
                full_name=row.full_name,
            )
            for row in results
        ]

    @staticmethod
    async def get_hierarchy(db: Session, workspace_id: UUID) -> dict[str, Any]:
        """Get the complete workspace → domain → team hierarchy."""

        domains = db.query(Domain).filter(Domain.workspace_id == workspace_id).all()

        hierarchy_domains = []
        for domain in domains:
            teams = db.query(Team).filter(Team.domain_id == domain.id).all()

            domain_data = {
                "id": str(domain.id),
                "name": domain.name,
                "slug": domain.slug,
                "description": domain.description,
                "teams": [
                    {
                        "id": str(team.id),
                        "name": team.name,
                        "slug": team.slug,
                        "description": team.description,
                        "is_active": team.is_active,
                    }
                    for team in teams
                ],
            }
            hierarchy_domains.append(domain_data)

        return {
            "workspace_id": str(workspace_id),
            "organization_name": "Workspace",
            "domains": hierarchy_domains,
        }
