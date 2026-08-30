"""
Metadata Search API Endpoints
F101 — Metadata Search Abstraction Layer
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.schemas.metadata_search import (
    MetadataSearchResponse,
    MetadataSyncResponse,
    MetadataTermCreate,
    MetadataTermResponse,
)
from app.services.auth.jwt import get_current_user
from app.services.metadata_search.search_service import MetadataSearchService
from app.services.metadata_search.sync_service import MetadataSyncService
from app.services.metadata_search.term_service import MetadataTermService

router = APIRouter()

_sync_service = MetadataSyncService()
_search_service = MetadataSearchService()
_term_service = MetadataTermService()


def _resolve_tenant_id(workspace_id: UUID, current_user: User, db: Session) -> UUID:
    PLATFORM_ROLES = {"platform_admin", "platform_viewer"}
    is_platform_op = getattr(current_user, "platform_role", None) in PLATFORM_ROLES
    if not is_platform_op and current_user.tenant_id:
        return current_user.tenant_id
    row = db.execute(
        text("SELECT tenant_id FROM control.workspaces WHERE workspace_id = :wid LIMIT 1"),
        {"wid": str(workspace_id)},
    ).fetchone()
    if not row or not row.tenant_id:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return row.tenant_id


@router.post(
    "/workspaces/{workspace_id}/metadata/sync",
    response_model=MetadataSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Sync metadata asset index",
    description="Pulls datasets, fields, and data sources into the metadata asset index.",
    tags=["metadata"],
)
def sync_metadata(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> MetadataSyncResponse:
    return _sync_service.sync_workspace(db, workspace_id)


@router.get(
    "/workspaces/{workspace_id}/metadata/search",
    response_model=MetadataSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search metadata assets and glossary terms",
    description="Combined ranked search across assets and terms using full-text, trigram, and exact matching.",
    tags=["metadata"],
)
def search_metadata(
    workspace_id: UUID,
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    asset_type: str | None = Query(None, description="Filter by asset type"),
    domain: str | None = Query(None, description="Filter by business domain"),
    limit: int = Query(20, ge=1, le=100, description="Max results per category"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> MetadataSearchResponse:
    return _search_service.search(
        db,
        workspace_id,
        q,
        asset_type=asset_type,
        domain=domain,
        limit=limit,
    )


@router.post(
    "/workspaces/{workspace_id}/metadata/terms",
    response_model=MetadataTermResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a glossary term",
    description="Creates a new glossary term in the metadata term index.",
    tags=["metadata"],
)
def create_term(
    workspace_id: UUID,
    payload: MetadataTermCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MetadataTermResponse:
    tenant_id = _resolve_tenant_id(workspace_id, current_user, db)
    return _term_service.create_term(db, workspace_id, tenant_id, payload)


@router.get(
    "/workspaces/{workspace_id}/metadata/terms",
    response_model=list[MetadataTermResponse],
    status_code=status.HTTP_200_OK,
    summary="List glossary terms",
    description="Lists glossary terms in the workspace, optionally filtered by domain.",
    tags=["metadata"],
)
def list_terms(
    workspace_id: UUID,
    domain: str | None = Query(None, description="Filter by domain"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MetadataTermResponse]:
    tenant_id = _resolve_tenant_id(workspace_id, current_user, db)
    return _term_service.list_terms(db, tenant_id, domain=domain, limit=limit)
