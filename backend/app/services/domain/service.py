"""Domain service for managing workspace domains."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.domain import Domain
from app.schemas.domain import CreateDomainRequest, UpdateDomainRequest


class DomainService:
    """Service for domain management operations."""

    @staticmethod
    async def create_domain(
        db: Session, workspace_id: UUID, request: CreateDomainRequest, user_id: UUID
    ) -> Domain:
        """Create a new domain in a workspace."""
        # Check if slug already exists in this workspace
        existing = (
            db.query(Domain)
            .filter(Domain.workspace_id == workspace_id, Domain.slug == request.slug)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Domain with slug '{request.slug}' already exists in this organization",
            )

        # Create domain
        domain = Domain(
            workspace_id=workspace_id,
            name=request.name,
            description=request.description,
            slug=request.slug,
            metadata=request.metadata or {},
            created_by=user_id,
        )
        db.add(domain)
        db.commit()
        db.refresh(domain)
        return domain

    @staticmethod
    async def get_domains(
        db: Session, workspace_id: UUID, skip: int = 0, limit: int = 100
    ) -> list[Domain]:
        """Get all domains for an organization."""
        domains = (
            db.query(Domain)
            .filter(Domain.workspace_id == workspace_id)
            .offset(skip)
            .limit(limit)
            .all()
        )
        return domains

    @staticmethod
    async def get_domain(db: Session, domain_id: UUID, workspace_id: UUID) -> Domain:
        """Get a specific domain by ID."""
        domain = (
            db.query(Domain)
            .filter(Domain.id == domain_id, Domain.workspace_id == workspace_id)
            .first()
        )
        if not domain:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
        return domain

    @staticmethod
    async def update_domain(
        db: Session, domain_id: UUID, workspace_id: UUID, request: UpdateDomainRequest
    ) -> Domain:
        """Update a domain."""
        domain = await DomainService.get_domain(db, domain_id, workspace_id)

        # Check slug uniqueness if being updated
        if request.slug and request.slug != domain.slug:
            existing = (
                db.query(Domain)
                .filter(
                    Domain.workspace_id == workspace_id,
                    Domain.slug == request.slug,
                    Domain.id != domain_id,
                )
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Domain with slug '{request.slug}' already exists",
                )

        # Update fields
        update_data = request.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(domain, field, value)

        db.commit()
        db.refresh(domain)
        return domain

    @staticmethod
    async def delete_domain(db: Session, domain_id: UUID, workspace_id: UUID) -> None:
        """Delete a domain (cascades to teams)."""
        domain = await DomainService.get_domain(db, domain_id, workspace_id)
        db.delete(domain)
        db.commit()

    @staticmethod
    async def get_domain_stats(db: Session, domain_id: UUID, workspace_id: UUID) -> dict:
        """Get statistics for a domain."""
        domain = await DomainService.get_domain(db, domain_id, workspace_id)

        from app.models.team import Team

        teams_count = db.query(Team).filter(Team.domain_id == domain_id).count()

        return {"teams_count": teams_count, "is_active": domain.is_active}
