"""Domain API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.schemas.domain import (
    CreateDomainRequest,
    DomainResponse,
    UpdateDomainRequest,
)
from app.services.auth.jwt import get_current_user
from app.services.domain.service import DomainService

router = APIRouter(prefix="/workspaces/{workspace_id}/domains", tags=["Domains"])


@router.post("", response_model=DomainResponse, status_code=status.HTTP_201_CREATED)
async def create_domain(
    workspace_id: UUID,
    request: CreateDomainRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new domain in an organization."""
    domain = await DomainService.create_domain(db, workspace_id, request, current_user.id)

    return DomainResponse(
        id=domain.id,
        workspace_id=domain.workspace_id,
        name=domain.name,
        description=domain.description,
        slug=domain.slug,
        is_active=domain.is_active,
        metadata=domain.metadata,
        created_by=domain.created_by,
        created_at=domain.created_at,
        updated_at=domain.updated_at,
    )


@router.get("", response_model=list[DomainResponse])
async def list_domains(
    workspace_id: UUID,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all domains in an organization."""
    domains = await DomainService.get_domains(db, workspace_id, skip, limit)

    return [
        DomainResponse(
            id=d.id,
            workspace_id=d.workspace_id,
            name=d.name,
            description=d.description,
            slug=d.slug,
            is_active=d.is_active,
            metadata=d.metadata,
            created_by=d.created_by,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in domains
    ]


@router.get("/{domain_id}", response_model=DomainResponse)
async def get_domain(
    workspace_id: UUID,
    domain_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific domain."""
    domain = await DomainService.get_domain(db, domain_id, workspace_id)

    return DomainResponse(
        id=domain.id,
        workspace_id=domain.workspace_id,
        name=domain.name,
        description=domain.description,
        slug=domain.slug,
        is_active=domain.is_active,
        metadata=domain.metadata,
        created_by=domain.created_by,
        created_at=domain.created_at,
        updated_at=domain.updated_at,
    )


@router.patch("/{domain_id}", response_model=DomainResponse)
async def update_domain(
    workspace_id: UUID,
    domain_id: UUID,
    request: UpdateDomainRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a domain."""
    domain = await DomainService.update_domain(db, domain_id, workspace_id, request)

    return DomainResponse(
        id=domain.id,
        workspace_id=domain.workspace_id,
        name=domain.name,
        description=domain.description,
        slug=domain.slug,
        is_active=domain.is_active,
        metadata=domain.metadata,
        created_by=domain.created_by,
        created_at=domain.created_at,
        updated_at=domain.updated_at,
    )


@router.delete("/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_domain(
    workspace_id: UUID,
    domain_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a domain (cascades to teams)."""
    await DomainService.delete_domain(db, domain_id, workspace_id)
    return None
