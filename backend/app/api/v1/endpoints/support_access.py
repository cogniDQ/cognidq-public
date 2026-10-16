"""
Ephemeral support-access grants.

A ``tenant_admin`` grants time-limited, audited access to ``platform_admin``
for their own tenant (or one workspace within it), so the platform operator
can troubleshoot without having standing access to client content.

    POST   /api/v1/tenants/{tenant_id}/support-access-grants          — tenant_admin grants
    GET    /api/v1/tenants/{tenant_id}/support-access-grants          — tenant_admin's own list
    POST   /api/v1/tenants/{tenant_id}/support-access-grants/{id}/revoke — tenant_admin revokes
    GET    /api/v1/admin/support-access-grants/active                 — platform_admin's own view
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from sqlalchemy import text as _sql_text

from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    TenantAPIError,
    get_actor_context,
    require_read_access,
    validate_uuid_path_param,
)
from app.models.database import get_db
from app.services.audit.models import AuditEntry
from app.services.audit.service import AuditService
from app.services.support_access import service as support_access_service

router = APIRouter(tags=["support-access"])


def _require_client_tenant_admin(tenant_id: UUID, actor: ActorContext, db: Session) -> None:
    """Only the client's own tenant_admin (or a workspace_administrator in
    that tenant) may grant or revoke support access — deliberately
    excludes ``platform_admin``. The whole point of this feature is that
    the client decides when a platform operator gets in; a platform admin
    must not be able to self-grant.
    """
    if actor.actor_role == "tenant_admin":
        if getattr(actor, "tenant_id", None) is not None and str(actor.tenant_id) == str(tenant_id):
            return
        raise TenantAPIError(
            status_code=403,
            code="forbidden",
            message="Tenant admin privileges do not extend to this tenant.",
        )

    row = db.execute(
        _sql_text(
            """
            SELECT u.tenant_id AS user_tenant_id,
                   EXISTS (
                       SELECT 1
                       FROM control.workspace_role_assignments wra
                       JOIN control.workspaces w ON w.workspace_id = wra.workspace_id
                       WHERE wra.user_id = u.id
                         AND wra.role_name = 'workspace_administrator'
                         AND w.tenant_id = :tenant_id
                   ) AS is_ws_admin_in_tenant
            FROM users u
            WHERE u.id = :user_id
            """
        ),
        {"user_id": str(actor.actor_id), "tenant_id": str(tenant_id)},
    ).fetchone()

    if not row or str(row.user_tenant_id) != str(tenant_id) or not row.is_ws_admin_in_tenant:
        raise TenantAPIError(
            status_code=403,
            code="forbidden",
            message="Only the tenant's own admin may grant or revoke support access.",
        )


class CreateGrantRequest(BaseModel):
    workspace_id: UUID | None = Field(
        default=None,
        description="Limit the grant to a single workspace. Omit for tenant-wide access.",
    )
    duration_minutes: int = Field(default=60, ge=1, le=support_access_service.MAX_DURATION_MINUTES)
    reason: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# Tenant-admin side: create / list / revoke
# ---------------------------------------------------------------------------


@router.post("/tenants/{tenant_id}/support-access-grants", status_code=201)
def create_support_access_grant(
    tenant_id: str,
    body: CreateGrantRequest,
    actor: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> JSONResponse:
    validated_tenant_id = validate_uuid_path_param(tenant_id, "tenant_id")
    _require_client_tenant_admin(validated_tenant_id, actor, db)

    if body.workspace_id is not None:
        ws_row = db.execute(
            _sql_text("SELECT tenant_id FROM control.workspaces WHERE workspace_id = :ws LIMIT 1"),
            {"ws": str(body.workspace_id)},
        ).fetchone()
        if not ws_row or str(ws_row.tenant_id) != str(validated_tenant_id):
            raise TenantAPIError(
                422,
                "validation_error",
                "workspace_id does not belong to this tenant.",
                fields=[{"field": "workspace_id", "reason": "cross_tenant"}],
            )

    grant = support_access_service.create_grant(
        db,
        tenant_id=validated_tenant_id,
        granted_by_user_id=actor.actor_id,
        workspace_id=body.workspace_id,
        duration_minutes=body.duration_minutes,
        reason=body.reason,
    )

    AuditService().write(
        db,
        AuditEntry(
            tenant_id=validated_tenant_id,
            workspace_id=body.workspace_id,
            action_type="support_access_granted",
            target_entity_type="support_access_grant",
            target_entity_id=UUID(grant["id"]),
            after_state=grant,
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
        ),
    )
    db.commit()

    return JSONResponse(status_code=201, content={"data": grant})


@router.get("/tenants/{tenant_id}/support-access-grants", status_code=200)
def list_support_access_grants(
    tenant_id: str,
    actor: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> JSONResponse:
    validated_tenant_id = validate_uuid_path_param(tenant_id, "tenant_id")
    _require_client_tenant_admin(validated_tenant_id, actor, db)

    grants = support_access_service.list_grants_for_tenant(db, validated_tenant_id)
    return JSONResponse(status_code=200, content={"data": grants})


@router.post("/tenants/{tenant_id}/support-access-grants/{grant_id}/revoke", status_code=200)
def revoke_support_access_grant(
    tenant_id: str,
    grant_id: str,
    actor: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> JSONResponse:
    validated_tenant_id = validate_uuid_path_param(tenant_id, "tenant_id")
    validated_grant_id = validate_uuid_path_param(grant_id, "grant_id")
    _require_client_tenant_admin(validated_tenant_id, actor, db)

    revoked = support_access_service.revoke_grant(
        db, validated_tenant_id, validated_grant_id, actor.actor_id
    )
    if not revoked:
        raise TenantAPIError(404, "not_found", "Grant not found or already revoked.")

    AuditService().write(
        db,
        AuditEntry(
            tenant_id=validated_tenant_id,
            action_type="support_access_revoked",
            target_entity_type="support_access_grant",
            target_entity_id=validated_grant_id,
            after_state={"revoked": True},
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
        ),
    )
    db.commit()

    return JSONResponse(status_code=200, content={"data": {"revoked": True}})


# ---------------------------------------------------------------------------
# Platform-admin side: see where I currently have active access
# ---------------------------------------------------------------------------


@router.get("/admin/support-access-grants/active", status_code=200)
def list_active_grants_for_admin(
    actor: ActorContext = Depends(require_read_access()),
    db: Session = Depends(get_db),
) -> JSONResponse:
    grants = support_access_service.list_active_grants_for_platform_admin(db)
    return JSONResponse(status_code=200, content={"data": grants})
