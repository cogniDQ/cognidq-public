"""F5 — Persisted anomaly service.

Wraps :class:`AnomalyDetectionService` to run detection, persist results into
``public.detected_anomalies`` (with fingerprint-based dedup), and expose
list/acknowledge/resolve operations.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.models.detected_anomaly import DetectedAnomaly
from app.services.kqi.anomaly_detection_service import AnomalyDetectionService

logger = logging.getLogger(__name__)

# Window during which an anomaly with the same fingerprint is treated as the
# same incident (we update detected_at instead of inserting a duplicate).
DEDUP_WINDOW = timedelta(hours=24)


def _fingerprint(workspace_id: UUID, anomaly: dict[str, Any]) -> str:
    parts = [
        str(workspace_id),
        anomaly.get("anomaly_type", ""),
        anomaly.get("dataset", "") or "",
        anomaly.get("column", "") or "",
        str(anomaly.get("rule_id") or ""),
    ]
    # Not security-sensitive: used only for dedup fingerprinting, not auth/integrity.
    return hashlib.sha1("|".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()


class PersistedAnomalyService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Detection + persistence
    # ------------------------------------------------------------------
    def detect_and_persist(
        self,
        workspace_id: UUID,
        tenant_id: UUID,
        period_days: int = 30,
    ) -> dict[str, Any]:
        """Run statistical detection and upsert results.

        Returns a summary dict: {detected, inserted, updated}.
        """
        detector = AnomalyDetectionService(self.db)
        # use_cache=False so we always evaluate against latest data
        result = detector.get_detected_anomalies(
            workspace_id, period_days=period_days, use_cache=False
        )
        detected: list[dict[str, Any]] = result.get("anomalies", []) or []

        inserted = 0
        updated = 0
        now = datetime.now(UTC)
        cutoff = now - DEDUP_WINDOW

        for a in detected:
            fp = _fingerprint(workspace_id, a)
            existing = (
                self.db.query(DetectedAnomaly)
                .filter(
                    and_(
                        DetectedAnomaly.workspace_id == workspace_id,
                        DetectedAnomaly.fingerprint == fp,
                        DetectedAnomaly.status.in_(["open", "acknowledged"]),
                        DetectedAnomaly.detected_at >= cutoff,
                    )
                )
                .order_by(desc(DetectedAnomaly.detected_at))
                .first()
            )

            if existing is not None:
                existing.severity = a.get("severity", existing.severity)
                existing.summary = a.get("anomaly", existing.summary)
                existing.current_value = a.get("current_value", existing.current_value)
                existing.expected_value = a.get("expected_value", existing.expected_value)
                existing.deviation = a.get("deviation", existing.deviation)
                existing.detected_at = now
                existing.updated_at = now
                updated += 1
            else:
                rec = DetectedAnomaly(
                    workspace_id=workspace_id,
                    tenant_id=tenant_id,
                    anomaly_type=a.get("anomaly_type", "unknown"),
                    severity=a.get("severity", "Medium"),
                    dataset=a.get("dataset"),
                    column_name=a.get("column"),
                    rule_id=a.get("rule_id"),
                    summary=a.get("anomaly", ""),
                    current_value=a.get("current_value"),
                    expected_value=a.get("expected_value"),
                    deviation=a.get("deviation"),
                    fingerprint=fp,
                    detected_at=now,
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(rec)
                inserted += 1

        self.db.commit()
        return {"detected": len(detected), "inserted": inserted, "updated": updated}

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------
    def list_anomalies(
        self,
        workspace_id: UUID,
        status: str | None = None,
        severity: str | None = None,
        anomaly_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        q = self.db.query(DetectedAnomaly).filter(DetectedAnomaly.workspace_id == workspace_id)
        if status:
            q = q.filter(DetectedAnomaly.status == status)
        if severity:
            q = q.filter(DetectedAnomaly.severity == severity)
        if anomaly_type:
            q = q.filter(DetectedAnomaly.anomaly_type == anomaly_type)

        total = q.count()
        rows = q.order_by(desc(DetectedAnomaly.detected_at)).offset(offset).limit(limit).all()

        return {
            "total": total,
            "items": [self._serialize(r) for r in rows],
        }

    def get(self, workspace_id: UUID, anomaly_id: UUID) -> DetectedAnomaly | None:
        return (
            self.db.query(DetectedAnomaly)
            .filter(
                DetectedAnomaly.id == anomaly_id,
                DetectedAnomaly.workspace_id == workspace_id,
            )
            .first()
        )

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------
    def acknowledge(
        self, workspace_id: UUID, anomaly_id: UUID, actor_id: UUID, notes: str | None = None
    ) -> DetectedAnomaly | None:
        rec = self.get(workspace_id, anomaly_id)
        if rec is None:
            return None
        rec.status = "acknowledged"
        rec.acknowledged_at = datetime.now(UTC)
        rec.acknowledged_by = actor_id
        if notes:
            rec.notes = notes
        rec.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(rec)
        return rec

    def resolve(
        self, workspace_id: UUID, anomaly_id: UUID, actor_id: UUID, notes: str | None = None
    ) -> DetectedAnomaly | None:
        rec = self.get(workspace_id, anomaly_id)
        if rec is None:
            return None
        rec.status = "resolved"
        rec.resolved_at = datetime.now(UTC)
        rec.resolved_by = actor_id
        if notes:
            rec.notes = notes
        rec.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(rec)
        return rec

    def suppress(
        self, workspace_id: UUID, anomaly_id: UUID, actor_id: UUID, notes: str | None = None
    ) -> DetectedAnomaly | None:
        rec = self.get(workspace_id, anomaly_id)
        if rec is None:
            return None
        rec.status = "suppressed"
        rec.resolved_at = datetime.now(UTC)
        rec.resolved_by = actor_id
        if notes:
            rec.notes = notes
        rec.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(rec)
        return rec

    # ------------------------------------------------------------------
    @staticmethod
    def _serialize(r: DetectedAnomaly) -> dict[str, Any]:
        return {
            "id": str(r.id),
            "workspace_id": str(r.workspace_id),
            "anomaly_type": r.anomaly_type,
            "severity": r.severity,
            "dataset": r.dataset,
            "column": r.column_name,
            "rule_id": str(r.rule_id) if r.rule_id else None,
            "summary": r.summary,
            "current_value": r.current_value,
            "expected_value": r.expected_value,
            "deviation": r.deviation,
            "status": r.status,
            "detected_at": r.detected_at.isoformat() if r.detected_at else None,
            "acknowledged_at": r.acknowledged_at.isoformat() if r.acknowledged_at else None,
            "acknowledged_by": str(r.acknowledged_by) if r.acknowledged_by else None,
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            "resolved_by": str(r.resolved_by) if r.resolved_by else None,
            "notes": r.notes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
