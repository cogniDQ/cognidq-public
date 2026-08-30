"""
Business Glossary API Endpoints
F109 — Business Glossary Management Service
"""

import io
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.schemas.glossary import (
    GlossaryImportResult,
    GlossaryListResponse,
    GlossaryTermCreate,
    GlossaryTermResponse,
    GlossaryTermUpdate,
)
from app.services.auth.jwt import get_current_user
from app.services.glossary.service import GlossaryService

router = APIRouter()
_glossary_service = GlossaryService()


def _resolve_tenant_id(workspace_id: UUID, current_user: User, db: Session) -> UUID:
    """
    Resolve tenant_id for glossary operations.
    Platform operators always look up the workspace's tenant (cross-tenant support).
    Regular users use tenant_id from their profile.
    """
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
    "/workspaces/{workspace_id}/glossary",
    response_model=GlossaryTermResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a glossary term",
    tags=["glossary"],
)
def create_glossary_term(
    workspace_id: UUID,
    payload: GlossaryTermCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GlossaryTermResponse:
    tenant_id = _resolve_tenant_id(workspace_id, current_user, db)
    return _glossary_service.create_term(db, workspace_id, tenant_id, payload)


@router.get(
    "/workspaces/{workspace_id}/glossary",
    response_model=GlossaryListResponse,
    status_code=status.HTTP_200_OK,
    summary="List or search glossary terms",
    tags=["glossary"],
)
def list_glossary_terms(
    workspace_id: UUID,
    search: str = Query(None, max_length=500, description="Search text"),
    domain: str = Query(None, max_length=100, description="Filter by domain"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=200, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GlossaryListResponse:
    tenant_id = _resolve_tenant_id(workspace_id, current_user, db)
    return _glossary_service.list_terms(
        db,
        tenant_id,
        search=search,
        domain=domain,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/workspaces/{workspace_id}/glossary/{term_id}",
    response_model=GlossaryTermResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single glossary term",
    tags=["glossary"],
)
def get_glossary_term(
    workspace_id: UUID,
    term_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GlossaryTermResponse:
    tenant_id = _resolve_tenant_id(workspace_id, current_user, db)
    term = _glossary_service.get_term(db, tenant_id, term_id)
    if not term:
        raise HTTPException(status_code=404, detail="Glossary term not found")
    return term


@router.put(
    "/workspaces/{workspace_id}/glossary/{term_id}",
    response_model=GlossaryTermResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a glossary term",
    tags=["glossary"],
)
def update_glossary_term(
    workspace_id: UUID,
    term_id: UUID,
    payload: GlossaryTermUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GlossaryTermResponse:
    tenant_id = _resolve_tenant_id(workspace_id, current_user, db)
    term = _glossary_service.update_term(db, tenant_id, term_id, payload)
    if not term:
        raise HTTPException(status_code=404, detail="Glossary term not found")
    return term


@router.delete(
    "/workspaces/{workspace_id}/glossary/{term_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a glossary term",
    tags=["glossary"],
)
def delete_glossary_term(
    workspace_id: UUID,
    term_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _resolve_tenant_id(workspace_id, current_user, db)
    deleted = _glossary_service.delete_term(db, tenant_id, term_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Glossary term not found")


@router.post(
    "/workspaces/{workspace_id}/glossary/import-csv",
    response_model=GlossaryImportResult,
    status_code=status.HTTP_200_OK,
    summary="Import glossary terms from CSV",
    tags=["glossary"],
)
async def import_glossary_csv(
    workspace_id: UUID,
    file: UploadFile = File(..., description="CSV file to import"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GlossaryImportResult:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv file")

    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    tenant_id = _resolve_tenant_id(workspace_id, current_user, db)
    return _glossary_service.import_csv(db, workspace_id, tenant_id, text_content)


@router.get(
    "/workspaces/{workspace_id}/glossary/export-csv",
    status_code=status.HTTP_200_OK,
    summary="Export glossary terms to CSV",
    tags=["glossary"],
)
def export_glossary_csv(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _resolve_tenant_id(workspace_id, current_user, db)
    csv_content = _glossary_service.export_csv(db, tenant_id)
    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=glossary-export.csv"},
    )
