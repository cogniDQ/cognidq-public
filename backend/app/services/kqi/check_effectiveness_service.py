"""
CheckEffectivenessService — KQI-041 to KQI-046.

Classifies checks as effective, noisy, always-passing, always-failing, or duplicate.
Computes overall check portfolio effectiveness score and provides
a paginated list of problematic checks with recommendations.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.dashboard import MetricsCache
from app.models.flow import DQFlow, FlowExecution, FlowNodeResult
from app.schemas.kqi import (
    CheckIntelligenceSummaryResponse,
    HealthDistributionItem,
    ProblematicCheck,
    ProblematicChecksResponse,
)

logger = logging.getLogger(__name__)

CACHE_TTL_MINUTES = 15  # Longer TTL for expensive check analysis

# Classification thresholds
NOISY_FLIP_RATE_THRESHOLD = 0.30
ALWAYS_PASSING_DAYS = 90
ALWAYS_PASSING_MIN_RUNS = 10
ALWAYS_FAILING_DAYS = 30
ALWAYS_FAILING_MIN_RUNS = 5
ALWAYS_FAILING_RATE_THRESHOLD = 0.90
MAX_RUNS_PER_CHECK = 30


class CheckEffectivenessService:
    """Service for classifying and scoring check effectiveness."""

    def __init__(self, db: Session):
        self.db = db

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
        import uuid as _uuid

        entry = MetricsCache(
            id=_uuid.uuid4(),
            workspace_id=workspace_id,
            metric_type=metric_type,
            metric_value=value,
            calculated_at=datetime.utcnow(),
        )
        self.db.merge(entry)
        self.db.commit()

    # ------------------------------------------------------------------
    # KQI-041 to KQI-046: Check Intelligence Summary
    # ------------------------------------------------------------------

    def get_summary(
        self, workspace_id: UUID, use_cache: bool = True
    ) -> CheckIntelligenceSummaryResponse:
        """Return check effectiveness summary with classification counts."""

        if use_cache:
            cached = self._get_cached(workspace_id, "kqi_check_intelligence")
            if cached:
                return CheckIntelligenceSummaryResponse(**cached.metric_value)

        classifications = self._classify_all_checks(workspace_id)

        noisy = classifications.get("noisy", [])
        always_pass = classifications.get("always_pass", [])
        always_fail = classifications.get("always_fail", [])
        duplicate = classifications.get("duplicate", [])
        effective = classifications.get("effective", [])

        total = len(noisy) + len(always_pass) + len(always_fail) + len(duplicate) + len(effective)

        # KQI-045: Effectiveness score
        effectiveness_score = round(len(effective) / max(total, 1) * 100, 1) if total > 0 else 0.0

        result = CheckIntelligenceSummaryResponse(
            noisy_checks_count=len(noisy),
            always_passing_count=len(always_pass),
            always_failing_count=len(always_fail),
            duplicate_checks_count=len(duplicate),
            effectiveness_score=effectiveness_score,
            health_distribution=[
                HealthDistributionItem(status="effective", count=len(effective)),
                HealthDistributionItem(status="noisy", count=len(noisy)),
                HealthDistributionItem(status="always_pass", count=len(always_pass)),
                HealthDistributionItem(status="always_fail", count=len(always_fail)),
                HealthDistributionItem(status="duplicate", count=len(duplicate)),
            ],
            has_data=total > 0,
        )

        self._set_cache(workspace_id, "kqi_check_intelligence", result.model_dump())
        return result

    def get_problematic_checks(
        self, workspace_id: UUID, page: int = 1, page_size: int = 20
    ) -> ProblematicChecksResponse:
        """Return paginated list of problematic checks with recommendations."""

        classifications = self._classify_all_checks(workspace_id)

        problematic: list[ProblematicCheck] = []

        for check_info in classifications.get("noisy", []):
            problematic.append(
                ProblematicCheck(
                    check_id=check_info["node_id"],
                    flow_id=check_info["flow_id"],
                    flow_name=check_info.get("flow_name", ""),
                    check_name=check_info.get("check_name", check_info["node_id"]),
                    classification="noisy",
                    flip_rate=check_info.get("flip_rate"),
                    pass_rate_30d=check_info.get("pass_rate_30d"),
                    recommendation="Review threshold or investigate data volatility causing frequent status flips.",
                )
            )

        for check_info in classifications.get("always_pass", []):
            problematic.append(
                ProblematicCheck(
                    check_id=check_info["node_id"],
                    flow_id=check_info["flow_id"],
                    flow_name=check_info.get("flow_name", ""),
                    check_name=check_info.get("check_name", check_info["node_id"]),
                    classification="always_pass",
                    pass_rate_30d=100.0,
                    recommendation="Consider tightening the threshold or removing if the check adds no value.",
                )
            )

        for check_info in classifications.get("always_fail", []):
            problematic.append(
                ProblematicCheck(
                    check_id=check_info["node_id"],
                    flow_id=check_info["flow_id"],
                    flow_name=check_info.get("flow_name", ""),
                    check_name=check_info.get("check_name", check_info["node_id"]),
                    classification="always_fail",
                    pass_rate_30d=check_info.get("pass_rate_30d"),
                    recommendation="Fix underlying data issue or reconfigure threshold. Persistent failures may mask new issues.",
                )
            )

        for check_info in classifications.get("duplicate", []):
            problematic.append(
                ProblematicCheck(
                    check_id=check_info["node_id"],
                    flow_id=check_info["flow_id"],
                    flow_name=check_info.get("flow_name", ""),
                    check_name=check_info.get("check_name", check_info["node_id"]),
                    classification="duplicate",
                    recommendation="Consolidate with similar check to reduce execution overhead.",
                )
            )

        total = len(problematic)
        start = (page - 1) * page_size
        end = start + page_size

        return ProblematicChecksResponse(
            checks=problematic[start:end],
            total=total,
            page=page,
            page_size=page_size,
        )

    # ------------------------------------------------------------------
    # Internal: Classify all checks
    # ------------------------------------------------------------------

    def _classify_all_checks(self, workspace_id: UUID) -> dict[str, list[dict]]:
        """Classify every check in the org into effectiveness categories."""

        # Get all unique checks (flow_id + node_id) with their recent results
        cutoff_90d = datetime.utcnow() - timedelta(days=ALWAYS_PASSING_DAYS)
        cutoff_30d = datetime.utcnow() - timedelta(days=ALWAYS_FAILING_DAYS)

        # Fetch check results grouped by flow_id:node_id
        results = (
            self.db.query(
                FlowExecution.flow_id,
                DQFlow.name.label("flow_name"),
                FlowNodeResult.node_id,
                FlowNodeResult.result_data,
                FlowNodeResult.status,
                FlowNodeResult.created_at,
            )
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.status.in_(["completed", "failed"]),
                    FlowNodeResult.created_at >= cutoff_90d,
                )
            )
            .order_by(FlowNodeResult.created_at.desc())
            .all()
        )

        # Group results by check identity (flow_id:node_id)
        check_history: dict[str, list[dict]] = defaultdict(list)
        check_meta: dict[str, dict] = {}

        for r in results:
            key = f"{r.flow_id}:{r.node_id}"
            rd = r.result_data or {}
            try:
                pr = float(rd.get("pass_rate", 0))
            except (ValueError, TypeError):
                pr = 0.0
            # threshold_pass is numeric; threshold may be a string like "95%"
            thr_raw = rd.get("threshold_pass") or rd.get("threshold")
            try:
                thr = float(str(thr_raw).rstrip("%")) if thr_raw else 80
            except (ValueError, TypeError):
                thr = 80
            passed = r.status == "completed" and pr >= thr
            entry = {
                "passed": passed,
                "pass_rate": pr,
                "created_at": r.created_at,
                "check_type": rd.get("check_type", ""),
                "column": rd.get("column_name") or rd.get("column", ""),
            }
            # Limit to last MAX_RUNS_PER_CHECK per check
            if len(check_history[key]) < MAX_RUNS_PER_CHECK:
                check_history[key].append(entry)

            if key not in check_meta:
                check_meta[key] = {
                    "flow_id": r.flow_id,
                    "flow_name": r.flow_name,
                    "node_id": r.node_id,
                    "check_name": rd.get("check_name") or rd.get("rule_name") or r.node_id,
                    "check_type": rd.get("check_type", ""),
                    "column": rd.get("column_name") or rd.get("column", ""),
                }

        classifications: dict[str, list[dict]] = {
            "noisy": [],
            "always_pass": [],
            "always_fail": [],
            "duplicate": [],
            "effective": [],
        }

        # Detect duplicates: same check_type + column across different flows
        type_col_map: dict[str, list[str]] = defaultdict(list)
        for key, meta in check_meta.items():
            if meta["check_type"] and meta["column"]:
                tc_key = f"{meta['check_type']}:{meta['column']}"
                type_col_map[tc_key].append(key)

        duplicate_keys = set()
        for tc_key, keys in type_col_map.items():
            if len(keys) > 1:
                # All but the first are duplicates
                for k in keys[1:]:
                    duplicate_keys.add(k)

        for key, history in check_history.items():
            meta = check_meta[key]

            if key in duplicate_keys:
                classifications["duplicate"].append(meta)
                continue

            total_runs = len(history)
            if total_runs == 0:
                continue

            passes = [h["passed"] for h in history]
            pass_count = sum(passes)
            pass_rate_overall = pass_count / total_runs

            # Check for always-passing (100% in 90 days, min runs)
            if total_runs >= ALWAYS_PASSING_MIN_RUNS and pass_rate_overall == 1.0:
                classifications["always_pass"].append(meta)
                continue

            # Check for always-failing (>90% fail in 30 days, min runs)
            recent_30d = [h for h in history if h["created_at"] and h["created_at"] >= cutoff_30d]
            if len(recent_30d) >= ALWAYS_FAILING_MIN_RUNS:
                recent_fail_rate = 1 - (sum(1 for h in recent_30d if h["passed"]) / len(recent_30d))
                if recent_fail_rate >= ALWAYS_FAILING_RATE_THRESHOLD:
                    avg_pr = sum(h["pass_rate"] for h in recent_30d) / len(recent_30d)
                    info = {**meta, "pass_rate_30d": round(avg_pr, 1)}
                    classifications["always_fail"].append(info)
                    continue

            # Check for noisy (flip rate > 30%)
            if total_runs >= 2:
                flips = sum(1 for i in range(1, len(passes)) if passes[i] != passes[i - 1])
                flip_rate = flips / (total_runs - 1)
                if flip_rate > NOISY_FLIP_RATE_THRESHOLD:
                    avg_pr = sum(h["pass_rate"] for h in history) / total_runs
                    info = {
                        **meta,
                        "flip_rate": round(flip_rate, 2),
                        "pass_rate_30d": round(avg_pr, 1),
                    }
                    classifications["noisy"].append(info)
                    continue

            # Otherwise effective
            classifications["effective"].append(meta)

        return classifications
