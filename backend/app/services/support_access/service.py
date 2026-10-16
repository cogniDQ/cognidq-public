"""
Support access grants.

A ``tenant_admin`` grants time-limited, audited read/write access to
``platform_admin`` for their own tenant (or a single workspace within it),
for troubleshooting. There is no standing cross-tenant access for
platform_admin — every workspace/tenant-content RBAC guard calls
``has_active_grant`` before falling back to the old unconditional bypass.

Grants are "any platform admin" grants (the client does not pick a
specific person) — ``granted_to_user_id`` is not recorded, only who
granted it and when it expires.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

MAX_DURATION_MINUTES = 24 * 60  # 24h cap on a single grant


def has_active_grant(
    db: Session,
    tenant_id: UUID | str | None,
    workspace_id: UUID | str | None = None,
) -> bool:
    """True if there is a non-revoked, non-expired grant covering this
    tenant (tenant-wide grant) or this specific workspace.

    If only ``workspace_id`` is known, its ``tenant_id`` is resolved first.
    """
    if not tenant_id and not workspace_id:
        return False

    if not tenant_id and workspace_id:
        row = db.execute(
            text("SELECT tenant_id FROM control.workspaces WHERE workspace_id = :ws LIMIT 1"),
            {"ws": str(workspace_id)},
        ).fetchone()
        if not row:
            return False
        tenant_id = row.tenant_id

    row = db.execute(
        text(
            """
            SELECT 1
            FROM control.support_access_grants
            WHERE tenant_id = :tenant_id
              AND (workspace_id IS NULL OR workspace_id = :workspace_id)
              AND revoked_at IS NULL
              AND expires_at > now()
            LIMIT 1
            """
        ),
        {"tenant_id": str(tenant_id), "workspace_id": str(workspace_id) if workspace_id else None},
    ).fetchone()
    return row is not None


def create_grant(
    db: Session,
    tenant_id: UUID,
    granted_by_user_id: UUID,
    workspace_id: UUID | None,
    duration_minutes: int,
    reason: str | None,
) -> dict[str, Any]:
    duration_minutes = max(1, min(duration_minutes, MAX_DURATION_MINUTES))
    grant_id = uuid.uuid4()
    expires_at = datetime.now(UTC) + timedelta(minutes=duration_minutes)

    row = db.execute(
        text(
            """
            INSERT INTO control.support_access_grants (
                id, tenant_id, workspace_id, granted_by_user_id, reason,
                created_at, expires_at
            ) VALUES (
                :id, :tenant_id, :workspace_id, :granted_by, :reason,
                now(), :expires_at
            )
            RETURNING id, tenant_id, workspace_id, granted_by_user_id, reason,
                      created_at, expires_at, revoked_at
            """
        ),
        {
            "id": str(grant_id),
            "tenant_id": str(tenant_id),
            "workspace_id": str(workspace_id) if workspace_id else None,
            "granted_by": str(granted_by_user_id),
            "reason": reason,
            "expires_at": expires_at,
        },
    ).fetchone()
    db.commit()
    return _serialize(row)


def revoke_grant(db: Session, tenant_id: UUID, grant_id: UUID, revoked_by_user_id: UUID) -> bool:
    result = db.execute(
        text(
            """
            UPDATE control.support_access_grants
            SET revoked_at = now(), revoked_by_user_id = :revoked_by
            WHERE id = :id AND tenant_id = :tenant_id AND revoked_at IS NULL
            """
        ),
        {"id": str(grant_id), "tenant_id": str(tenant_id), "revoked_by": str(revoked_by_user_id)},
    )
    db.commit()
    return result.rowcount > 0


def list_grants_for_tenant(db: Session, tenant_id: UUID) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT id, tenant_id, workspace_id, granted_by_user_id, reason,
                   created_at, expires_at, revoked_at
            FROM control.support_access_grants
            WHERE tenant_id = :tenant_id
            ORDER BY created_at DESC
            LIMIT 200
            """
        ),
        {"tenant_id": str(tenant_id)},
    ).fetchall()
    return [_serialize(r) for r in rows]


def list_active_grants_for_platform_admin(db: Session) -> list[dict[str, Any]]:
    """All currently-active grants, any tenant — this is what a platform
    admin sees in the management console to know where they're allowed in.
    """
    rows = db.execute(
        text(
            """
            SELECT g.id, g.tenant_id, g.workspace_id, g.granted_by_user_id, g.reason,
                   g.created_at, g.expires_at, g.revoked_at,
                   t.tenant_name AS tenant_name, w.workspace_name AS workspace_name
            FROM control.support_access_grants g
            JOIN control.tenants t ON t.tenant_id = g.tenant_id
            LEFT JOIN control.workspaces w ON w.workspace_id = g.workspace_id
            WHERE g.revoked_at IS NULL AND g.expires_at > now()
            ORDER BY g.expires_at ASC
            """
        )
    ).fetchall()
    out = []
    for r in rows:
        d = _serialize(r)
        d["tenant_name"] = r.tenant_name
        d["workspace_name"] = r.workspace_name
        out.append(d)
    return out


def _serialize(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "workspace_id": str(row.workspace_id) if row.workspace_id else None,
        "granted_by_user_id": str(row.granted_by_user_id),
        "reason": row.reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }
