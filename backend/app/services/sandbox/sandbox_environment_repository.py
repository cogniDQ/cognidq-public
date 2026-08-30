"""
F134 — Demo Sandbox Provisioning
SandboxEnvironmentRepository: DB operations for control.sandbox_environments.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_INSERT_SQL = text("""
    INSERT INTO control.sandbox_environments (
        id, demo_request_id, tenant_id, workspace_id,
        template_id, access_profile_id,
        status, expires_at
    ) VALUES (
        :id,
        CAST(:demo_request_id AS UUID),
        CAST(:tenant_id AS UUID),
        CAST(:workspace_id AS UUID),
        :template_id,
        CAST(:access_profile_id AS UUID),
        'provisioning',
        :expires_at
    )
    RETURNING
        id::text, demo_request_id::text, tenant_id::text,
        workspace_id::text, template_id, access_profile_id::text,
        status, expires_at, created_at, updated_at
""")

_FIND_BY_ID_SQL = text("""
    SELECT
        id::text, demo_request_id::text, tenant_id::text,
        workspace_id::text, template_id, access_profile_id::text,
        status, provisioned_at, expires_at, suspended_at,
        archived_at, deleted_at, extension_count, grace_period_days,
        retention_policy, engagement_score, last_activity_at,
        session_count, created_at, updated_at
    FROM control.sandbox_environments
    WHERE id = :id
""")

_UPDATE_STATUS_SQL = text("""
    UPDATE control.sandbox_environments
    SET
        status       = :status,
        updated_at   = NOW(),
        provisioned_at = CASE WHEN :set_provisioned_at THEN NOW() ELSE provisioned_at END,
        suspended_at   = CASE WHEN :set_suspended_at THEN NOW() ELSE suspended_at END,
        archived_at    = CASE WHEN :set_archived_at THEN NOW() ELSE archived_at END,
        deleted_at     = CASE WHEN :set_deleted_at THEN NOW() ELSE deleted_at END,
        last_error     = COALESCE(:last_error, last_error)
    WHERE id = :id
    RETURNING id::text, status, updated_at
""")

_LIST_EXPIRING_SQL = text("""
    SELECT
        id::text, demo_request_id::text, tenant_id::text,
        workspace_id::text, status, expires_at
    FROM control.sandbox_environments
    WHERE status IN ('active', 'suspended')
      AND expires_at <= :threshold_at
    ORDER BY expires_at ASC
""")

_LIST_READY_CLEANUP_SQL = text("""
    SELECT
        id::text, demo_request_id::text, tenant_id::text,
        workspace_id::text, status, archived_at
    FROM control.sandbox_environments
    WHERE status = 'archived'
      AND archived_at <= :threshold_at
    ORDER BY archived_at ASC
    LIMIT :limit
""")

_FIND_BY_TENANT_SQL = text("""
    SELECT
        id::text, demo_request_id::text, tenant_id::text,
        workspace_id::text, status, expires_at
    FROM control.sandbox_environments
    WHERE tenant_id = CAST(:tenant_id AS UUID)
""")

_INCREMENT_EXTENSION_SQL = text("""
    UPDATE control.sandbox_environments
    SET
        extension_count = extension_count + 1,
        expires_at      = :new_expires_at,
        updated_at      = NOW()
    WHERE id = :id
    RETURNING id::text, extension_count, expires_at
""")

_UPDATE_LAST_ACTIVITY_SQL = text("""
    UPDATE control.sandbox_environments
    SET
        last_activity_at = :occurred_at,
        session_count    = CASE WHEN :increment_sessions THEN session_count + 1 ELSE session_count END,
        updated_at       = NOW()
    WHERE id = :id
""")


class SandboxEnvironmentRepository:
    """Data access for control.sandbox_environments."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        demo_request_id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        template_id: str,
        access_profile_id: UUID,
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        row = self._db.execute(
            _INSERT_SQL,
            {
                "id": str(uuid4()),
                "demo_request_id": str(demo_request_id),
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "template_id": template_id,
                "access_profile_id": str(access_profile_id),
                "expires_at": expires_at,
            },
        ).fetchone()
        return dict(row._mapping)

    def find_by_id(self, sandbox_id: UUID) -> dict[str, Any] | None:
        row = self._db.execute(_FIND_BY_ID_SQL, {"id": str(sandbox_id)}).fetchone()
        return dict(row._mapping) if row else None

    def find_by_tenant(self, tenant_id: UUID) -> dict[str, Any] | None:
        row = self._db.execute(_FIND_BY_TENANT_SQL, {"tenant_id": str(tenant_id)}).fetchone()
        return dict(row._mapping) if row else None

    def update_status(
        self,
        *,
        sandbox_id: UUID,
        status: str,
        set_provisioned_at: bool = False,
        set_suspended_at: bool = False,
        set_archived_at: bool = False,
        set_deleted_at: bool = False,
        last_error: str | None = None,
    ) -> dict[str, Any] | None:
        row = self._db.execute(
            _UPDATE_STATUS_SQL,
            {
                "id": str(sandbox_id),
                "status": status,
                "set_provisioned_at": set_provisioned_at,
                "set_suspended_at": set_suspended_at,
                "set_archived_at": set_archived_at,
                "set_deleted_at": set_deleted_at,
                "last_error": last_error,
            },
        ).fetchone()
        return dict(row._mapping) if row else None

    def list_expiring(self, *, threshold_at: datetime) -> list[dict[str, Any]]:
        rows = self._db.execute(_LIST_EXPIRING_SQL, {"threshold_at": threshold_at}).fetchall()
        return [dict(r._mapping) for r in rows]

    def list_ready_for_cleanup(
        self, *, threshold_at: datetime, limit: int = 100
    ) -> list[dict[str, Any]]:
        rows = self._db.execute(
            _LIST_READY_CLEANUP_SQL, {"threshold_at": threshold_at, "limit": limit}
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def increment_extension(
        self, *, sandbox_id: UUID, new_expires_at: datetime
    ) -> dict[str, Any] | None:
        row = self._db.execute(
            _INCREMENT_EXTENSION_SQL,
            {"id": str(sandbox_id), "new_expires_at": new_expires_at},
        ).fetchone()
        return dict(row._mapping) if row else None

    def update_last_activity(
        self,
        *,
        sandbox_id: UUID,
        occurred_at: datetime,
        increment_sessions: bool = False,
    ) -> None:
        self._db.execute(
            _UPDATE_LAST_ACTIVITY_SQL,
            {
                "id": str(sandbox_id),
                "occurred_at": occurred_at,
                "increment_sessions": increment_sessions,
            },
        )

    def list_all(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return (rows, total_count) for admin sandbox list view."""
        where = "WHERE status = :status" if status else ""
        sql = text(f"""
            SELECT
                id::text, demo_request_id::text, tenant_id::text,
                workspace_id::text, template_id, status,
                expires_at, provisioned_at, engagement_score,
                last_activity_at, extension_count, created_at, updated_at,
                COUNT(*) OVER() AS total_count
            FROM control.sandbox_environments
            {where}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        params: dict = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        rows = self._db.execute(sql, params).fetchall()
        if not rows:
            return [], 0
        total = rows[0]._mapping["total_count"]
        return [dict(r._mapping) for r in rows], total
