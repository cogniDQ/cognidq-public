"""
F054 — Rule Change History Repository
========================================

Read-only repository that queries ``control.workspace_audit_logs`` for
rule entity changes, returning paginated results with actor display names.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.rules.change_history_models import RuleChangeQueryParams

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
    wal.previous_data,
    wal.new_data,
    wal.request_id
"""

_FROM_JOINS = """
    FROM control.workspace_audit_logs wal
    LEFT JOIN users actor_u
        ON actor_u.id = wal.actor_id
"""


class RuleChangeHistoryRepository:
    """Read-only repository for F054 rule change history."""

    def list_changes(
        self,
        session: Session,
        tenant_id: UUID,
        workspace_id: UUID,
        rule_id: UUID,
        filters: RuleChangeQueryParams,
    ) -> list[dict[str, Any]]:
        """Return one page of change entries for a specific rule."""
        where_clause, params = self._build_where(tenant_id, workspace_id, rule_id, filters)
        offset = (filters.page - 1) * filters.page_size

        sql = text(
            f"SELECT {_SELECT_COLS} {_FROM_JOINS} {where_clause} "
            f"ORDER BY wal.occurred_at DESC "
            f"LIMIT :page_size OFFSET :offset"
        )
        params["page_size"] = filters.page_size
        params["offset"] = offset

        result = session.execute(sql, params)
        return [dict(row._mapping) for row in result]

    def count_changes(
        self,
        session: Session,
        tenant_id: UUID,
        workspace_id: UUID,
        rule_id: UUID,
        filters: RuleChangeQueryParams,
    ) -> int:
        """Return total count of change entries for a specific rule."""
        where_clause, params = self._build_where(tenant_id, workspace_id, rule_id, filters)
        sql = text(f"SELECT COUNT(*) AS cnt FROM control.workspace_audit_logs wal {where_clause}")
        result = session.execute(sql, params)
        return int(result.scalar() or 0)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_where(
        self,
        tenant_id: UUID,
        workspace_id: UUID,
        rule_id: UUID,
        filters: RuleChangeQueryParams,
    ):
        """Build WHERE clause scoped to a specific rule."""
        clauses = [
            "wal.tenant_id = CAST(:tenant_id AS UUID)",
            "wal.workspace_id = CAST(:workspace_id AS UUID)",
            "wal.target_entity_type = 'rule'",
            "wal.target_entity_id = CAST(:rule_id AS UUID)",
        ]
        params: dict[str, Any] = {
            "tenant_id": str(tenant_id),
            "workspace_id": str(workspace_id),
            "rule_id": str(rule_id),
        }

        if filters.action_type is not None:
            clauses.append("wal.action_type = :action_type")
            params["action_type"] = filters.action_type

        where = "WHERE " + " AND ".join(clauses)
        return where, params
