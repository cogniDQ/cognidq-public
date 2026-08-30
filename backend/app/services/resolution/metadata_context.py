"""Metadata context enrichment for resolution ranking (F123)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class MetadataContextService:
    """Loads optional metadata signals for resolution ranking.

    This service is fail-open by design. Missing tables or unavailable metadata
    should not block resolution; consumers receive empty/default context.
    """

    def enrich_context(
        self, db: Session, workspace_id: UUID, context: dict[str, Any]
    ) -> dict[str, Any]:
        enriched = dict(context)

        # Parent dataset names for field candidates (existing signal dependency).
        enriched["parent_dataset_names"] = self._load_parent_dataset_names(db, workspace_id)

        # Optional precomputed maps for advanced signals.
        enriched["lineage_distance_by_asset"] = self._load_lineage_distance_map(db, workspace_id)
        enriched["cooccurrence_by_asset"] = self._load_cooccurrence_map(db, workspace_id)
        enriched["usage_count_by_asset"] = self._load_usage_count_map(db, workspace_id)
        enriched["recency_days_by_asset"] = self._load_recency_days_map(db, workspace_id)
        enriched["profile_stats_by_asset"] = self._load_profile_stats_map(db, workspace_id)

        # Sprint 4.8 — fallback derivations when dedicated index tables are
        # empty/missing. These complete the lineage / usage / ownership
        # signals using data that already exists (asset parent links,
        # dq_rules targets, glossary owners).
        if not enriched["lineage_distance_by_asset"]:
            enriched["lineage_distance_by_asset"] = self._derive_lineage_from_parents(
                db, workspace_id, enriched
            )
        if not enriched["usage_count_by_asset"]:
            enriched["usage_count_by_asset"] = self._derive_usage_from_rules(db, workspace_id)
        if not enriched["profile_stats_by_asset"]:
            enriched["profile_stats_by_asset"] = self._derive_ownership_from_glossary(
                db, workspace_id
            )

        return enriched

    @staticmethod
    def _load_parent_dataset_names(db: Session, workspace_id: UUID) -> dict[str, str]:
        try:
            with db.begin_nested():
                rows = db.execute(
                    text(
                        """
                        SELECT asset_id, name
                        FROM control.metadata_asset_index
                        WHERE workspace_id = :wid AND asset_type = 'dataset'
                        """
                    ),
                    {"wid": str(workspace_id)},
                ).fetchall()
                return {str(r.asset_id): r.name for r in rows}
        except Exception as exc:  # pragma: no cover
            logger.debug("metadata_context: parent dataset names unavailable: %s", exc)
            return {}

    @staticmethod
    def _load_lineage_distance_map(db: Session, workspace_id: UUID) -> dict[str, int]:
        # Optional table; gracefully handle absence.
        try:
            with db.begin_nested():
                rows = db.execute(
                    text(
                        """
                        SELECT target_asset_id, min(hop_distance) AS hop_distance
                        FROM control.metadata_lineage_index
                        WHERE workspace_id = :wid
                        GROUP BY target_asset_id
                        """
                    ),
                    {"wid": str(workspace_id)},
                ).fetchall()
                return {
                    str(r.target_asset_id): int(r.hop_distance)
                    for r in rows
                    if r.hop_distance is not None
                }
        except Exception:  # pragma: no cover
            return {}

    @staticmethod
    def _load_cooccurrence_map(db: Session, workspace_id: UUID) -> dict[str, float]:
        try:
            with db.begin_nested():
                rows = db.execute(
                    text(
                        """
                        SELECT asset_id, normalized_score
                        FROM control.metadata_cooccurrence_index
                        WHERE workspace_id = :wid
                        """
                    ),
                    {"wid": str(workspace_id)},
                ).fetchall()
                return {
                    str(r.asset_id): float(r.normalized_score)
                    for r in rows
                    if r.normalized_score is not None
                }
        except Exception:  # pragma: no cover
            return {}

    @staticmethod
    def _load_usage_count_map(db: Session, workspace_id: UUID) -> dict[str, int]:
        try:
            with db.begin_nested():
                rows = db.execute(
                    text(
                        """
                        SELECT asset_id, usage_count
                        FROM control.metadata_usage_index
                        WHERE workspace_id = :wid
                        """
                    ),
                    {"wid": str(workspace_id)},
                ).fetchall()
                return {
                    str(r.asset_id): int(r.usage_count) for r in rows if r.usage_count is not None
                }
        except Exception:  # pragma: no cover
            return {}

    @staticmethod
    def _load_recency_days_map(db: Session, workspace_id: UUID) -> dict[str, float]:
        try:
            with db.begin_nested():
                rows = db.execute(
                    text(
                        """
                        SELECT asset_id,
                               EXTRACT(EPOCH FROM (now() - COALESCE(updated_at, created_at))) / 86400.0 AS age_days
                        FROM control.metadata_asset_index
                        WHERE workspace_id = :wid
                        """
                    ),
                    {"wid": str(workspace_id)},
                ).fetchall()
                return {str(r.asset_id): float(r.age_days) for r in rows if r.age_days is not None}
        except Exception:  # pragma: no cover
            return {}

    @staticmethod
    def _load_profile_stats_map(db: Session, workspace_id: UUID) -> dict[str, dict[str, Any]]:
        try:
            with db.begin_nested():
                rows = db.execute(
                    text(
                        """
                        SELECT asset_id, null_rate, cardinality_class
                        FROM control.metadata_profile_index
                        WHERE workspace_id = :wid
                        """
                    ),
                    {"wid": str(workspace_id)},
                ).fetchall()
                return {
                    str(r.asset_id): {
                        "null_rate": float(r.null_rate) if r.null_rate is not None else None,
                        "cardinality_class": r.cardinality_class,
                    }
                    for r in rows
                }
        except Exception:  # pragma: no cover
            return {}

    # ──────────────────────────────────────────────────────────────────────
    # Sprint 4.8 — fallback signal derivations
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _derive_lineage_from_parents(
        db: Session,
        workspace_id: UUID,
        context: dict[str, Any],
    ) -> dict[str, int]:
        """Fallback lineage signal: when a `dataset_hint` is in context,
        mark every FIELD whose parent dataset matches the hint as hop 1.

        Cheap, no extra table required, and works against the data we
        already index in ``control.metadata_asset_index``.
        """
        hint = context.get("dataset_hint")
        if not hint:
            return {}
        try:
            with db.begin_nested():
                rows = db.execute(
                    text(
                        """
                        SELECT f.asset_id
                        FROM control.metadata_asset_index f
                        JOIN control.metadata_asset_index d
                          ON d.asset_id = f.parent_asset_id
                        WHERE f.workspace_id = :wid
                          AND f.asset_type = 'field'
                          AND d.asset_type = 'dataset'
                          AND LOWER(d.name) = LOWER(:hint)
                        """
                    ),
                    {"wid": str(workspace_id), "hint": str(hint)},
                ).fetchall()
            return {str(r.asset_id): 1 for r in rows}
        except Exception as exc:  # pragma: no cover
            logger.debug("metadata_context: lineage fallback unavailable: %s", exc)
            return {}

    @staticmethod
    def _derive_usage_from_rules(db: Session, workspace_id: UUID) -> dict[str, int]:
        """Fallback usage_count: count rules in ``public.dq_rules`` that
        reference each dataset/field asset (by physical table/column names).
        """
        try:
            with db.begin_nested():
                # Dataset usage — rules whose target_table matches.
                dataset_rows = db.execute(
                    text(
                        """
                        WITH dataset_assets AS (
                            SELECT a.asset_id, d.schema_name, d.physical_identifier AS table_name
                            FROM control.metadata_asset_index a
                            JOIN control.datasets d ON d.dataset_id = a.source_id
                            WHERE a.workspace_id = :wid
                              AND a.asset_type = 'dataset'
                              AND a.source_table = 'datasets'
                        )
                        SELECT da.asset_id, COUNT(r.id) AS usage_count
                        FROM dataset_assets da
                        LEFT JOIN public.dq_rules r
                          ON LOWER(r.target_table) = LOWER(da.table_name)
                         AND (r.target_schema IS NULL
                              OR LOWER(r.target_schema) = LOWER(COALESCE(da.schema_name, '')))
                        GROUP BY da.asset_id
                        """
                    ),
                    {"wid": str(workspace_id)},
                ).fetchall()
                dataset_usage = {str(r.asset_id): int(r.usage_count) for r in dataset_rows}

                # Field usage — inherits the parent dataset's count (proxy
                # since dq_rules.target_columns is array of strings, not
                # asset_ids). Keeps the signal monotonic with rule activity
                # without a costly per-name JSON scan.
                field_rows = db.execute(
                    text(
                        """
                        SELECT f.asset_id, f.parent_asset_id
                        FROM control.metadata_asset_index f
                        WHERE f.workspace_id = :wid
                          AND f.asset_type = 'field'
                          AND f.parent_asset_id IS NOT NULL
                        """
                    ),
                    {"wid": str(workspace_id)},
                ).fetchall()
            out: dict[str, int] = dict(dataset_usage)
            for r in field_rows:
                parent = str(r.parent_asset_id)
                if parent in dataset_usage and dataset_usage[parent] > 0:
                    out[str(r.asset_id)] = dataset_usage[parent]
            return out
        except Exception as exc:  # pragma: no cover
            logger.debug("metadata_context: usage fallback unavailable: %s", exc)
            return {}

    @staticmethod
    def _derive_ownership_from_glossary(
        db: Session, workspace_id: UUID
    ) -> dict[str, dict[str, Any]]:
        """Fallback ownership signal for Signal 11.

        When the dedicated profile index is absent we use the glossary as a
        proxy: assets linked to a glossary term that has a defined ``owner``
        get a small positive cardinality_class signal so the resolver mildly
        prefers documented assets.
        """
        try:
            with db.begin_nested():
                rows = db.execute(
                    text(
                        """
                        SELECT DISTINCT jsonb_array_elements_text(linked_asset_ids) AS asset_id,
                               COALESCE(owner, '') AS owner
                        FROM control.metadata_term_index
                        WHERE workspace_id = :wid
                          AND linked_asset_ids IS NOT NULL
                          AND jsonb_typeof(linked_asset_ids) = 'array'
                        """
                    ),
                    {"wid": str(workspace_id)},
                ).fetchall()
            out: dict[str, dict[str, Any]] = {}
            for r in rows:
                aid = str(r.asset_id)
                has_owner = bool((r.owner or "").strip())
                out[aid] = {
                    "null_rate": 0.0,  # neutral — keeps score_ownership positive
                    "cardinality_class": "high" if has_owner else "medium",
                }
            return out
        except Exception as exc:  # pragma: no cover
            logger.debug("metadata_context: ownership fallback unavailable: %s", exc)
            return {}
