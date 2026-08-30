"""
F008 — Permission Audit Visibility — Repository Layer
=====================================================

Executes parameterised, read-only queries against ``control.workspace_audit_logs``
with LEFT JOINs to ``public.users`` (actor + target-user) and ``public.teams``
(target-team) for display-name resolution.

Tenant isolation is unconditional: ``tenant_id`` and ``workspace_id`` are
always applied regardless of which optional filters are provided.

The export query fetches LIMIT 10001 (one more than the cap) so the service
layer can detect truncation without a separate COUNT query.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.permission_audit import (
    ACCESS_CONTROL_ACTION_TYPES,
    PermissionAuditExportQueryParams,
    PermissionAuditQueryParams,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL fragments
# ---------------------------------------------------------------------------

_SELECT_COLS = """
    wal.log_id,
    wal.occurred_at,
    wal.action_type,
    wal.actor_id,
    wal.actor_role,
    wal.actor_type,
    COALESCE(actor_u.full_name, actor_u.email) AS actor_display_name,
    wal.target_entity_type,
    wal.target_entity_id,
    COALESCE(target_u.full_name, target_u.email, t.name) AS target_display_name,
    wal.workspace_id,
    wal.request_id
"""

_FROM_JOINS = """
    FROM control.workspace_audit_logs wal
    LEFT JOIN users actor_u
        ON actor_u.id = wal.actor_id
    LEFT JOIN users target_u
        ON (
            wal.target_entity_type IN (
                'user', 'user_profile', 'role_assignment'
            )
            AND target_u.id = wal.target_entity_id
        )
    LEFT JOIN teams t
        ON (
            wal.target_entity_type IN (
                'team', 'team_membership', 'team_member'
            )
            AND t.id = wal.target_entity_id
        )
"""

# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class PermissionAuditRepository:
    """Read-only repository for the permission audit endpoints (F008)."""

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def list_entries(
        self,
        session: Session,
        tenant_id: UUID,
        workspace_id: UUID,
        filters: PermissionAuditQueryParams,
    ) -> list[dict[str, Any]]:
        """Return one page of matching audit entries as plain dicts."""
        where_clause, params = self._build_where(tenant_id, workspace_id, filters)
        order = "ASC" if filters.sort_dir == "asc" else "DESC"
        offset = (filters.page - 1) * filters.page_size

        sql = text(
            f"SELECT {_SELECT_COLS} {_FROM_JOINS} {where_clause} "
            f"ORDER BY wal.occurred_at {order} "
            f"LIMIT :page_size OFFSET :offset"
        )
        params["page_size"] = filters.page_size
        params["offset"] = offset

        result = session.execute(sql, params)
        return [dict(row._mapping) for row in result]

    def count_entries(
        self,
        session: Session,
        tenant_id: UUID,
        workspace_id: UUID,
        filters: PermissionAuditQueryParams,
    ) -> int:
        """Return the total count of matching entries (for pagination)."""
        where_clause, params = self._build_where(tenant_id, workspace_id, filters)
        sql = text(f"SELECT COUNT(*) AS cnt FROM control.workspace_audit_logs wal {where_clause}")
        result = session.execute(sql, params)
        return int(result.scalar() or 0)

    def export_entries(
        self,
        session: Session,
        tenant_id: UUID,
        workspace_id: UUID,
        filters: PermissionAuditExportQueryParams,
    ) -> list[dict[str, Any]]:
        """Return up to 10 001 matching entries for the CSV export path.

        Fetching 10 001 rows allows the service layer to detect truncation
        at 10 000 without a separate COUNT query.
        """
        where_clause, params = self._build_export_where(tenant_id, workspace_id, filters)

        sql = text(
            f"SELECT {_SELECT_COLS} {_FROM_JOINS} {where_clause} "
            f"ORDER BY wal.occurred_at DESC "
            f"LIMIT 10001"
        )
        result = session.execute(sql, params)
        return [dict(row._mapping) for row in result]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_where(
        self,
        tenant_id: UUID,
        workspace_id: UUID,
        filters: PermissionAuditQueryParams,
    ):
        """Build WHERE clause and params dict for the list / count queries."""
        clauses = [
            "wal.tenant_id = CAST(:tenant_id AS UUID)",
            "wal.workspace_id = CAST(:workspace_id AS UUID)",
            "wal.action_type = ANY(:action_type_set)",
        ]
        params: dict[str, Any] = {
            "tenant_id": str(tenant_id),
            "workspace_id": str(workspace_id),
            "action_type_set": list(
                [filters.action_type] if filters.action_type else ACCESS_CONTROL_ACTION_TYPES
            ),
        }

        if filters.actor_id is not None:
            clauses.append("wal.actor_id = CAST(:actor_id AS UUID)")
            params["actor_id"] = str(filters.actor_id)

        if filters.target_entity_id is not None:
            clauses.append("wal.target_entity_id = CAST(:target_entity_id AS UUID)")
            params["target_entity_id"] = str(filters.target_entity_id)

        if filters.target_entity_type is not None:
            clauses.append("wal.target_entity_type = :target_entity_type")
            params["target_entity_type"] = filters.target_entity_type

        if filters.from_date is not None:
            clauses.append("wal.occurred_at >= :from_date")
            params["from_date"] = filters.from_date

        if filters.to_date is not None:
            clauses.append("wal.occurred_at <= :to_date")
            params["to_date"] = filters.to_date

        where = "WHERE " + " AND ".join(clauses)
        return where, params

    def _build_export_where(
        self,
        tenant_id: UUID,
        workspace_id: UUID,
        filters: PermissionAuditExportQueryParams,
    ):
        """Build WHERE clause and params dict for the export query."""
        clauses = [
            "wal.tenant_id = CAST(:tenant_id AS UUID)",
            "wal.workspace_id = CAST(:workspace_id AS UUID)",
            "wal.action_type = ANY(:action_type_set)",
        ]
        params: dict[str, Any] = {
            "tenant_id": str(tenant_id),
            "workspace_id": str(workspace_id),
            "action_type_set": list(
                [filters.action_type] if filters.action_type else ACCESS_CONTROL_ACTION_TYPES
            ),
        }

        if filters.actor_id is not None:
            clauses.append("wal.actor_id = CAST(:actor_id AS UUID)")
            params["actor_id"] = str(filters.actor_id)

        if filters.target_entity_id is not None:
            clauses.append("wal.target_entity_id = CAST(:target_entity_id AS UUID)")
            params["target_entity_id"] = str(filters.target_entity_id)

        if filters.target_entity_type is not None:
            clauses.append("wal.target_entity_type = :target_entity_type")
            params["target_entity_type"] = filters.target_entity_type

        if filters.from_date is not None:
            clauses.append("wal.occurred_at >= :from_date")
            params["from_date"] = filters.from_date

        if filters.to_date is not None:
            clauses.append("wal.occurred_at <= :to_date")
            params["to_date"] = filters.to_date

        where = "WHERE " + " AND ".join(clauses)
        return where, params
