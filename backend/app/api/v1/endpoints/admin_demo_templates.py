"""
F134 P06 — Admin Demo Templates endpoint

GET /admin/demo-templates   — list all enabled templates (platform_admin only)
GET /admin/demo-templates/{id} — get single template by id
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v1.dependencies.tenant_auth import ActorContext, require_write_access
from app.models.database import get_db
from app.services.sandbox.demo_template_repository import DemoTemplateRepository

router = APIRouter(tags=["demo-sandbox-admin"])


@router.get("/admin/demo-templates")
async def list_demo_templates(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_write_access()),
) -> JSONResponse:
    repo = DemoTemplateRepository(db)
    rows = repo.list_enabled()
    return JSONResponse(
        status_code=200,
        content={
            "items": [_serialize(r) for r in rows],
            "total": len(rows),
        },
    )


@router.get("/admin/demo-templates/{template_id}")
async def get_demo_template(
    template_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_write_access()),
) -> JSONResponse:
    repo = DemoTemplateRepository(db)
    row = repo.find_by_id(template_id)
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "Template not found."}},
        )
    return JSONResponse(status_code=200, content=_serialize(row))


def _serialize(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out
