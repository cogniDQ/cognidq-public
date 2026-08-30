"""
F055 — Ownership History Service
===================================

Orchestrates repository calls and builds response models for the ownership
history and accountability trace endpoints.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.ownership.ownership_history_models import (
    OwnershipEvent,
    OwnershipHistoryPage,
    OwnershipHistoryQueryParams,
)
from app.services.ownership.ownership_history_repository import (
    OwnershipHistoryRepository,
)

logger = logging.getLogger(__name__)


class OwnershipHistoryService:
    """Service layer for F055 ownership history."""

    def __init__(self, repository: OwnershipHistoryRepository | None = None) -> None:
        self._repo = repository or OwnershipHistoryRepository()

    def get_page(
        self,
        session: Session,
        tenant_id: UUID,
        workspace_id: UUID,
        filters: OwnershipHistoryQueryParams,
    ) -> OwnershipHistoryPage:
        """Fetch one page of ownership events."""
        rows = self._repo.list_events(session, tenant_id, workspace_id, filters)
        total = self._repo.count_events(session, tenant_id, workspace_id, filters)
        items = [self._row_to_event(row) for row in rows]
        has_next = total > filters.page * filters.page_size

        logger.info(
            "ownership_history_query workspace=%s entity_type=%s page=%s total=%s",
            workspace_id,
            filters.entity_type,
            filters.page,
            total,
        )
        return OwnershipHistoryPage(
            items=items,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            has_next=has_next,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_event(row: dict[str, Any]) -> OwnershipEvent:
        """Convert a DB row dict to an OwnershipEvent domain object."""
        return OwnershipEvent(
            log_id=row["log_id"],
            occurred_at=row["occurred_at"],
            action_type=row["action_type"],
            target_entity_type=row.get("target_entity_type"),
            target_entity_id=row.get("target_entity_id"),
            actor_id=row.get("actor_id"),
            actor_role=row.get("actor_role"),
            actor_type=row.get("actor_type"),
            actor_display_name=row.get("actor_display_name"),
            previous_data=row.get("previous_data"),
            new_data=row.get("new_data"),
            request_id=row.get("request_id"),
        )
