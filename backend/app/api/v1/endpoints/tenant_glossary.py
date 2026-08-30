"""
F130 — Tenant Glossary API
============================

Routes (all under /api/v1/tenants/{tenant_id}/glossary):
  GET    /                       — list terms
  POST   /                       — create term
  GET    /{term_id}              — get term
  PATCH  /{term_id}              — update term
  PUT    /{term_id}              — update term (alias for PATCH)
  DELETE /{term_id}              — delete term
  POST   /bulk                   — bulk create terms
  POST   /bulk-delete            — bulk delete by ids
  POST   /import                 — bulk CSV import (multipart file or JSON body)
  GET    /export                 — CSV export
  GET    /{term_id}/lineage      — resolve linked assets (lineage view)
  POST   /{term_id}/links        — set linked_asset_ids for a term

Auth: JWT required.
  Write: require_tenant_write_access (platform_admin OR tenant admin of path)
  Read:  require_tenant_read_access  (platform_admin/viewer OR tenant admin of path)
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    TenantAPIError,
    require_tenant_read_access,
    require_tenant_write_access,
    validate_uuid_path_param,
)
from app.models.database import get_db
from app.schemas.glossary import GlossaryTermCreate, GlossaryTermUpdate
from app.services.glossary.service import GlossaryService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/tenants/{tenant_id}/glossary",
    tags=["glossary"],
)

_service = GlossaryService()


# ──────────────────────────────────────────────────────────────────────────────
# Request schemas
# ──────────────────────────────────────────────────────────────────────────────


class CsvImportRequest(BaseModel):
    content: str = Field(..., description="Raw CSV content as a string.")


class BulkCreateRequest(BaseModel):
    items: list[GlossaryTermCreate] = Field(..., min_length=1, max_length=500)


class BulkDeleteRequest(BaseModel):
    term_ids: list[str] = Field(..., min_length=1, max_length=500)


class LinkAssetsRequest(BaseModel):
    asset_ids: list[str] = Field(default_factory=list, max_length=200)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _parse_tenant_id(tenant_id: str) -> UUID:
    return validate_uuid_path_param(tenant_id, "tenant_id")


def _parse_term_id(term_id: str) -> UUID:
    return validate_uuid_path_param(term_id, "term_id")


def _term_response(term) -> dict:
    d = term.model_dump() if hasattr(term, "model_dump") else dict(term)
    for k, v in d.items():
        if isinstance(v, UUID):
            d[k] = str(v)
    return d


def _resolve_default_workspace_id(db: Session, tenant_id: UUID) -> UUID:
    """Pick the oldest non-archived workspace in the tenant as the default owner
    for tenant-scoped glossary writes. Raises 409 if none exists."""
    row = db.execute(
        text(
            """
            SELECT workspace_id
            FROM control.workspaces
            WHERE tenant_id = :tid
              AND status != 'archived'
            ORDER BY created_at ASC
            LIMIT 1
            """
        ),
        {"tid": str(tenant_id)},
    ).fetchone()
    if row is None:
        raise TenantAPIError(
            status_code=409,
            code="no_workspace",
            message="Tenant has no active workspace to own glossary writes.",
        )
    return row.workspace_id if isinstance(row.workspace_id, UUID) else UUID(str(row.workspace_id))


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────


@router.get("", status_code=status.HTTP_200_OK)
async def list_terms(
    tenant_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str | None = Query(None),
    domain: str | None = Query(None),
    actor: ActorContext = Depends(require_tenant_read_access()),
    db: Session = Depends(get_db),
):
    tid = _parse_tenant_id(tenant_id)
    result = _service.list_terms(
        db, tid, search=search, domain=domain, page=page, page_size=page_size
    )
    return {
        "items": [_term_response(t) for t in result.items],
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_term(
    tenant_id: str,
    body: GlossaryTermCreate,
    actor: ActorContext = Depends(require_tenant_write_access()),
    db: Session = Depends(get_db),
):
    tid = _parse_tenant_id(tenant_id)
    wid = _resolve_default_workspace_id(db, tid)
    term = _service.create_term(db, wid, tid, body)
    return _term_response(term)


# ──────────────────────────────────────────────────────────────────────────────
# Bulk operations — MUST be registered BEFORE /{term_id} routes so FastAPI
# does not match e.g. GET /export against GET /{term_id}.
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/bulk", status_code=status.HTTP_200_OK)
async def bulk_create_terms(
    tenant_id: str,
    body: BulkCreateRequest,
    actor: ActorContext = Depends(require_tenant_write_access()),
    db: Session = Depends(get_db),
):
    """Bulk create glossary terms. Returns counts + per-item errors."""
    tid = _parse_tenant_id(tenant_id)
    wid = _resolve_default_workspace_id(db, tid)
    created: list[dict] = []
    errors: list[dict] = []
    for idx, item in enumerate(body.items):
        try:
            term = _service.create_term(db, wid, tid, item)
            created.append(_term_response(term))
        except Exception as exc:  # noqa: BLE001
            logger.warning("bulk_create_terms item %d failed: %s", idx, exc)
            errors.append({"index": idx, "business_name": item.business_name, "reason": str(exc)})
    return {
        "created_count": len(created),
        "error_count": len(errors),
        "items": created,
        "errors": errors,
    }


@router.post("/bulk-delete", status_code=status.HTTP_200_OK)
async def bulk_delete_terms(
    tenant_id: str,
    body: BulkDeleteRequest,
    actor: ActorContext = Depends(require_tenant_write_access()),
    db: Session = Depends(get_db),
):
    """Bulk delete glossary terms by id."""
    tid = _parse_tenant_id(tenant_id)
    deleted = 0
    missing: list[str] = []
    for raw_id in body.term_ids:
        try:
            tmid = validate_uuid_path_param(raw_id, "term_id")
        except Exception:
            missing.append(raw_id)
            continue
        if _service.delete_term(db, tid, tmid):
            deleted += 1
        else:
            missing.append(raw_id)
    return {"deleted_count": deleted, "missing_count": len(missing), "missing_ids": missing}


@router.post("/import", status_code=status.HTTP_200_OK)
async def import_csv(
    tenant_id: str,
    actor: ActorContext = Depends(require_tenant_write_access()),
    db: Session = Depends(get_db),
    file: UploadFile | None = File(None),
    body: CsvImportRequest | None = None,
):
    """Accepts either a multipart file upload (field name `file`) or a JSON body
    with `{content: "..."}`. The frontend uses multipart."""
    tid = _parse_tenant_id(tenant_id)
    wid = _resolve_default_workspace_id(db, tid)

    if file is not None:
        raw = await file.read()
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = raw.decode("latin-1")
    elif body is not None:
        content = body.content
    else:
        raise TenantAPIError(
            status_code=400,
            code="missing_csv",
            message="Provide either a `file` multipart upload or JSON body with `content`.",
        )

    result = _service.import_csv(db, wid, tid, content)
    return result.model_dump()


@router.get("/export", status_code=status.HTTP_200_OK)
async def export_csv(
    tenant_id: str,
    actor: ActorContext = Depends(require_tenant_read_access()),
    db: Session = Depends(get_db),
):
    tid = _parse_tenant_id(tenant_id)
    csv_content = _service.export_csv(db, tid)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=glossary_{tid}.csv"},
    )


# ──────────────────────────────────────────────────────────────────────────────
# Per-term routes
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/{term_id}", status_code=status.HTTP_200_OK)
async def get_term(
    tenant_id: str,
    term_id: str,
    actor: ActorContext = Depends(require_tenant_read_access()),
    db: Session = Depends(get_db),
):
    tid = _parse_tenant_id(tenant_id)
    tmid = _parse_term_id(term_id)
    term = _service.get_term(db, tid, tmid)
    if term is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "TERM_NOT_FOUND",
                    "message": "Glossary term not found.",
                    "fields": None,
                }
            },
        )
    return _term_response(term)


async def _update_term_impl(tenant_id: str, term_id: str, body: GlossaryTermUpdate, db: Session):
    tid = _parse_tenant_id(tenant_id)
    tmid = _parse_term_id(term_id)
    term = _service.update_term(db, tid, tmid, body)
    if term is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "TERM_NOT_FOUND",
                    "message": "Glossary term not found.",
                    "fields": None,
                }
            },
        )
    return _term_response(term)


@router.patch("/{term_id}", status_code=status.HTTP_200_OK)
async def update_term(
    tenant_id: str,
    term_id: str,
    body: GlossaryTermUpdate,
    actor: ActorContext = Depends(require_tenant_write_access()),
    db: Session = Depends(get_db),
):
    return await _update_term_impl(tenant_id, term_id, body, db)


@router.put("/{term_id}", status_code=status.HTTP_200_OK)
async def update_term_put(
    tenant_id: str,
    term_id: str,
    body: GlossaryTermUpdate,
    actor: ActorContext = Depends(require_tenant_write_access()),
    db: Session = Depends(get_db),
):
    # PUT alias for PATCH (frontend uses PUT).
    return await _update_term_impl(tenant_id, term_id, body, db)


@router.delete("/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_term(
    tenant_id: str,
    term_id: str,
    actor: ActorContext = Depends(require_tenant_write_access()),
    db: Session = Depends(get_db),
):
    tid = _parse_tenant_id(tenant_id)
    tmid = _parse_term_id(term_id)
    deleted = _service.delete_term(db, tid, tmid)
    if not deleted:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "TERM_NOT_FOUND",
                    "message": "Glossary term not found.",
                    "fields": None,
                }
            },
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ──────────────────────────────────────────────────────────────────────────────
# Lineage
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/{term_id}/lineage", status_code=status.HTTP_200_OK)
async def get_term_lineage(
    tenant_id: str,
    term_id: str,
    actor: ActorContext = Depends(require_tenant_read_access()),
    db: Session = Depends(get_db),
):
    """Resolve the linked asset IDs on a term against `control.metadata_asset_index`
    and return rich lineage rows so the UI can render asset names + types."""
    tid = _parse_tenant_id(tenant_id)
    tmid = _parse_term_id(term_id)
    term = _service.get_term(db, tid, tmid)
    if term is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "TERM_NOT_FOUND",
                    "message": "Glossary term not found.",
                    "fields": None,
                }
            },
        )

    linked_ids = [str(a) for a in (term.linked_asset_ids or []) if a]
    assets: list[dict] = []
    if linked_ids:
        rows = db.execute(
            text(
                """
                SELECT a.asset_id, a.asset_type, a.name, a.display_name,
                       a.description, a.data_type, a.parent_asset_id,
                       a.workspace_id, a.source_table, a.source_id
                FROM control.metadata_asset_index a
                JOIN control.workspaces w ON w.workspace_id = a.workspace_id
                WHERE w.tenant_id = :tid
                  AND a.asset_id::text = ANY(:ids)
                """
            ),
            {"tid": str(tid), "ids": linked_ids},
        ).fetchall()
        found_ids = {str(r.asset_id) for r in rows}
        for r in rows:
            assets.append(
                {
                    "asset_id": str(r.asset_id),
                    "asset_type": r.asset_type,
                    "name": r.name,
                    "display_name": r.display_name,
                    "description": r.description,
                    "data_type": r.data_type,
                    "parent_asset_id": str(r.parent_asset_id) if r.parent_asset_id else None,
                    "workspace_id": str(r.workspace_id),
                    "source_table": r.source_table,
                    "source_id": str(r.source_id) if r.source_id else None,
                }
            )
        # Track orphan links so UI can surface stale references.
        orphans = [aid for aid in linked_ids if aid not in found_ids]
    else:
        orphans = []

    return {
        "term_id": str(tmid),
        "business_name": term.business_name,
        "linked_count": len(linked_ids),
        "resolved_count": len(assets),
        "assets": assets,
        "orphan_asset_ids": orphans,
    }


@router.post("/{term_id}/links", status_code=status.HTTP_200_OK)
async def set_term_links(
    tenant_id: str,
    term_id: str,
    body: LinkAssetsRequest,
    actor: ActorContext = Depends(require_tenant_write_access()),
    db: Session = Depends(get_db),
):
    """Replace the term's linked_asset_ids with the provided list."""
    tid = _parse_tenant_id(tenant_id)
    tmid = _parse_term_id(term_id)
    # Validate every id is a UUID up-front
    for raw in body.asset_ids:
        validate_uuid_path_param(raw, "asset_id")
    term = _service.update_term(
        db,
        tid,
        tmid,
        GlossaryTermUpdate(linked_asset_ids=body.asset_ids),
    )
    if term is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "TERM_NOT_FOUND",
                    "message": "Glossary term not found.",
                    "fields": None,
                }
            },
        )
    return _term_response(term)
