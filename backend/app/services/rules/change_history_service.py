"""
F054 — Rule Change History Service
=====================================

Orchestrates repository calls, builds response models, and computes
human-readable change summaries from before/after state in the audit log.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.rules.change_history_models import (
    RuleChangeEntry,
    RuleChangePage,
    RuleChangeQueryParams,
)
from app.services.rules.change_history_repository import RuleChangeHistoryRepository

logger = logging.getLogger(__name__)

# Human-readable action labels
_ACTION_LABELS = {
    "rule_created": "Rule created",
    "rule_updated": "Rule updated",
    "rule_deleted": "Rule deleted",
    "rule_activated": "Rule activated",
    "rule_deactivated": "Rule deactivated",
}


class RuleChangeHistoryService:
    """Service layer for F054 rule change history."""

    def __init__(self, repository: RuleChangeHistoryRepository | None = None) -> None:
        self._repo = repository or RuleChangeHistoryRepository()

    def get_page(
        self,
        session: Session,
        tenant_id: UUID,
        workspace_id: UUID,
        rule_id: UUID,
        filters: RuleChangeQueryParams,
    ) -> RuleChangePage:
        """Fetch one page of rule change entries."""
        rows = self._repo.list_changes(session, tenant_id, workspace_id, rule_id, filters)
        total = self._repo.count_changes(session, tenant_id, workspace_id, rule_id, filters)
        items = [self._row_to_entry(row) for row in rows]
        has_next = total > filters.page * filters.page_size

        return RuleChangePage(
            items=items,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            has_next=has_next,
            rule_id=rule_id,
        )

    @staticmethod
    def describe_action(action_type: str) -> str:
        """Return human-readable label for an action type."""
        return _ACTION_LABELS.get(action_type, action_type)

    @staticmethod
    def compute_changed_fields(
        previous_data: dict[str, Any] | None,
        new_data: dict[str, Any] | None,
    ) -> list[str]:
        """Return list of field names that differ between before and after."""
        if previous_data is None or new_data is None:
            return []
        changed = []
        all_keys = set(previous_data.keys()) | set(new_data.keys())
        for key in sorted(all_keys):
            if previous_data.get(key) != new_data.get(key):
                changed.append(key)
        return changed

    @staticmethod
    def _row_to_entry(row: dict[str, Any]) -> RuleChangeEntry:
        return RuleChangeEntry(
            log_id=row["log_id"],
            occurred_at=row["occurred_at"],
            action_type=row["action_type"],
            actor_id=row.get("actor_id"),
            actor_role=row.get("actor_role"),
            actor_type=row.get("actor_type"),
            actor_display_name=row.get("actor_display_name"),
            previous_data=row.get("previous_data"),
            new_data=row.get("new_data"),
            request_id=row.get("request_id"),
        )
