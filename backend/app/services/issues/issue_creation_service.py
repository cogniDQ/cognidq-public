"""
IssueCreationService — F031 Automatic Issue Creation

Creates Issue records automatically when a FlowNodeResult has status='failed'.
Implements all 13 logic steps from TDD §5.3.

Transaction ownership
---------------------
The service receives a caller-provided SQLAlchemy Session.  It does NOT commit.
On a successful insert the caller is responsible for calling ``db.commit()``.
On an internal DB exception the service calls ``db.rollback()`` to restore the
session to a clean state, logs at ERROR level, and returns None.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.flow import DQFlow, FlowExecution, FlowNodeResult
from app.models.rule import DQRule
from app.services.incidents.auto_incident_service import AutoIncidentService
from app.services.issues.issue_grouping_service import IssueGroupingService
from app.services.issues.issue_models import IssueDomain
from app.services.issues.issue_repository import IssueRepository
from app.services.issues.sample_capture_service import SampleCaptureService
from app.services.workspaces import settings_repository as _settings_repo
from app.services.workspaces.repository import WorkspaceRepository

logger = logging.getLogger(__name__)

_workspace_repo = WorkspaceRepository()


class IssueCreationService:
    """Creates Issue records automatically when a check node fails."""

    def __init__(
        self,
        repository: IssueRepository | None = None,
        grouping_service: IssueGroupingService | None = None,
        sample_service: SampleCaptureService | None = None,
        auto_incident_service: AutoIncidentService | None = None,
    ) -> None:
        self._repo = repository or IssueRepository()
        self._grouping_service = grouping_service or IssueGroupingService(self._repo)
        self._sample_service = sample_service or SampleCaptureService()
        self._auto_incident_service = auto_incident_service or AutoIncidentService()

    def create_from_node_result(
        self,
        db: Session,
        node_result_id: UUID,
        flow_execution_id: UUID,
    ) -> IssueDomain | None:
        """
        Create an Issue from a failed FlowNodeResult.

        Implements TDD §5.3 logic steps 1–13.

        Parameters
        ----------
        db:
            SQLAlchemy Session (caller-owned; service does not commit).
        node_result_id:
            PK of the FlowNodeResult to evaluate.
        flow_execution_id:
            PK of the parent FlowExecution (used to load DQFlow → workspace_id).

        Returns
        -------
        IssueDomain | None
            Persisted (flushed) domain model on success, None if no issue
            should be created or if an error is caught internally.
        """
        # Step 1 — Load node result; guard on status
        node_result: FlowNodeResult | None = (
            db.query(FlowNodeResult).filter(FlowNodeResult.id == node_result_id).first()
        )
        if node_result is None or node_result.status != "failed":
            return None

        # Step 2 — Load flow execution; extract flow_id
        execution: FlowExecution | None = (
            db.query(FlowExecution).filter(FlowExecution.id == flow_execution_id).first()
        )
        if execution is None:
            logger.error(
                "F031 issue creation: FlowExecution %s not found",
                flow_execution_id,
            )
            return None

        # Step 3 — Load DQFlow; extract workspace_id (stored as workspace_id)
        flow: DQFlow | None = db.query(DQFlow).filter(DQFlow.id == execution.flow_id).first()
        if flow is None:
            logger.error(
                "F031 issue creation: DQFlow %s not found",
                execution.flow_id,
            )
            return None

        workspace_id: UUID = flow.workspace_id

        # Step 4 — Load workspace settings via settings repository directly
        # (background task has no JWT actor context; use any-tenant path)
        settings_row = _settings_repo.find_by_workspace_id(db, workspace_id, tenant_id=None)
        workspace_settings = settings_row.with_defaults() if settings_row else None

        # Step 4a — Grouping check (F032)
        policy = (
            getattr(workspace_settings, "issue_grouping_policy", "one_per_execution")
            if workspace_settings
            else "one_per_execution"
        )
        tz_name = (
            getattr(workspace_settings, "default_timezone", "UTC") if workspace_settings else "UTC"
        )
        # Metrics needed for grouping check (steps 6 & 7 extracted early for step 4a)
        _early_node_config = _get_node_config(flow.flow_definition, node_result.node_id)
        _early_rule_id_raw = _early_node_config.get("rule_id")
        _early_rule_id: UUID | None = UUID(_early_rule_id_raw) if _early_rule_id_raw else None
        if _early_rule_id is None:
            _early_rule_id = _resolve_rule_id_fallback(db, workspace_id, _early_node_config)
        _early_dataset_id_raw = _early_node_config.get("dataset_id")
        _early_dataset_id: UUID | None = (
            UUID(_early_dataset_id_raw) if _early_dataset_id_raw else None
        )
        if _early_dataset_id is None:
            _early_dataset_id = _resolve_dataset_id_fallback(
                db,
                workspace_id,
                flow.flow_definition,
                node_result.node_id,
                _early_node_config,
            )
        _early_result_data: dict = node_result.result_data or {}
        _early_rows_failed: int = int(_early_result_data.get("rows_failed", 0))
        _early_opened_at = node_result.completed_at

        if policy != "one_per_execution" and _early_rule_id and _early_dataset_id:
            try:
                grouped = self._grouping_service.find_and_update_candidate(
                    db=db,
                    workspace_id=workspace_id,
                    rule_id=_early_rule_id,
                    dataset_id=_early_dataset_id,
                    policy=policy,
                    workspace_timezone=tz_name,
                    new_rows_failed=_early_rows_failed,
                    new_completed_at=_early_opened_at,
                )
                if grouped is not None:
                    db.flush()
                    logger.info(
                        "F032 issue grouped: issue_id=%s workspace=%s rule=%s "
                        "dataset=%s policy=%s new_failure_count=%s execution=%s",
                        grouped.id,
                        workspace_id,
                        _early_rule_id,
                        _early_dataset_id,
                        policy,
                        grouped.failure_count,
                        flow_execution_id,
                    )
                    return grouped
            except Exception as exc:
                logger.warning(
                    "F032 grouping check failed, falling back to new issue: "
                    "workspace=%s rule=%s exc=%s",
                    workspace_id,
                    _early_rule_id,
                    exc,
                )
                # Fall through to normal issue creation

        # Step 5 — Resolve rule_id from node config; load rule severity
        node_config = _get_node_config(flow.flow_definition, node_result.node_id)
        rule_id_raw: str | None = node_config.get("rule_id")
        rule_id: UUID | None = UUID(rule_id_raw) if rule_id_raw else None

        # F11 fallback — NL-generated flows often omit rule_id from the check
        # node config. Resolve by (workspace_id, rule name) so the auto-created
        # Issue still links to the rule that owns it.
        if rule_id is None:
            rule_id = _resolve_rule_id_fallback(db, workspace_id, node_config)

        severity: str = "minor"  # conservative default if rule is absent
        # Prefer severity declared directly on the check node config (NL rule
        # builder sets this when the flow was generated from natural language
        # without an associated DQRule row).
        node_severity = node_config.get("severity")
        if node_severity:
            severity = _normalise_severity(str(node_severity))
        if rule_id:
            rule = db.query(DQRule).filter(DQRule.id == rule_id).first()
            if rule:
                # severity lives in canonical_rule JSON, not as a direct column
                _sev = None
                if rule.canonical_rule and isinstance(rule.canonical_rule, dict):
                    _sev = rule.canonical_rule.get("severity")
                if _sev:
                    severity = _normalise_severity(_sev)

        # Step 6 — dataset_id from node config (nullable)
        dataset_id_raw: str | None = node_config.get("dataset_id")
        dataset_id: UUID | None = UUID(dataset_id_raw) if dataset_id_raw else None

        # F11 fallback — for NL-generated flows the check node has no
        # dataset_id; walk back through connections to the upstream source
        # node, or look the dataset up by name/physical identifier.
        if dataset_id is None:
            dataset_id = _resolve_dataset_id_fallback(
                db,
                workspace_id,
                flow.flow_definition,
                node_result.node_id,
                node_config,
            )

        # Step 7 — Extract metrics from result_data; use safe defaults
        result_data: dict = node_result.result_data or {}
        rows_scanned: int = int(result_data.get("rows_scanned", 0))
        rows_failed: int = int(result_data.get("rows_failed", 0))
        pass_rate_raw = result_data.get("pass_rate")

        # Step 8 — Build impact_summary
        impact_summary: str = _build_impact_summary(rows_failed, rows_scanned, pass_rate_raw)

        # Step 9 — Compute due_at using workspace SLA policy
        sla_policy = workspace_settings.sla_policy if workspace_settings else None
        opened_at = node_result.completed_at
        due_at = _compute_due_at(opened_at, severity, sla_policy)

        # Step 10 — Resolve tenant_id via workspace lookup (cross-schema)
        try:
            workspace = _workspace_repo.find_by_id_any_tenant(db, workspace_id)
            tenant_id: UUID = workspace.tenant_id
        except Exception as exc:
            logger.error(
                "F031 issue creation: could not resolve tenant_id for workspace %s: %s",
                workspace_id,
                exc,
            )
            return None

        # F11 — resolve dataset_name + dataset owner for humanised title +
        # assignee. Cheap single-row lookup using the dataset_id we just
        # resolved (may still be None for sourceless flows; that is fine).
        dataset_name: str | None = None
        assignee_id: UUID | None = None
        if dataset_id is not None:
            try:
                from sqlalchemy import text as _sql_text

                _row = db.execute(
                    _sql_text(
                        "SELECT dataset_name, owner_user_id FROM control.datasets "
                        "WHERE dataset_id = CAST(:dsid AS UUID) "
                        "  AND workspace_id = CAST(:ws AS UUID) LIMIT 1"
                    ),
                    {"dsid": str(dataset_id), "ws": str(workspace_id)},
                ).fetchone()
                if _row is not None:
                    dataset_name = _row[0]
                    assignee_id = _row[1]
            except Exception as exc:
                logger.warning(
                    "F11: dataset lookup failed for dataset %s: %s",
                    dataset_id,
                    exc,
                )

        # F11/F7 — humanised title: prefer rule name + dataset name when known.
        title = _build_humanised_title(
            severity=severity,
            rule_id=rule_id,
            db=db,
            node_result=node_result,
            node_config=node_config,
            dataset_name=dataset_name,
        )

        # Build IssueDomain (step 10 continued)
        issue_domain = IssueDomain(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            flow_execution_id=flow_execution_id,
            flow_node_result_id=node_result_id,
            rule_id=rule_id,
            dataset_id=dataset_id,
            assignee_id=assignee_id,
            issue_type="threshold_breach",
            severity=severity,
            title=title,
            impact_summary=impact_summary,
            failure_count=rows_failed,
            rows_scanned=rows_scanned,
            pass_rate=pass_rate_raw,
            due_at=due_at,
            opened_at=opened_at,
        )

        # Step 11 — Insert with isolated exception handling
        try:
            persisted = self._repo.insert(db, issue_domain)
        except Exception as exc:
            # Step 12 — On DB exception: rollback session, log at ERROR, return None
            try:
                db.rollback()
            except Exception:
                pass
            logger.error(
                "F031 issue creation failed",
                extra={
                    "flow_execution_id": str(flow_execution_id),
                    "flow_node_result_id": str(node_result_id),
                    "rule_id": str(rule_id) if rule_id else None,
                    "workspace_id": str(workspace_id),
                    "exc_type": type(exc).__name__,
                    "exc_message": str(exc),
                },
            )
            return None

        # Step 13 — Log success and return
        logger.info(
            "F031 issue created",
            extra={
                "issue_id": str(persisted.id),
                "workspace_id": str(workspace_id),
                "severity": severity,
                "flow_execution_id": str(flow_execution_id),
                "rule_id": str(rule_id) if rule_id else None,
            },
        )

        # Step 13a — Sample capture (F034, non-blocking)
        try:
            self._sample_service.capture_for_issue(
                db=db,
                issue_id=persisted.id,
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                node_result_result_data=result_data,
            )
        except Exception as exc:
            logger.warning(
                "F034 sample capture failed, issue=%s exc=%s",
                persisted.id,
                exc,
            )

        # Step 13b — Auto-incident creation (F039, non-blocking)
        try:
            _inc_policy = getattr(workspace_settings, "incident_policy", None)
            self._auto_incident_service.evaluate_and_create(
                db,
                workspace_id=workspace_id,
                tenant_id=tenant_id,
                issue_id=persisted.id,
                issue_severity=severity,
                issue_failure_count=persisted.failure_count,
                issue_title=persisted.title,
                policy=_inc_policy,
            )
        except Exception as exc:
            logger.warning(
                "F039 auto-incident creation failed, issue=%s exc=%s",
                persisted.id,
                exc,
            )

        # Step 13c — issue_created alert trigger (best-effort, non-blocking)
        try:
            from app.services.alerts.alert_trigger_service import AlertTriggerService

            AlertTriggerService().trigger(
                db,
                workspace_id=workspace_id,
                tenant_id=tenant_id,
                trigger_type="issue_created",
                payload={
                    "issue_id": str(persisted.id),
                    "title": persisted.title,
                    "severity": severity,
                    "dataset_id": str(dataset_id) if dataset_id else None,
                    "rule_id": str(rule_id) if rule_id else None,
                    "flow_execution_id": str(flow_execution_id),
                },
                audit_ctx=None,
            )
        except Exception as exc:
            logger.warning(
                "issue_created alert trigger failed, issue=%s exc=%s",
                persisted.id,
                exc,
            )

        return persisted

    # ─────────────────────────────────────────────────────────────────────
    # F6 — Auto-create Issue from a direct rule execution (no Flow)
    # ─────────────────────────────────────────────────────────────────────

    def create_from_rule_execution(
        self,
        db: Session,
        rule_execution_id: UUID,
    ) -> IssueDomain | None:
        """
        Create an Issue from a completed ``RuleExecution`` that has rows_failed > 0.

        This is the rule-only counterpart to ``create_from_node_result``: it is
        triggered by ``RuleExecutor.execute_rule`` so that users running a
        single rule from the Rules UI (without a Flow) still get an Issue.

        Best-effort: any exception is logged and ``None`` is returned. The caller
        is responsible for ``commit()``.
        """
        from app.models.rule import DQRule, RuleExecution

        # Step 1 — Load execution; guard on terminal state and failed rows
        execution: RuleExecution | None = (
            db.query(RuleExecution).filter(RuleExecution.id == rule_execution_id).first()
        )
        if execution is None:
            logger.error("F6: RuleExecution %s not found", rule_execution_id)
            return None
        if execution.status != "completed":
            return None
        if int(execution.rows_failed or 0) <= 0:
            return None

        # Step 2 — Load rule
        rule: DQRule | None = db.query(DQRule).filter(DQRule.id == execution.rule_id).first()
        if rule is None:
            logger.error(
                "F6: DQRule %s not found for execution %s", execution.rule_id, rule_execution_id
            )
            return None

        workspace_id: UUID = rule.workspace_id

        # Step 3 — Severity from rule (canonical_rule.severity preferred)
        severity = "minor"
        if rule.canonical_rule and isinstance(rule.canonical_rule, dict):
            _sev = rule.canonical_rule.get("severity")
            if _sev:
                severity = _normalise_severity(str(_sev))

        # Step 4 — Resolve dataset_id + owner via control.datasets lookup
        dataset_id: UUID | None = None
        assignee_id: UUID | None = None
        dataset_name: str | None = None
        try:
            from sqlalchemy import text as _sql_text

            row = db.execute(
                _sql_text(
                    "SELECT dataset_id, dataset_name, owner_user_id "
                    "FROM control.datasets "
                    "WHERE workspace_id = CAST(:ws AS UUID) "
                    "  AND (lower(physical_identifier) = lower(:t) "
                    "       OR lower(dataset_name) = lower(:t)) "
                    "  AND (:s IS NULL OR lower(schema_name) = lower(:s)) "
                    "LIMIT 1"
                ),
                {
                    "ws": str(workspace_id),
                    "t": rule.target_table,
                    "s": rule.target_schema,
                },
            ).fetchone()
            if row is not None:
                dataset_id = row[0]
                dataset_name = row[1]
                assignee_id = row[2]
        except Exception as exc:
            logger.warning("F6: dataset lookup failed for rule %s: %s", rule.id, exc)

        # Step 5 — Resolve tenant_id
        try:
            workspace = _workspace_repo.find_by_id_any_tenant(db, workspace_id)
            tenant_id: UUID = workspace.tenant_id
        except Exception as exc:
            logger.error("F6: could not resolve tenant_id for workspace %s: %s", workspace_id, exc)
            return None

        # Step 6 — Workspace settings (for SLA/incident policy)
        settings_row = _settings_repo.find_by_workspace_id(db, workspace_id, tenant_id=None)
        workspace_settings = settings_row.with_defaults() if settings_row else None
        sla_policy = workspace_settings.sla_policy if workspace_settings else None

        # Step 7 — Build metrics
        rows_failed = int(execution.rows_failed or 0)
        rows_scanned = int(execution.rows_scanned or 0)
        pass_rate = execution.pass_rate
        impact_summary = _build_impact_summary(rows_failed, rows_scanned, pass_rate)
        opened_at = execution.completed_at
        due_at = _compute_due_at(opened_at, severity, sla_policy)

        # Step 8 — Humanised title (F7): compose using rule.name (+ canonical_rule
        # fallbacks) and the resolved dataset_name for the same look/feel as
        # the flow path.
        primary_text: str | None = rule.name
        if not primary_text and isinstance(rule.canonical_rule, dict):
            cr = rule.canonical_rule
            primary_text = cr.get("description") or cr.get("nl_text") or cr.get("name")
        title = _compose_title(severity, primary_text or "", dataset_name)

        issue_domain = IssueDomain(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            flow_execution_id=None,
            flow_node_result_id=None,
            rule_id=rule.id,
            dataset_id=dataset_id,
            assignee_id=assignee_id,
            issue_type="threshold_breach",
            severity=severity,
            title=title,
            impact_summary=impact_summary,
            failure_count=rows_failed,
            rows_scanned=rows_scanned,
            pass_rate=pass_rate,
            due_at=due_at,
            opened_at=opened_at,
        )

        # Step 9 — Insert
        try:
            persisted = self._repo.insert(db, issue_domain)
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            logger.error(
                "F6 issue creation failed",
                extra={
                    "rule_execution_id": str(rule_execution_id),
                    "rule_id": str(rule.id),
                    "workspace_id": str(workspace_id),
                    "exc_type": type(exc).__name__,
                    "exc_message": str(exc),
                },
            )
            return None

        logger.info(
            "F6 issue created from rule execution",
            extra={
                "issue_id": str(persisted.id),
                "workspace_id": str(workspace_id),
                "severity": severity,
                "rule_id": str(rule.id),
                "rule_execution_id": str(rule_execution_id),
            },
        )

        # Step 10 — Sample capture (F034): pass violations from result_details
        try:
            result_data = execution.result_details or {}
            # Pull violations from the rule_violations table since
            # RuleExecution.result_details only stores aggregates.
            from app.models.rule import RuleViolation

            v_rows = (
                db.query(RuleViolation)
                .filter(RuleViolation.execution_id == execution.id)
                .limit(100)
                .all()
            )
            violations = [(v.violation_details or {}) for v in v_rows]
            self._sample_service.capture_for_issue(
                db=db,
                issue_id=persisted.id,
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                node_result_result_data={**result_data, "violations": violations},
            )
        except Exception as exc:
            logger.warning("F034 sample capture (F6) failed, issue=%s exc=%s", persisted.id, exc)

        # Step 11 — Auto-incident (best-effort)
        try:
            _inc_policy = getattr(workspace_settings, "incident_policy", None)
            self._auto_incident_service.evaluate_and_create(
                db,
                workspace_id=workspace_id,
                tenant_id=tenant_id,
                issue_id=persisted.id,
                issue_severity=severity,
                issue_failure_count=persisted.failure_count,
                issue_title=persisted.title,
                policy=_inc_policy,
            )
        except Exception as exc:
            logger.warning("F039 auto-incident (F6) failed, issue=%s exc=%s", persisted.id, exc)

        # Step 12 — issue_created alert trigger (best-effort)
        try:
            from app.services.alerts.alert_trigger_service import AlertTriggerService

            AlertTriggerService().trigger(
                db,
                workspace_id=workspace_id,
                tenant_id=tenant_id,
                trigger_type="issue_created",
                payload={
                    "issue_id": str(persisted.id),
                    "title": persisted.title,
                    "severity": severity,
                    "dataset_id": str(dataset_id) if dataset_id else None,
                    "rule_id": str(rule.id),
                    "rule_execution_id": str(rule_execution_id),
                },
                audit_ctx=None,
            )
        except Exception as exc:
            logger.warning(
                "issue_created alert trigger (F6) failed, issue=%s exc=%s", persisted.id, exc
            )

        return persisted


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────


def _get_node_config(flow_definition: dict | None, node_id: str) -> dict:
    """Return the ``config`` dict for *node_id* from *flow_definition*, or {}."""
    if not flow_definition:
        return {}
    for node in flow_definition.get("nodes", []):
        if node.get("id") == node_id:
            return node.get("config", {})
    return {}


# Mapping from DQRule.severity vocabulary to Issue severity domain values.
_SEVERITY_MAP: dict[str, str] = {
    "blocker": "critical",
    "critical": "critical",
    "high": "major",
    "major": "major",
    "medium": "minor",
    "minor": "minor",
    "low": "informational",
    "info": "informational",
    "informational": "informational",
}


def _normalise_severity(rule_severity: str) -> str:
    """Map ``DQRule.severity`` values to the issue severity domain enum."""
    return _SEVERITY_MAP.get(rule_severity.lower(), "minor")


def _build_impact_summary(rows_failed: int, rows_scanned: int, pass_rate) -> str:
    """Build the human-readable impact summary per TDD §5.3 step 8.

    Examples
    --------
    >>> _build_impact_summary(150, 1000, 85.0)
    '150 of 1000 rows failed (85.0% pass rate)'
    """
    if pass_rate is not None:
        return f"{rows_failed} of {rows_scanned} rows failed ({float(pass_rate):.1f}% pass rate)"
    return f"{rows_failed} of {rows_scanned} rows failed"


def _build_title(node_result: FlowNodeResult, severity: str) -> str:
    """Build a short descriptive title for the auto-created issue."""
    return f"[{severity.upper()}] Check failed: node {node_result.node_id}"


def _build_humanised_title(
    *,
    severity: str,
    rule_id: UUID | None,
    db: Session,
    node_result: FlowNodeResult,
    node_config: dict,
    dataset_name: str | None,
) -> str:
    """F7/F11 — humanised title: ``[SEV] <rule name> — <dataset name>``.

    Resolution order for the rule descriptor:
    1. ``DQRule.name`` (if rule_id resolves).
    2. ``DQRule.canonical_rule.description`` / ``.nl_text`` / ``.name``
       (NL-built rules where ``name`` is a generated id).
    3. ``node_config.rule_name`` / ``ruleName`` (NL flow check node).
    4. ``node_config.description`` / ``nl_rule_text``.
    5. Legacy ``[SEV] Check failed: node <id>``.
    """
    rule_name: str | None = None
    rule_obj = None
    if rule_id is not None:
        try:
            rule_obj = db.query(DQRule).filter(DQRule.id == rule_id).first()
        except Exception:
            rule_obj = None
    if rule_obj is not None:
        if rule_obj.name:
            rule_name = rule_obj.name
        if not rule_name and isinstance(rule_obj.canonical_rule, dict):
            cr = rule_obj.canonical_rule
            rule_name = cr.get("description") or cr.get("nl_text") or cr.get("name")
    if not rule_name:
        rule_name = node_config.get("rule_name") or node_config.get("ruleName")
    if not rule_name:
        rule_name = node_config.get("description") or node_config.get("nl_rule_text")

    if rule_name:
        return _compose_title(severity, rule_name, dataset_name)

    return _build_title(node_result, severity)[:500]


def _compose_title(severity: str, primary: str, dataset_name: str | None) -> str:
    """F7 — compose a clean humanised title.

    Strips a leading ``[SEV] `` if *primary* already carries one (defensive
    against double-prefixing when rule names were generated from old auto
    titles). Truncates at 500 chars to satisfy ``issues.title`` VARCHAR(500).
    """
    text = (primary or "").strip()
    # Defensive: strip any pre-existing severity bracket prefix.
    if text.startswith("[") and "]" in text:
        try:
            close = text.index("]")
            bracket = text[1:close].strip().lower()
            if bracket in {"critical", "major", "minor", "informational", "info"}:
                text = text[close + 1 :].strip()
        except ValueError:
            pass
    title = f"[{severity.upper()}] {text}" if text else f"[{severity.upper()}]"
    if dataset_name:
        title = f"{title} \u2014 {dataset_name}"
    return title[:500]


def _resolve_rule_id_fallback(db: Session, workspace_id: UUID, node_config: dict) -> UUID | None:
    """F11 — best-effort: resolve ``rule_id`` from the rule name on the
    check-node config when the flow definition omitted it. Returns ``None``
    when no unique active match exists."""
    name = (
        node_config.get("rule_name")
        or node_config.get("ruleName")
        or node_config.get("description")
    )
    if not name:
        return None
    try:
        rule = (
            db.query(DQRule)
            .filter(
                DQRule.workspace_id == workspace_id,
                DQRule.name == name,
            )
            .order_by(DQRule.is_active.desc(), DQRule.updated_at.desc())
            .first()
        )
        if rule is not None:
            return rule.id
    except Exception as exc:
        logger.warning(
            "F11 rule resolution failed for workspace=%s name=%s exc=%s",
            workspace_id,
            name,
            exc,
        )
    return None


def _resolve_dataset_id_fallback(
    db: Session,
    workspace_id: UUID,
    flow_definition: dict | None,
    check_node_id: str,
    node_config: dict,
) -> UUID | None:
    """F11 — best-effort dataset resolution:

    1. Walk ``flow_definition.connections`` to the source node feeding this
       check; read its ``config.dataset_id`` (already a UUID string).
    2. If still missing, look the dataset up by name against
       ``control.datasets`` for the current workspace, matching either
       ``physical_identifier`` or ``dataset_name`` against the check node's
       ``dataset_name`` / source node's ``name`` config.
    """
    if not flow_definition:
        return None

    nodes = {n.get("id"): n for n in flow_definition.get("nodes", [])}
    connections = flow_definition.get("connections", []) or []

    # Step 1 — find direct predecessor source node
    source_node = None
    for c in connections:
        target = c.get("to") or c.get("target") or c.get("targetNode")
        source = c.get("from") or c.get("source") or c.get("sourceNode")
        if target == check_node_id and source in nodes:
            cand = nodes[source]
            if cand.get("type") == "source":
                source_node = cand
                break

    candidate_name: str | None = None
    if source_node is not None:
        s_cfg = source_node.get("config", {}) or {}
        ds_id_raw = s_cfg.get("dataset_id")
        if ds_id_raw:
            try:
                return UUID(str(ds_id_raw))
            except Exception:
                pass
        candidate_name = s_cfg.get("name") or s_cfg.get("dataset_name")

    if not candidate_name:
        candidate_name = (
            node_config.get("dataset_name")
            or node_config.get("datasetName")
            or node_config.get("table")
        )

    if not candidate_name:
        return None

    try:
        from sqlalchemy import text as _sql_text

        row = db.execute(
            _sql_text(
                "SELECT dataset_id FROM control.datasets "
                "WHERE workspace_id = CAST(:ws AS UUID) "
                "  AND (lower(physical_identifier) = lower(:n) "
                "       OR lower(dataset_name) = lower(:n)) "
                "LIMIT 1"
            ),
            {"ws": str(workspace_id), "n": candidate_name},
        ).fetchone()
        if row is not None:
            return row[0]
    except Exception as exc:
        logger.warning(
            "F11 dataset resolution failed for workspace=%s name=%s exc=%s",
            workspace_id,
            candidate_name,
            exc,
        )
    return None


def _compute_due_at(opened_at, severity: str, sla_policy):
    """Compute ``due_at`` from the workspace SLA policy per TDD §5.3 step 9.

    Returns None when ``sla_policy`` is None, ``opened_at`` is None, or
    the severity's SLA hours field is None (e.g. informational_hours=None).
    """
    if sla_policy is None or opened_at is None:
        return None
    hours_map = {
        "critical": sla_policy.critical_hours,
        "major": sla_policy.major_hours,
        "minor": sla_policy.minor_hours,
        "informational": sla_policy.informational_hours,
    }
    hours = hours_map.get(severity)
    if hours is None:
        return None
    return opened_at + timedelta(hours=hours)
