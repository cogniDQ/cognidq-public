"""
AnomalyDetectionService â€” Statistical anomaly detection on DQ execution data.

Detects pass-rate drops, volume anomalies, and failure spikes by comparing
recent rule/flow execution metrics against historical baselines using z-scores.
"""

import logging
import uuid as _uuid
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Float, and_, case, cast, func
from sqlalchemy.orm import Session

from app.models.dashboard import MetricsCache
from app.models.flow import DQFlow, FlowExecution
from app.models.rule import DQRule, RuleExecution

logger = logging.getLogger(__name__)

CACHE_TTL_MINUTES = 5
Z_SCORE_THRESHOLD = 2.0
MIN_EXECUTIONS = 3  # Need at least 3 data points for meaningful statistics


class AnomalyDetectionService:
    """Detects anomalies by comparing recent execution results against historical baselines."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------
    def _get_cached(self, workspace_id: UUID, metric_type: str):
        return (
            self.db.query(MetricsCache)
            .filter(
                and_(
                    MetricsCache.workspace_id == workspace_id,
                    MetricsCache.metric_type == metric_type,
                    MetricsCache.calculated_at
                    > datetime.utcnow() - timedelta(minutes=CACHE_TTL_MINUTES),
                )
            )
            .first()
        )

    def _set_cache(self, workspace_id: UUID, metric_type: str, value: dict):
        cache_entry = MetricsCache(
            id=_uuid.uuid4(),
            workspace_id=workspace_id,
            metric_type=metric_type,
            metric_value=value,
            calculated_at=datetime.utcnow(),
        )
        self.db.add(cache_entry)
        self.db.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_anomaly_summary(
        self, workspace_id: UUID, period_days: int = 30, use_cache: bool = True
    ) -> dict[str, Any]:
        """Summary metrics for detected anomalies."""
        cache_key = f"anomaly_summary_{period_days}"
        if use_cache:
            cached = self._get_cached(workspace_id, cache_key)
            if cached:
                return cached.metric_value

        anomalies = self._detect_all_anomalies(workspace_id, period_days)
        result = {
            "total_anomalies": len(anomalies),
            "critical_anomalies": sum(1 for a in anomalies if a["severity"] == "Critical"),
            "high_anomalies": sum(1 for a in anomalies if a["severity"] == "High"),
            "medium_anomalies": sum(1 for a in anomalies if a["severity"] == "Medium"),
            "low_anomalies": sum(1 for a in anomalies if a["severity"] == "Low"),
            "has_data": self._has_execution_data(workspace_id, period_days),
        }

        if use_cache:
            self._set_cache(workspace_id, cache_key, result)
        return result

    def get_detected_anomalies(
        self, workspace_id: UUID, period_days: int = 30, use_cache: bool = True
    ) -> dict[str, Any]:
        """Detailed list of detected anomalies."""
        cache_key = f"anomaly_detected_{period_days}"
        if use_cache:
            cached = self._get_cached(workspace_id, cache_key)
            if cached:
                return cached.metric_value

        anomalies = self._detect_all_anomalies(workspace_id, period_days)
        result = {
            "anomalies": anomalies,
            "has_data": len(anomalies) > 0 or self._has_execution_data(workspace_id, period_days),
        }

        if use_cache:
            self._set_cache(workspace_id, cache_key, result)
        return result

    def get_volume_trends(
        self, workspace_id: UUID, days: int = 30, use_cache: bool = True
    ) -> dict[str, Any]:
        """Daily execution volume trends."""
        cache_key = f"anomaly_volume_{days}"
        if use_cache:
            cached = self._get_cached(workspace_id, cache_key)
            if cached:
                return cached.metric_value

        cutoff = datetime.utcnow() - timedelta(days=days)
        rows = (
            self.db.query(
                func.date(FlowExecution.started_at).label("day"),
                func.count().label("total_executions"),
                func.sum(case((FlowExecution.status == "failed", 1), else_=0)).label(
                    "failed_executions"
                ),
                func.sum(case((FlowExecution.status == "completed", 1), else_=0)).label(
                    "successful_executions"
                ),
            )
            .join(DQFlow, DQFlow.id == FlowExecution.flow_id)
            .filter(
                DQFlow.workspace_id == workspace_id,
                FlowExecution.started_at >= cutoff,
                FlowExecution.started_at.isnot(None),
            )
            .group_by(func.date(FlowExecution.started_at))
            .order_by(func.date(FlowExecution.started_at))
            .all()
        )

        trends = [
            {
                "date": str(r.day),
                "total_executions": r.total_executions,
                "failed_executions": int(r.failed_executions or 0),
                "successful_executions": int(r.successful_executions or 0),
            }
            for r in rows
        ]
        result = {"trends": trends, "has_data": len(trends) > 0}

        if use_cache:
            self._set_cache(workspace_id, cache_key, result)
        return result

    def get_suggestions(
        self, workspace_id: UUID, period_days: int = 30, use_cache: bool = True
    ) -> dict[str, Any]:
        """Generate actionable suggestions based on detected anomalies."""
        cache_key = f"anomaly_suggestions_{period_days}"
        if use_cache:
            cached = self._get_cached(workspace_id, cache_key)
            if cached:
                return cached.metric_value

        anomalies = self._detect_all_anomalies(workspace_id, period_days)
        suggestions: list[dict[str, str]] = []
        seen_types: set = set()

        for a in anomalies:
            atype = a.get("anomaly_type", "")
            if atype in seen_types:
                continue
            seen_types.add(atype)

            if atype == "pass_rate_drop":
                suggestions.append(
                    {
                        "signal": "Quality rule pass rate degradation",
                        "priority": "P1" if a["severity"] == "Critical" else "P2",
                        "action": "Review data pipeline inputs for the affected rules and check for upstream schema changes",
                        "estimated_impact": f"{a.get('current_value', 'N/A')} current vs {a.get('expected_value', 'N/A')} expected",
                    }
                )
            elif atype == "volume_anomaly":
                suggestions.append(
                    {
                        "signal": "Execution volume deviation",
                        "priority": "P2",
                        "action": "Investigate data source ingestion pipeline for missing or duplicate loads",
                        "estimated_impact": a.get("deviation", "Unknown deviation"),
                    }
                )
            elif atype == "failure_spike":
                suggestions.append(
                    {
                        "signal": "Flow failure rate spike",
                        "priority": "P1",
                        "action": "Check infrastructure health and review failed node error messages",
                        "estimated_impact": a.get("deviation", "Elevated failure rate"),
                    }
                )

        if not suggestions and self._has_execution_data(workspace_id, period_days):
            suggestions.append(
                {
                    "signal": "All systems nominal",
                    "priority": "P3",
                    "action": "No anomalies detected. Consider tightening detection thresholds for proactive monitoring.",
                    "estimated_impact": "No impact â€” healthy state",
                }
            )

        result = {"suggestions": suggestions, "has_data": len(suggestions) > 0}

        if use_cache:
            self._set_cache(workspace_id, cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _has_execution_data(self, workspace_id: UUID, period_days: int) -> bool:
        cutoff = datetime.utcnow() - timedelta(days=period_days)
        count = (
            self.db.query(func.count(RuleExecution.id))
            .join(DQRule, DQRule.id == RuleExecution.rule_id)
            .filter(
                DQRule.workspace_id == workspace_id,
                RuleExecution.started_at >= cutoff,
            )
            .scalar()
        )
        return (count or 0) > 0

    # ------------------------------------------------------------------
    # Core detection engine
    # ------------------------------------------------------------------
    def _detect_all_anomalies(self, workspace_id: UUID, period_days: int) -> list[dict[str, Any]]:
        anomalies: list[dict[str, Any]] = []
        anomalies.extend(self._detect_pass_rate_anomalies(workspace_id, period_days))
        anomalies.extend(self._detect_volume_anomalies(workspace_id, period_days))
        anomalies.extend(self._detect_failure_spike_anomalies(workspace_id, period_days))

        severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        anomalies.sort(key=lambda a: severity_order.get(a["severity"], 4))
        return anomalies

    def _detect_pass_rate_anomalies(
        self, workspace_id: UUID, period_days: int
    ) -> list[dict[str, Any]]:
        """Detect rules with abnormal pass rate drops using z-score."""
        cutoff = datetime.utcnow() - timedelta(days=period_days)

        # Aggregate pass rate stats per rule
        stats = (
            self.db.query(
                RuleExecution.rule_id,
                func.avg(cast(RuleExecution.pass_rate, Float)).label("avg_rate"),
                func.stddev(cast(RuleExecution.pass_rate, Float)).label("std_rate"),
                func.count().label("exec_count"),
            )
            .join(DQRule, DQRule.id == RuleExecution.rule_id)
            .filter(
                DQRule.workspace_id == workspace_id,
                RuleExecution.status == "completed",
                RuleExecution.started_at >= cutoff,
            )
            .group_by(RuleExecution.rule_id)
            .having(func.count() >= MIN_EXECUTIONS)
            .all()
        )

        anomalies = []
        for stat in stats:
            if stat.std_rate is None or float(stat.std_rate) == 0:
                continue

            latest = (
                self.db.query(RuleExecution)
                .filter(
                    RuleExecution.rule_id == stat.rule_id,
                    RuleExecution.status == "completed",
                )
                .order_by(RuleExecution.started_at.desc())
                .first()
            )

            if latest is None or latest.pass_rate is None:
                continue

            z_score = (float(latest.pass_rate) - float(stat.avg_rate)) / float(stat.std_rate)
            if z_score < -Z_SCORE_THRESHOLD:
                rule = self.db.query(DQRule).get(stat.rule_id)
                severity = "Critical" if z_score < -3 else "High" if z_score < -2.5 else "Medium"
                anomalies.append(
                    {
                        "dataset": rule.target_table or rule.name if rule else str(stat.rule_id),
                        "column": (rule.target_columns[0] if rule and rule.target_columns else ""),
                        "anomaly": f"Pass rate drop ({float(latest.pass_rate):.1f}% vs avg {float(stat.avg_rate):.1f}%)",
                        "anomaly_type": "pass_rate_drop",
                        "severity": severity,
                        "detected": latest.started_at.isoformat() if latest.started_at else None,
                        "current_value": f"{float(latest.pass_rate):.1f}%",
                        "expected_value": f"~{float(stat.avg_rate):.1f}%",
                        "deviation": f"{abs(z_score):.1f}Ïƒ below mean",
                        "status": "Active",
                    }
                )

        return anomalies

    def _detect_volume_anomalies(
        self, workspace_id: UUID, period_days: int
    ) -> list[dict[str, Any]]:
        """Detect abnormal daily execution volume changes."""
        cutoff = datetime.utcnow() - timedelta(days=period_days)

        daily_counts = (
            self.db.query(
                func.date(FlowExecution.started_at).label("day"),
                func.count().label("count"),
            )
            .join(DQFlow, DQFlow.id == FlowExecution.flow_id)
            .filter(
                DQFlow.workspace_id == workspace_id,
                FlowExecution.started_at >= cutoff,
                FlowExecution.started_at.isnot(None),
            )
            .group_by(func.date(FlowExecution.started_at))
            .order_by(func.date(FlowExecution.started_at))
            .all()
        )

        if len(daily_counts) < MIN_EXECUTIONS:
            return []

        counts = [float(r.count) for r in daily_counts]
        mean_count = sum(counts) / len(counts)
        variance = sum((c - mean_count) ** 2 for c in counts) / len(counts)
        std_count = variance**0.5

        if std_count == 0:
            return []

        anomalies = []
        latest_count = counts[-1]
        latest_date = str(daily_counts[-1].day)
        z = (latest_count - mean_count) / std_count

        if abs(z) > Z_SCORE_THRESHOLD:
            direction = "spike" if z > 0 else "drop"
            severity = "High" if abs(z) > 3 else "Medium"
            anomalies.append(
                {
                    "dataset": "All flows",
                    "column": "",
                    "anomaly": f"Execution volume {direction} ({int(latest_count)} vs avg {mean_count:.0f})",
                    "anomaly_type": "volume_anomaly",
                    "severity": severity,
                    "detected": latest_date,
                    "current_value": f"{int(latest_count)} executions",
                    "expected_value": f"~{mean_count:.0f} executions/day",
                    "deviation": f"{abs(z):.1f}Ïƒ {'above' if z > 0 else 'below'} mean",
                    "status": "Active",
                }
            )

        return anomalies

    def _detect_failure_spike_anomalies(
        self, workspace_id: UUID, period_days: int
    ) -> list[dict[str, Any]]:
        """Detect days with abnormally high failure rates."""
        cutoff = datetime.utcnow() - timedelta(days=period_days)

        daily_stats = (
            self.db.query(
                func.date(FlowExecution.started_at).label("day"),
                func.count().label("total"),
                func.sum(case((FlowExecution.status == "failed", 1), else_=0)).label("failures"),
            )
            .join(DQFlow, DQFlow.id == FlowExecution.flow_id)
            .filter(
                DQFlow.workspace_id == workspace_id,
                FlowExecution.started_at >= cutoff,
                FlowExecution.started_at.isnot(None),
            )
            .group_by(func.date(FlowExecution.started_at))
            .order_by(func.date(FlowExecution.started_at))
            .all()
        )

        if len(daily_stats) < MIN_EXECUTIONS:
            return []

        failure_rates = [
            float(r.failures or 0) / float(r.total) * 100 if r.total > 0 else 0 for r in daily_stats
        ]
        mean_rate = sum(failure_rates) / len(failure_rates)
        variance = sum((r - mean_rate) ** 2 for r in failure_rates) / len(failure_rates)
        std_rate = variance**0.5

        if std_rate == 0:
            return []

        anomalies = []
        latest_rate = failure_rates[-1]
        latest_date = str(daily_stats[-1].day)
        z = (latest_rate - mean_rate) / std_rate

        if z > Z_SCORE_THRESHOLD:
            severity = "Critical" if z > 3 else "High"
            anomalies.append(
                {
                    "dataset": "All flows",
                    "column": "",
                    "anomaly": f"Failure rate spike ({latest_rate:.1f}% vs avg {mean_rate:.1f}%)",
                    "anomaly_type": "failure_spike",
                    "severity": severity,
                    "detected": latest_date,
                    "current_value": f"{latest_rate:.1f}% failure rate",
                    "expected_value": f"~{mean_rate:.1f}% failure rate",
                    "deviation": f"{z:.1f}Ïƒ above mean",
                    "status": "Active",
                }
            )

        return anomalies
