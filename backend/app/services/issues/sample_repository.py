"""
F034 — SampleRepository

CRUD against ``public.issue_record_samples``.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.issue import IssueSample
from app.services.issues.issue_sample_models import SampleDomain

logger = logging.getLogger(__name__)


class SampleRepository:
    """Persist and retrieve ``IssueSample`` records."""

    def insert(self, db: Session, domain: SampleDomain) -> SampleDomain:
        """Insert a new sample row and return the refreshed domain."""
        orm = IssueSample(
            issue_id=domain.issue_id,
            workspace_id=domain.workspace_id,
            sample_count=domain.sample_count,
            rows=domain.rows,
            masking_applied=domain.masking_applied,
            masking_threshold=domain.masking_threshold,
        )
        db.add(orm)
        db.flush()
        db.refresh(orm)
        return SampleDomain.model_validate(orm)

    def find_by_issue(
        self,
        db: Session,
        issue_id: UUID,
        workspace_id: UUID,
    ) -> SampleDomain | None:
        """Return the sample for ``issue_id`` scoped to ``workspace_id``, or None."""
        row = (
            db.query(IssueSample)
            .filter(
                IssueSample.issue_id == issue_id,
                IssueSample.workspace_id == workspace_id,
            )
            .first()
        )
        return SampleDomain.model_validate(row) if row else None
