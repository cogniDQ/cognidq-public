"""
F034 — SampleCaptureService

Captures a bounded sample of failing records from ``FlowNodeResult.result_data``
at issue-creation time, applies sensitivity-based masking, and persists the
result via ``SampleRepository``.

Design principles:
- Non-blocking: callers wrap in try/except; exceptions are never re-raised here.
- Privacy-safe default: columns with sensitivity_classification IN
  ('confidential', 'restricted') are replaced with "[MASKED]" at write time.
- Testable: all external dependencies are injected.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.issues.issue_sample_models import SampleDomain
from app.services.issues.sample_repository import SampleRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SAMPLE_MAX_ROWS: int = 50
_MASKING_THRESHOLD: str = "confidential"
# Sensitivity values that trigger masking at the default threshold
_MASK_SENSITIVE_AT: frozenset = frozenset({"confidential", "restricted"})

_SENSITIVITY_SQL = """
    SELECT field_name, sensitivity_classification
    FROM control.dataset_fields
    WHERE dataset_id = CAST(:dataset_id AS UUID)
"""


# ---------------------------------------------------------------------------
# SampleCaptureService
# ---------------------------------------------------------------------------


class SampleCaptureService:
    """Capture, mask, and store a failing-record sample for an issue."""

    def __init__(self, repository: SampleRepository | None = None) -> None:
        self._repo = repository or SampleRepository()

    def capture_for_issue(
        self,
        db: Session,
        issue_id: UUID,
        workspace_id: UUID,
        dataset_id: UUID | None,
        node_result_result_data: dict,
    ) -> SampleDomain | None:
        """
        Main entry point.

        Steps:
        1. Extract violations list from result_data (cap to _SAMPLE_MAX_ROWS).
        2. If empty → return None (nothing to capture).
        3. Load field sensitivity map from control.dataset_fields.
        4. Apply masking.
        5. Build SampleDomain.
        6. Persist via repository.
        7. Return inserted domain.
        """
        # Step 1 — Extract violations
        # The check node stores failing rows under 'canonical_violations'.
        # Fall back to 'violations' for any legacy result_data shapes.
        raw_violations: list[dict[str, Any]] = list(
            node_result_result_data.get("canonical_violations")
            or node_result_result_data.get("violations")
            or []
        )
        capped = raw_violations[:_SAMPLE_MAX_ROWS]

        # Step 2 — Nothing to capture
        if not capped:
            return None

        # Step 3 — Load sensitivity map
        sensitivity_map: dict[str, str] = {}
        if dataset_id is not None:
            sensitivity_map = _load_sensitivity_map(db, dataset_id)

        # Step 4 — Apply masking
        masked_rows, any_masked = _apply_masking(capped, sensitivity_map)

        # Step 5 — Build domain
        domain = SampleDomain(
            issue_id=issue_id,
            workspace_id=workspace_id,
            sample_count=len(masked_rows),
            rows=masked_rows,
            masking_applied=any_masked,
            masking_threshold=_MASKING_THRESHOLD if any_masked else None,
        )

        # Step 6 — Persist
        inserted = self._repo.insert(db, domain)

        # Step 7 — Return
        logger.info(
            "F034 sample captured: issue=%s workspace=%s rows=%s masking=%s",
            issue_id,
            workspace_id,
            inserted.sample_count,
            inserted.masking_applied,
        )
        return inserted


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _load_sensitivity_map(db: Session, dataset_id: UUID) -> dict[str, str]:
    """
    Load {field_name: sensitivity_classification} for all fields of a dataset.

    Uses raw SQL against control.dataset_fields to avoid ORM schema coupling.
    """
    try:
        rows = db.execute(
            text(_SENSITIVITY_SQL),
            {"dataset_id": str(dataset_id)},
        ).fetchall()
        return {r.field_name: r.sensitivity_classification for r in rows}
    except Exception as exc:
        logger.warning("F034 could not load sensitivity map for dataset %s: %s", dataset_id, exc)
        return {}


def _apply_masking(
    rows: list[dict[str, Any]],
    sensitivity_map: dict[str, str],
) -> tuple[list[dict[str, Any]], bool]:
    """
    Replace values for columns with sensitivity_classification in
    _MASK_SENSITIVE_AT with the literal string "[MASKED]".

    Returns (masked_rows, any_masked_flag).
    """
    any_masked = False
    out: list[dict[str, Any]] = []
    for row in rows:
        masked_row: dict[str, Any] = {}
        for col, val in row.items():
            if sensitivity_map.get(col) in _MASK_SENSITIVE_AT:
                masked_row[col] = "[MASKED]"
                any_masked = True
            else:
                masked_row[col] = val
        out.append(masked_row)
    return out, any_masked
