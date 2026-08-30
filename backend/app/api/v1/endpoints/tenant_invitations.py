"""
Tenant invitation endpoints (GAP-004 fix).

Provides the missing invitation workflow for bringing new users into an
existing tenant:

    POST   /api/v1/tenants/{tenant_id}/invitations          — create invitation
    GET    /api/v1/tenants/{tenant_id}/invitations          — list invitations
    DELETE /api/v1/tenants/{tenant_id}/invitations/{id}     — revoke

Accepting an invitation happens via ``POST /api/v1/auth/register`` with the
``invitation_token`` field (see schemas/auth.py).

Authorization
-------------
``platform_admin`` or any user whose ``users.tenant_id == path tenant_id``
AND who holds ``workspace_administrator`` in the tenant may issue invitations
(tenant-admin capability).  Matches BUG-006/007 widening.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    TenantAPIError,
    get_actor_context,
    validate_uuid_path_param,
)
from app.core.config import settings
from app.models.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_id}/invitations", tags=["tenant-invitations"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_ALLOWED_WORKSPACE_ROLES: frozenset = frozenset(
    {
        "workspace_administrator",
        "data_engineer",
        "data_steward",
        "business_analyst",
        "governance_viewer",
    }
)


class CreateInvitationRequest(BaseModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=255)
    workspace_id: UUID | None = Field(
        default=None,
        description="Workspace to attach the user to on acceptance. "
        "If omitted, the invited user is attached to the tenant only.",
    )
    role_name: str | None = Field(
        default=None,
        description=f"One of {sorted(_ALLOWED_WORKSPACE_ROLES)}. Required when "
        "workspace_id is set.",
    )
    expires_in_hours: int = Field(default=72, ge=1, le=24 * 30)


# ---------------------------------------------------------------------------
# Authorization helpers
# ---------------------------------------------------------------------------


def _require_tenant_admin(tenant_id: UUID, actor: ActorContext, db: Session) -> None:
    """Allow platform_admin OR tenant admin (user.tenant_id matches + has
    workspace_administrator in that tenant).

    Raises TenantAPIError(403) if neither path is satisfied.
    """
    if actor.actor_role == "platform_admin":
        return

    # First-class tenant_admin: JWT tenant_id must match path tenant_id.
    if actor.actor_role == "tenant_admin":
        if getattr(actor, "tenant_id", None) is not None and str(actor.tenant_id) == str(tenant_id):
            return
        raise TenantAPIError(
            status_code=403,
            code="forbidden",
            message="Tenant admin privileges do not extend to this tenant.",
        )

    row = db.execute(
        text(
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
            message="Tenant admin privileges required (platform_admin or "
            "workspace_administrator in this tenant).",
        )


def _serialize_invitation(row: Any, include_token: bool = False) -> dict[str, Any]:
    data = {
        "invitation_id": str(row.id),
        "tenant_id": str(row.tenant_id) if row.tenant_id else None,
        "workspace_id": str(row.workspace_id) if row.workspace_id else None,
        "email": row.email,
        "role": row.role,
        "status": row.status,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
    }
    if include_token:
        data["token"] = row.token
        base = settings.APP_PUBLIC_URL.rstrip("/")
        data["acceptance_url"] = f"{base}/auth/accept-invitation?token={row.token}"
    return data


# ---------------------------------------------------------------------------
# POST /api/v1/tenants/{tenant_id}/invitations
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
def create_invitation(
    tenant_id: str,
    body: CreateInvitationRequest,
    actor: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Issue an invitation.  Returns the acceptance token ONCE."""
    validated_tenant_id = validate_uuid_path_param(tenant_id, "tenant_id")
    _require_tenant_admin(validated_tenant_id, actor, db)

    if body.workspace_id is not None and not body.role_name:
        raise TenantAPIError(
            422,
            "validation_error",
            "role_name is required when workspace_id is provided.",
            fields=[{"field": "role_name", "reason": "required"}],
        )
    if body.role_name and body.role_name not in _ALLOWED_WORKSPACE_ROLES:
        raise TenantAPIError(
            422,
            "validation_error",
            f"role_name must be one of {sorted(_ALLOWED_WORKSPACE_ROLES)}.",
            fields=[{"field": "role_name", "reason": "unknown_role"}],
        )

    if body.workspace_id is not None:
        ws_row = db.execute(
            text("SELECT tenant_id FROM control.workspaces WHERE workspace_id = :ws LIMIT 1"),
            {"ws": str(body.workspace_id)},
        ).fetchone()
        if not ws_row or str(ws_row.tenant_id) != str(validated_tenant_id):
            raise TenantAPIError(
                422,
                "validation_error",
                "workspace_id does not belong to this tenant.",
                fields=[{"field": "workspace_id", "reason": "cross_tenant"}],
            )

    # Enforce one pending invitation per email per tenant.
    dup = db.execute(
        text(
            "SELECT 1 FROM invitations "
            "WHERE LOWER(email) = LOWER(:email) "
            "  AND tenant_id = :tenant_id "
            "  AND COALESCE(status,'pending') = 'pending' "
            "  AND accepted = FALSE "
            "LIMIT 1"
        ),
        {"email": body.email, "tenant_id": str(validated_tenant_id)},
    ).fetchone()
    if dup:
        raise TenantAPIError(
            422,
            "duplicate_invitation",
            "A pending invitation already exists for this email in this tenant.",
        )

    token = secrets.token_urlsafe(48)
    inv_id = uuid4()
    expires_at = datetime.now(UTC) + timedelta(hours=body.expires_in_hours)

    row = db.execute(
        text(
            """
            INSERT INTO invitations (
                id, workspace_id, tenant_id, email, invitee_name,
                role, token, invited_by, expires_at, accepted, status
            ) VALUES (
                :id, :ws, :tenant_id, :email, :full_name,
                :role, :token, :invited_by, :expires_at, FALSE, 'pending'
            )
            RETURNING id, workspace_id, tenant_id, email, role, token,
                      expires_at, status, accepted, created_at,
                      NULL::timestamptz AS accepted_at
            """
        ),
        {
            "id": str(inv_id),
            "ws": str(body.workspace_id) if body.workspace_id else None,
            "tenant_id": str(validated_tenant_id),
            "email": body.email,
            "full_name": body.full_name,
            "role": body.role_name,
            "token": token,
            "invited_by": str(actor.actor_id),
            "expires_at": expires_at,
        },
    ).fetchone()
    db.commit()

    logger.info(
        "invitation_created tenant_id=%s email=%s actor_id=%s",
        validated_tenant_id,
        body.email,
        actor.actor_id,
    )

    return JSONResponse(
        status_code=201,
        content={"data": _serialize_invitation(row, include_token=True)},
    )


# ---------------------------------------------------------------------------
# GET /api/v1/tenants/{tenant_id}/invitations
# ---------------------------------------------------------------------------


@router.get("", status_code=200)
def list_invitations(
    tenant_id: str,
    actor: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> JSONResponse:
    validated_tenant_id = validate_uuid_path_param(tenant_id, "tenant_id")
    _require_tenant_admin(validated_tenant_id, actor, db)

    rows = db.execute(
        text(
            """
            SELECT id, workspace_id, tenant_id, email, role, token,
                   expires_at, COALESCE(status,'pending') AS status,
                   accepted, created_at, accepted_at
            FROM invitations
            WHERE tenant_id = :tenant_id
            ORDER BY created_at DESC
            LIMIT 200
            """
        ),
        {"tenant_id": str(validated_tenant_id)},
    ).fetchall()

    return JSONResponse(
        status_code=200,
        content={"data": [_serialize_invitation(r, include_token=False) for r in rows]},
    )


# ---------------------------------------------------------------------------
# DELETE /api/v1/tenants/{tenant_id}/invitations/{invitation_id}
# ---------------------------------------------------------------------------


@router.delete("/{invitation_id}", status_code=200)
def revoke_invitation(
    tenant_id: str,
    invitation_id: str,
    actor: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> JSONResponse:
    validated_tenant_id = validate_uuid_path_param(tenant_id, "tenant_id")
    validated_inv_id = validate_uuid_path_param(invitation_id, "invitation_id")
    _require_tenant_admin(validated_tenant_id, actor, db)

    result = db.execute(
        text(
            "UPDATE invitations SET status='revoked' "
            "WHERE id = :id "
            "  AND tenant_id = :tenant_id "
            "  AND accepted = FALSE "
            "  AND COALESCE(status,'pending') = 'pending'"
        ),
        {"id": str(validated_inv_id), "tenant_id": str(validated_tenant_id)},
    )
    db.commit()
    if result.rowcount == 0:
        raise TenantAPIError(
            404,
            "not_found",
            "Invitation not found, already accepted, or already revoked.",
        )
    return JSONResponse(status_code=200, content={"data": {"revoked": True}})
