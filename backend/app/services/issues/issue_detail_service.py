"""
IssueDetailService — F033 Issue Detail and Context

Loads an issue by PK and enriches it with resolved context objects for each
foreign-key reference (rule, dataset, assignee, flow execution, node result).

Transaction ownership
---------------------
Read-only.  The service receives a caller-provided SQLAlchemy Session and
executes SELECT queries only — no writes, no commits.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.flow import DQFlow, FlowExecution, FlowNodeResult
from app.models.rule import DQRule
from app.models.user import User
from app.services.issues.issue_models import (
    AssigneeSummary,
    DatasetSummary,
    EnrichedIssueDetail,
    FlowExecutionSummary,
    IssueDetail,
    NodeResultSummary,
    RuleSummary,
)
from app.services.issues.issue_repository import IssueRepository

logger = logging.getLogger(__name__)

_DATASET_SQL = text(
    "SELECT dataset_id, dataset_name, business_domain, criticality, status "
    "FROM control.datasets "
    "WHERE dataset_id = CAST(:dataset_id AS UUID)"
)


class IssueDetailService:
    """Enriches a flat issue detail with resolved FK context objects."""

    def __init__(self, repository: IssueRepository | None = None) -> None:
        self._repo = repository or IssueRepository()

    def get_enriched_detail(
        self,
        db: Session,
        issue_id: UUID,
        workspace_id: UUID,
    ) -> EnrichedIssueDetail | None:
        """
        Load an issue and resolve all FK references into summary objects.

        Returns None when the issue does not exist or belongs to a different
        workspace.  Missing referenced entities produce None context fields
        (graceful degradation — never raises on a deleted FK target).
        """
        detail: IssueDetail | None = self._repo.get_by_id_and_workspace(
            db,
            issue_id,
            workspace_id,
        )
        if detail is None:
            return None

        rule = self._resolve_rule(db, detail.rule_id)
        dataset = self._resolve_dataset(db, detail.dataset_id)
        assignee = self._resolve_assignee(db, detail.assignee_id)
        execution = self._resolve_execution(db, detail.flow_execution_id)
        node_result = self._resolve_node_result(db, detail.flow_node_result_id)

        return EnrichedIssueDetail(
            **detail.model_dump(),
            rule=rule,
            dataset=dataset,
            assignee=assignee,
            flow_execution=execution,
            node_result=node_result,
        )

    # ------------------------------------------------------------------
    # Private resolvers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_rule(db: Session, rule_id: UUID | None) -> RuleSummary | None:
        if rule_id is None:
            return None
        row = db.query(DQRule).filter(DQRule.id == rule_id).first()
        if row is None:
            return None
        _sev = None
        if row.canonical_rule and isinstance(row.canonical_rule, dict):
            _sev = row.canonical_rule.get("severity")
        return RuleSummary(
            id=row.id,
            name=row.name,
            category=row.category,
            severity=_sev,
            status=row.status,
            target_table=row.target_table,
            target_columns=list(row.target_columns) if row.target_columns else None,
        )

    @staticmethod
    def _resolve_dataset(
        db: Session,
        dataset_id: UUID | None,
    ) -> DatasetSummary | None:
        if dataset_id is None:
            return None
        try:
            result = db.execute(_DATASET_SQL, {"dataset_id": str(dataset_id)})
            row = result.fetchone()
        except Exception:
            logger.warning("F033: dataset lookup failed for %s", dataset_id, exc_info=True)
            return None
        if row is None:
            return None
        return DatasetSummary(
            dataset_id=row[0],
            dataset_name=row[1],
            business_domain=row[2],
            criticality=row[3],
            status=row[4],
        )

    @staticmethod
    def _resolve_assignee(
        db: Session,
        assignee_id: UUID | None,
    ) -> AssigneeSummary | None:
        if assignee_id is None:
            return None
        row = db.query(User).filter(User.id == assignee_id).first()
        if row is None:
            return None
        return AssigneeSummary(
            id=row.id,
            display_name=row.full_name or row.email,
            email=row.email,
        )

    @staticmethod
    def _resolve_execution(
        db: Session,
        execution_id: UUID | None,
    ) -> FlowExecutionSummary | None:
        if execution_id is None:
            return None
        row = db.query(FlowExecution).filter(FlowExecution.id == execution_id).first()
        if row is None:
            return None
        flow_name: str | None = None
        if row.flow_id:
            flow = db.query(DQFlow).filter(DQFlow.id == row.flow_id).first()
            if flow:
                flow_name = flow.name
        return FlowExecutionSummary(
            id=row.id,
            flow_name=flow_name,
            status=row.status,
            started_at=row.started_at,
            completed_at=row.completed_at,
            nodes_total=row.nodes_executed,
            nodes_passed=row.nodes_passed,
            nodes_failed=row.nodes_failed,
        )

    @staticmethod
    def _resolve_node_result(
        db: Session,
        node_result_id: UUID | None,
    ) -> NodeResultSummary | None:
        if node_result_id is None:
            return None
        row = db.query(FlowNodeResult).filter(FlowNodeResult.id == node_result_id).first()
        if row is None:
            return None
        result_data: dict = row.result_data or {}
        output_data = result_data.get("output_data") or {}
        # Surface a small, bounded sample (max 20 rows) for the evidence panel
        raw_sample = output_data.get("sample_data") if isinstance(output_data, dict) else None
        sample = raw_sample[:20] if isinstance(raw_sample, list) else None
        raw_violations = result_data.get("violations")
        violations = raw_violations[:50] if isinstance(raw_violations, list) else None
        threshold = result_data.get("threshold")
        if threshold is not None and not isinstance(threshold, str):
            threshold = str(threshold)
        return NodeResultSummary(
            id=row.id,
            node_id=row.node_id,
            node_type=row.node_type,
            status=row.status,
            rows_scanned=result_data.get("rows_scanned"),
            rows_passed=result_data.get("rows_passed"),
            rows_failed=result_data.get("rows_failed"),
            pass_rate=result_data.get("pass_rate"),
            check_type=result_data.get("check_type"),
            dataset=result_data.get("dataset"),
            table_name=result_data.get("table_name"),
            schema_name=result_data.get("schema_name"),
            columns=result_data.get("columns")
            if isinstance(result_data.get("columns"), list)
            else None,
            threshold=threshold,
            violations=violations,
            sample_data=sample,
        )
