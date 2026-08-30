"""
Tenant member management endpoints.

Exposes:
    GET /api/v1/tenants/{tenant_id}/members

Returns every user whose ``users.tenant_id`` equals the path tenant, together
with their workspace role assignments inside that tenant. This powers the
Tenant Admin "assignment matrix" UI.

Authorization: platform_admin OR first-class tenant_admin whose JWT
``tenant_id`` matches the path.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    TenantAPIError,
    get_actor_context,
    validate_uuid_path_param,
)
from app.models.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_id}/members", tags=["tenant-members"])


def _require_tenant_scope(tenant_id: UUID, actor: ActorContext) -> None:
    if actor.actor_role == "platform_admin":
        return
    if (
        actor.actor_role == "tenant_admin"
        and actor.tenant_id is not None
        and str(actor.tenant_id) == str(tenant_id)
    ):
        return
    raise TenantAPIError(
        status_code=403,
        code="forbidden",
        message="Tenant admin privileges required for this tenant.",
    )


@router.get("", status_code=200)
def list_tenant_members(
    tenant_id: str,
    actor: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """List tenant users with their workspace role assignments."""
    validated = validate_uuid_path_param(tenant_id, "tenant_id")
    _require_tenant_scope(validated, actor)

    users = (
        db.execute(
            text(
                """
            SELECT u.id, u.email, u.full_name, u.platform_role, u.status
            FROM users u
            WHERE u.tenant_id = :tid
            ORDER BY u.email
            """
            ),
            {"tid": str(validated)},
        )
        .mappings()
        .all()
    )

    if not users:
        return JSONResponse(status_code=200, content={"data": []})

    user_ids = [str(u["id"]) for u in users]
    assignments = (
        db.execute(
            text(
                """
            SELECT wra.user_id, wra.workspace_id, wra.role_name,
                   w.workspace_name, wra.granted_at
            FROM control.workspace_role_assignments wra
            JOIN control.workspaces w ON w.workspace_id = wra.workspace_id
            WHERE w.tenant_id = :tid
              AND wra.user_id = ANY(CAST(:uids AS uuid[]))
            """
            ),
            {"tid": str(validated), "uids": user_ids},
        )
        .mappings()
        .all()
    )

    by_user: dict[str, list[dict[str, Any]]] = {uid: [] for uid in user_ids}
    for a in assignments:
        by_user[str(a["user_id"])].append(
            {
                "workspace_id": str(a["workspace_id"]),
                "workspace_name": a["workspace_name"],
                "role_name": a["role_name"],
                "granted_at": a["granted_at"].isoformat() if a["granted_at"] else None,
            }
        )

    data = [
        {
            "user_id": str(u["id"]),
            "email": u["email"],
            "full_name": u["full_name"],
            "platform_role": u["platform_role"],
            "status": u["status"].value if hasattr(u["status"], "value") else u["status"],
            "assignments": by_user[str(u["id"])],
        }
        for u in users
    ]

    return JSONResponse(status_code=200, content={"data": data})
