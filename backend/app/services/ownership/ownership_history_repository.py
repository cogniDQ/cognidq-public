"""
F055 — Ownership History Repository
======================================

Read-only repository that queries ``control.workspace_audit_logs`` for
ownership and accountability events across all entity types.

Ownership action types tracked:
* ``issue_assigned``          — issue assignee changed
* ``incident_owner_changed``  — incident owner/assignee changed
* ``incident_assigned``       — incident owner assigned (Sprint A7)
* ``rule_owner_changed``      — rule owner reassigned (Sprint B1)
* ``flow_owner_changed``      — flow owner reassigned (Sprint B2)
* ``role_assigned``           — workspace role granted (accountability trace)
* ``role_revoked``            — workspace role revoked
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.ownership.ownership_history_models import OwnershipHistoryQueryParams

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Action types that constitute an ownership / accountability event
# ---------------------------------------------------------------------------

OWNERSHIP_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "issue_assigned",
        "incident_owner_changed",
        "incident_assigned",
        "rule_owner_changed",
        "flow_owner_changed",
        "role_assigned",
        "role_revoked",
    }
)

# ---------------------------------------------------------------------------
# SQL fragments
# ---------------------------------------------------------------------------

_SELECT_COLS = """
    wal.log_id,
    wal.occurred_at,
    wal.action_type,
    wal.target_entity_type,
    wal.target_entity_id,
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
    LEFT JOIN users actor_u ON actor_u.id = wal.actor_id
"""


class OwnershipHistoryRepository:
    """Read-only repository for F055 ownership history."""

    def list_events(
        self,
        session: Session,
        tenant_id: UUID,
        workspace_id: UUID,
        filters: OwnershipHistoryQueryParams,
    ) -> list[dict[str, Any]]:
        """Return one page of ownership events."""
        where_clause, params = self._build_where(tenant_id, workspace_id, filters)
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

    def count_events(
        self,
        session: Session,
        tenant_id: UUID,
        workspace_id: UUID,
        filters: OwnershipHistoryQueryParams,
    ) -> int:
        """Return total count of ownership events matching the filters."""
        where_clause, params = self._build_where(tenant_id, workspace_id, filters)
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
        filters: OwnershipHistoryQueryParams,
    ) -> tuple[str, dict[str, Any]]:
        """Build WHERE clause for ownership events."""
        # Base: tenant + workspace scope, restricted to ownership action types
        action_placeholders = ", ".join(f":at_{i}" for i in range(len(OWNERSHIP_ACTION_TYPES)))
        clauses = [
            "wal.tenant_id = CAST(:tenant_id AS UUID)",
            "wal.workspace_id = CAST(:workspace_id AS UUID)",
            f"wal.action_type IN ({action_placeholders})",
        ]
        params: dict[str, Any] = {
            "tenant_id": str(tenant_id),
            "workspace_id": str(workspace_id),
        }
        for i, at in enumerate(sorted(OWNERSHIP_ACTION_TYPES)):
            params[f"at_{i}"] = at

        # Optional entity_type filter
        if filters.entity_type is not None:
            clauses.append("wal.target_entity_type = :entity_type")
            params["entity_type"] = filters.entity_type

        # Optional entity_id filter
        if filters.entity_id is not None:
            clauses.append("wal.target_entity_id = CAST(:entity_id AS UUID)")
            params["entity_id"] = str(filters.entity_id)

        # Optional action_type filter (must still be within the ownership set)
        if filters.action_type is not None:
            if filters.action_type in OWNERSHIP_ACTION_TYPES:
                clauses.append("wal.action_type = :action_type_filter")
                params["action_type_filter"] = filters.action_type

        where = "WHERE " + " AND ".join(clauses)
        return where, params
