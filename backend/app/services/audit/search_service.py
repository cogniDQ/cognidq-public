"""
F053 — Audit Log Search Service
=================================

Orchestrates repository calls, builds response models, and produces export
rows with formula-injection escaping applied.

Export truncation: the repository fetches LIMIT 10001.  If exactly 10001
rows are returned the service returns the first 10000 and appends a
truncation-notice row at the end of the list.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.audit.search_models import (
    AuditLogEntry,
    AuditLogPage,
    AuditLogQueryParams,
)
from app.services.audit.search_repository import AuditLogSearchRepository

logger = logging.getLogger(__name__)

_EXPORT_TRUNCATION_LIMIT = 10_000
_EXPORT_FETCH_LIMIT = _EXPORT_TRUNCATION_LIMIT + 1

_TRUNCATION_NOTICE = (
    "# NOTE: Export truncated at 10000 rows. Apply narrower filters for a complete export."
)

_FORMULA_INJECTION_PREFIXES = frozenset({"=", "+", "-", "@"})

_EXPORT_COLUMNS = [
    "log_id",
    "occurred_at",
    "action_type",
    "actor_id",
    "actor_display_name",
    "actor_role",
    "actor_type",
    "target_entity_type",
    "target_entity_id",
    "workspace_id",
    "request_id",
]


class AuditLogSearchService:
    """Service layer for F053 audit log search endpoints."""

    def __init__(self, repository: AuditLogSearchRepository | None = None) -> None:
        self._repo = repository or AuditLogSearchRepository()

    # ------------------------------------------------------------------
    # List endpoint
    # ------------------------------------------------------------------

    def get_page(
        self,
        session: Session,
        tenant_id: UUID,
        workspace_id: UUID,
        filters: AuditLogQueryParams,
    ) -> AuditLogPage:
        """Fetch one page of audit log entries."""
        rows = self._repo.list_entries(session, tenant_id, workspace_id, filters)
        total = self._repo.count_entries(session, tenant_id, workspace_id, filters)
        items = [self._row_to_entry(row) for row in rows]
        has_next = total > filters.page * filters.page_size

        logger.info(
            "audit_log_search",
            extra={
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "total_records": total,
                "page": filters.page,
                "page_size": filters.page_size,
                "action": "audit_log_search",
                "result": "ok",
            },
        )

        return AuditLogPage(
            items=items,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            has_next=has_next,
        )

    # ------------------------------------------------------------------
    # Export endpoint
    # ------------------------------------------------------------------

    def build_export_rows(
        self,
        session: Session,
        tenant_id: UUID,
        workspace_id: UUID,
        filters: AuditLogQueryParams,
    ) -> list[dict[str, str]]:
        """Return list of dicts ready for CSV.  Formula-injection escaped."""
        rows = self._repo.export_entries(session, tenant_id, workspace_id, filters)
        truncated = len(rows) > _EXPORT_TRUNCATION_LIMIT
        data_rows = rows[:_EXPORT_TRUNCATION_LIMIT]

        export: list[dict[str, str]] = [self._row_to_export_dict(row) for row in data_rows]

        if truncated:
            notice: dict[str, str] = {col: "" for col in _EXPORT_COLUMNS}
            notice["log_id"] = _TRUNCATION_NOTICE
            export.append(notice)

        logger.info(
            "audit_log_export",
            extra={
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "export_row_count": len(data_rows),
                "truncated": truncated,
                "action": "audit_log_export",
                "result": "ok",
            },
        )

        return export

    @staticmethod
    def export_columns() -> list[str]:
        return list(_EXPORT_COLUMNS)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_entry(row: dict[str, Any]) -> AuditLogEntry:
        return AuditLogEntry(
            log_id=row["log_id"],
            occurred_at=row["occurred_at"],
            action_type=row["action_type"],
            actor_id=row.get("actor_id"),
            actor_role=row.get("actor_role"),
            actor_type=row.get("actor_type"),
            actor_display_name=row.get("actor_display_name"),
            target_entity_type=row.get("target_entity_type"),
            target_entity_id=row.get("target_entity_id"),
            workspace_id=row.get("workspace_id"),
            request_id=row.get("request_id"),
        )

    @staticmethod
    def _row_to_export_dict(row: dict[str, Any]) -> dict[str, str]:
        result: dict[str, str] = {}
        for col in _EXPORT_COLUMNS:
            raw = row.get(col)
            value = str(raw) if raw is not None else ""
            result[col] = _escape_csv_cell(value)
        return result


# ---------------------------------------------------------------------------
# Formula-injection escaping (module-level for unit testability)
# ---------------------------------------------------------------------------


def _escape_csv_cell(value: str) -> str:
    """Prefix values starting with formula-injection characters with ``'``."""
    if value and value[0] in _FORMULA_INJECTION_PREFIXES:
        return "'" + value
    return value
