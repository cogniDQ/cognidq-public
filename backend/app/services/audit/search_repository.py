"""
F053 — Audit Log Search Repository
=====================================

Read-only repository for general audit log search and export.
Queries ``control.workspace_audit_logs`` with tenant scope.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.audit.search_models import AuditLogQueryParams

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
    wal.workspace_id,
    wal.request_id
"""

_FROM_JOINS = """
    FROM control.workspace_audit_logs wal
    LEFT JOIN users actor_u
        ON actor_u.id = wal.actor_id
"""


class AuditLogSearchRepository:
    """Read-only repository for the general audit log search (F053)."""

    def list_entries(
        self,
        session: Session,
        tenant_id: UUID,
        workspace_id: UUID,
        filters: AuditLogQueryParams,
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
        filters: AuditLogQueryParams,
    ) -> int:
        """Return total count of matching entries."""
        where_clause, params = self._build_where(tenant_id, workspace_id, filters)
        sql = text(f"SELECT COUNT(*) AS cnt FROM control.workspace_audit_logs wal {where_clause}")
        result = session.execute(sql, params)
        return int(result.scalar() or 0)

    def export_entries(
        self,
        session: Session,
        tenant_id: UUID,
        workspace_id: UUID,
        filters: AuditLogQueryParams,
    ) -> list[dict[str, Any]]:
        """Return up to 10 001 entries for CSV export (detect truncation at 10k)."""
        where_clause, params = self._build_where(tenant_id, workspace_id, filters)
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
        filters: AuditLogQueryParams,
    ):
        """Build WHERE clause and params dict."""
        clauses = [
            "wal.tenant_id = CAST(:tenant_id AS UUID)",
            "wal.workspace_id = CAST(:workspace_id AS UUID)",
        ]
        params: dict[str, Any] = {
            "tenant_id": str(tenant_id),
            "workspace_id": str(workspace_id),
        }

        if filters.action_type is not None:
            clauses.append("wal.action_type = :action_type")
            params["action_type"] = filters.action_type

        if filters.entity_type is not None:
            clauses.append("wal.target_entity_type = :entity_type")
            params["entity_type"] = filters.entity_type

        if filters.actor_id is not None:
            clauses.append("wal.actor_id = CAST(:actor_id AS UUID)")
            params["actor_id"] = str(filters.actor_id)

        if filters.from_date is not None:
            clauses.append("wal.occurred_at >= :from_date")
            params["from_date"] = filters.from_date

        if filters.to_date is not None:
            clauses.append("wal.occurred_at <= :to_date")
            params["to_date"] = filters.to_date

        where = "WHERE " + " AND ".join(clauses)
        return where, params
