"""
F008 — Permission Audit Visibility — Service Layer
==================================================

Orchestrates repository calls, builds response models, and produces export
rows with formula-injection escaping applied.

Formula-injection escaping: any cell value whose first character is one of
``= + - @`` is prefixed with ``'`` (a single apostrophe) to prevent
spreadsheet applications from interpreting the cell as a formula.

Export truncation: the repository fetches LIMIT 10001.  If exactly 10001
rows are returned the service returns the first 10000 and appends a
truncation-notice row at the end of the list.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.permission_audit import (
    PermissionAuditEntry,
    PermissionAuditExportQueryParams,
    PermissionAuditPage,
    PermissionAuditQueryParams,
)
from app.services.permission_audit.repository import PermissionAuditRepository

logger = logging.getLogger(__name__)

_EXPORT_TRUNCATION_LIMIT = 10_000
_EXPORT_FETCH_LIMIT = _EXPORT_TRUNCATION_LIMIT + 1  # repository fetches this many

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
    "target_display_name",
    "workspace_id",
    "request_id",
]


class PermissionAuditService:
    """Service layer for F008 permission audit read endpoints."""

    def __init__(self, repository: PermissionAuditRepository | None = None) -> None:
        self._repo = repository or PermissionAuditRepository()

    # ------------------------------------------------------------------
    # List endpoint
    # ------------------------------------------------------------------

    def get_page(
        self,
        session: Session,
        tenant_id: UUID,
        workspace_id: UUID,
        filters: PermissionAuditQueryParams,
    ) -> PermissionAuditPage:
        """Fetch one page of permission audit entries."""
        rows = self._repo.list_entries(session, tenant_id, workspace_id, filters)
        total = self._repo.count_entries(session, tenant_id, workspace_id, filters)
        items = [self._row_to_entry(row) for row in rows]
        has_next = total > filters.page * filters.page_size

        logger.info(
            "permission_audit_list",
            extra={
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "total_records": total,
                "page": filters.page,
                "page_size": filters.page_size,
                "action": "permission_audit_list",
                "result": "ok",
            },
        )

        return PermissionAuditPage(
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
        filters: PermissionAuditExportQueryParams,
    ) -> list[dict[str, str]]:
        """Return a list of dicts ready to be written to CSV.

        Each dict has exactly the columns in ``_EXPORT_COLUMNS``.  All values
        are strings.  Formula-injection escaping is applied.  If the result
        set exceeds 10 000 rows a truncation-notice dict is appended as the
        last item.
        """
        rows = self._repo.export_entries(session, tenant_id, workspace_id, filters)
        truncated = len(rows) > _EXPORT_TRUNCATION_LIMIT
        data_rows = rows[:_EXPORT_TRUNCATION_LIMIT]

        export: list[dict[str, str]] = [self._row_to_export_dict(row) for row in data_rows]

        if truncated:
            notice: dict[str, str] = {col: "" for col in _EXPORT_COLUMNS}
            notice["log_id"] = _TRUNCATION_NOTICE
            export.append(notice)

        logger.info(
            "permission_audit_export",
            extra={
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "export_row_count": len(data_rows),
                "truncated": truncated,
                "action": "permission_audit_export",
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
    def _row_to_entry(row: dict[str, Any]) -> PermissionAuditEntry:
        return PermissionAuditEntry(
            log_id=row["log_id"],
            occurred_at=row["occurred_at"],
            action_type=row["action_type"],
            actor_id=row.get("actor_id"),
            actor_display_name=row.get("actor_display_name"),
            actor_role=row["actor_role"],
            actor_type=row["actor_type"],
            target_entity_type=row.get("target_entity_type"),
            target_entity_id=row.get("target_entity_id"),
            target_display_name=row.get("target_display_name"),
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
