"""
Rule Execution Engine
Executes data quality rules against data sources and stores results.
"""

import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.rule import DQRule, RuleExecution, RuleViolation
from app.schemas.rule import ExecutionStatus, ExecutionType
from app.services.datasources.connection_manager import ConnectionManager
from app.services.rules.compiler import RuleCompiler

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    """Recursively coerce values into JSON-serializable primitives.

    PostgreSQL JSONB columns reject `date`, `datetime`, `Decimal`, `bytes`, and
    a few other Python types we routinely see in DB result rows. This keeps the
    rule executor able to persist violation samples without crashing on
    common column types.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            return bytes(value).decode("utf-8", errors="replace")
        except Exception:
            return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(v) for v in value]
    # Last-resort fallback: stringify unknown types (e.g. UUID).
    return str(value)


class RuleExecutor:
    """
    Executes data quality rules and manages execution lifecycle.
    """

    def __init__(self):
        self.compiler = RuleCompiler()
        self.connection_manager = ConnectionManager()

    async def execute_rule(
        self,
        db: Session,
        rule: DQRule,
        execution_type: ExecutionType,
        executed_by: str | None = None,
        parameters: dict[str, Any] = None,
        sample_only: bool = False,
        sample_size: int | None = None,
    ) -> RuleExecution:
        """
        Execute a data quality rule.

        Args:
            db: Database session
            rule: Rule to execute
            execution_type: Type of execution (manual, scheduled, etc.)
            executed_by: User ID who triggered execution
            parameters: Additional execution parameters
            sample_only: Whether to run on sample data only
            sample_size: Sample size if sample_only is True

        Returns:
            RuleExecution record
        """
        parameters = parameters or {}

        # Create execution record
        execution = RuleExecution(
            rule_id=rule.id,
            execution_type=execution_type.value,
            status=ExecutionStatus.PENDING.value,
            executed_by=executed_by,
            execution_params=parameters,
            rows_scanned=0,
            rows_passed=0,
            rows_failed=0,
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        try:
            # Update status to running
            execution.status = ExecutionStatus.RUNNING.value
            execution.started_at = datetime.utcnow()
            db.commit()

            # Execute based on data source type
            if rule.data_source:
                # SQL-based execution
                result = await self._execute_sql_rule(
                    rule, execution, sample_only=sample_only, sample_size=sample_size
                )
            else:
                raise ValueError("Rule must have a data source configured")

            # Update execution with results (coerce to int — adapters may return Decimal)
            execution.rows_scanned = int(result.get("rows_scanned", 0) or 0)
            execution.rows_passed = int(result.get("rows_passed", 0) or 0)
            execution.rows_failed = int(result.get("rows_failed", 0) or 0)

            # Calculate pass rate
            if execution.rows_scanned > 0:
                execution.pass_rate = Decimal(
                    str(round(100.0 * execution.rows_passed / execution.rows_scanned, 2))
                )
            else:
                execution.pass_rate = Decimal("0.00")

            # Store violations (with sampling). Best-effort: a sampling failure
            # must not fail the whole execution — the counts are still valid.
            violations = result.get("violations", [])
            if violations:
                try:
                    await self._store_violations(
                        db, execution.id, violations, rule, sample_limit=1000
                    )
                except Exception as v_exc:  # noqa: BLE001
                    logger.warning(
                        "Could not store violation samples for execution %s: %s",
                        execution.id,
                        v_exc,
                    )
                    try:
                        db.rollback()
                    except Exception:
                        pass

            # Store detailed results
            statistics = result.get("statistics", {})
            statistics = (
                _json_safe(statistics)
                if isinstance(statistics, dict)
                else _json_safe({"value": statistics})
            )
            execution.result_details = {
                "total_rows": execution.rows_scanned,
                "passed": execution.rows_passed,
                "failed": execution.rows_failed,
                "pass_rate": float(execution.pass_rate),
                "violation_count": len(violations),
                # Include a sample of violation rows so the check_node can forward them
                # to SampleCaptureService for the "View faulty records" feature.
                # Apply _json_safe to handle Decimal/UUID/datetime values in row dicts.
                "violations": [
                    _json_safe(r) if isinstance(r, dict) else _json_safe({"value": r})
                    for r in violations[:100]
                ],
                "threshold_met": await self._check_thresholds(execution, rule),
                "statistics": statistics,
            }

            # Mark as completed
            execution.status = ExecutionStatus.COMPLETED.value
            execution.completed_at = datetime.utcnow()
            execution.duration_seconds = int(
                (execution.completed_at - execution.started_at).total_seconds()
            )

        except Exception as e:
            logger.error(f"Rule execution failed: {str(e)}", exc_info=True)

            # Mark as failed
            execution.status = ExecutionStatus.FAILED.value
            execution.completed_at = datetime.utcnow()
            execution.error_message = str(e)
            execution.error_details = {"error_type": type(e).__name__, "error_message": str(e)}

            if execution.started_at:
                execution.duration_seconds = int(
                    (execution.completed_at - execution.started_at).total_seconds()
                )

        db.commit()
        db.refresh(execution)

        # F6 — Auto-create Issue when a direct rule execution produces failures.
        # Best-effort: failure here must not affect the returned execution.
        try:
            if (
                execution.status == ExecutionStatus.COMPLETED.value
                and int(execution.rows_failed or 0) > 0
            ):
                from app.services.issues.issue_creation_service import IssueCreationService

                issue = IssueCreationService().create_from_rule_execution(
                    db=db, rule_execution_id=execution.id
                )
                if issue is not None:
                    db.commit()
        except Exception as f6_exc:  # noqa: BLE001
            logger.warning(
                "F6 auto-issue creation failed for execution %s: %s",
                execution.id,
                f6_exc,
            )
            try:
                db.rollback()
            except Exception:
                pass

        # F10 — Fire `rule_failed` / `execution_failed` alerts for direct
        # rule executions. Best-effort: never let alerting break the run.
        try:
            trigger_type: str | None = None
            if execution.status == ExecutionStatus.FAILED.value:
                trigger_type = "execution_failed"
            elif (
                execution.status == ExecutionStatus.COMPLETED.value
                and int(execution.rows_failed or 0) > 0
            ):
                trigger_type = "rule_failed"
            if trigger_type is not None:
                from app.services.alerts.alert_trigger_service import AlertTriggerService

                _n_fired = AlertTriggerService().trigger_for_workspace(
                    db,
                    workspace_id=rule.workspace_id,
                    trigger_type=trigger_type,
                    payload={
                        "title": rule.name,
                        "rule_id": str(rule.id),
                        "rule_name": rule.name,
                        "execution_id": str(execution.id),
                        "status": execution.status,
                        "rows_scanned": int(execution.rows_scanned or 0),
                        "rows_failed": int(execution.rows_failed or 0),
                        "rows_passed": int(execution.rows_passed or 0),
                        "pass_rate": float(execution.pass_rate)
                        if execution.pass_rate is not None
                        else None,
                        "severity": (rule.canonical_rule or {}).get("severity")
                        if isinstance(rule.canonical_rule, dict)
                        else None,
                        "error_message": execution.error_message,
                    },
                )
                if _n_fired:
                    db.commit()
                    logger.info(
                        "F10 alert dispatch fired %s event(s) for execution %s (trigger=%s)",
                        _n_fired,
                        execution.id,
                        trigger_type,
                    )
        except Exception as alert_exc:  # noqa: BLE001
            logger.warning(
                "F10 alert dispatch failed for execution %s: %s",
                execution.id,
                alert_exc,
            )
            try:
                db.rollback()
            except Exception:
                pass

        return execution

    async def _execute_sql_rule(
        self,
        rule: DQRule,
        execution: RuleExecution,
        sample_only: bool = False,
        sample_size: int | None = None,
    ) -> dict[str, Any]:
        """
        Execute SQL-based rule against a database.
        """
        # Get compiled SQL (use database-specific if available)
        ds_type = rule.data_source.type

        if ds_type == "postgresql" and rule.compiled_postgres:
            sql = rule.compiled_postgres
        elif ds_type == "mysql" and rule.compiled_mysql:
            sql = rule.compiled_mysql
        elif ds_type == "snowflake" and rule.compiled_snowflake:
            sql = rule.compiled_snowflake
        else:
            sql = rule.compiled_sql

        # F5 fix — the rule model does not persist the per-row `violation_sql`
        # the compiler emits, so we recompile from the canonical rule to recover
        # it. Without this, sample failing rows are never collected and the
        # "View faulty records" UI is always empty.
        violation_sql = self._compile_violation_sql(rule)

        if not sql:
            raise ValueError("No compiled SQL available for rule")

        # Add sampling if requested
        if sample_only and sample_size:
            sql = f"{sql} LIMIT {sample_size}"

        # Get database connection
        connector = await self.connection_manager.get_connector(
            rule.data_source.type, rule.data_source.connection_config
        )

        # Execute main rule query
        result_rows = await connector.execute_query(sql)

        if not result_rows:
            raise ValueError("Rule execution returned no results")

        result = result_rows[0]

        # Parse results based on rule dimension
        dimension = rule.canonical_rule.get("dimension")

        # Generic mapping of (passed_alias, failed_alias) per dimension. The
        # compiler emits dimension-specific SELECT aliases (e.g. accuracy →
        # accurate_rows/inaccurate_rows, timeliness → timely_rows/untimely_rows).
        # We try the dimension-specific names first, then fall back to a
        # broad set of generic aliases.
        _DIM_ALIASES = {
            "completeness": ("non_null_rows", "null_rows"),
            "validity": ("valid_rows", "invalid_rows"),
            "uniqueness": ("unique_rows", "duplicate_rows"),
            "conformity": ("conforming_rows", "non_conforming_rows"),
            "consistency": ("consistent_rows", "inconsistent_rows"),
            "accuracy": ("accurate_rows", "inaccurate_rows"),
            "timeliness": ("timely_rows", "untimely_rows"),
            "reconciliation": ("matched_rows", "unmatched_rows"),
        }
        # Universal fallback aliases, ordered most-to-least specific.
        _PASSED_FALLBACKS = (
            "passed_rows",
            "valid_rows",
            "non_null_rows",
            "conforming_rows",
            "consistent_rows",
            "accurate_rows",
            "timely_rows",
            "matched_rows",
            "verified_rows",
        )
        _FAILED_FALLBACKS = (
            "failed_rows",
            "invalid_rows",
            "null_rows",
            "nonconforming_rows",
            "non_conforming_rows",
            "inconsistent_rows",
            "inaccurate_rows",
            "untimely_rows",
            "unmatched_rows",
            "duplicate_rows",
            "violations",
            "violation_count",
        )

        rows_scanned = result.get("total_rows") or 0
        passed_alias, failed_alias = _DIM_ALIASES.get(dimension, (None, None))

        rows_passed = None
        rows_failed = None
        if passed_alias and passed_alias in result:
            rows_passed = result.get(passed_alias)
        if failed_alias and failed_alias in result:
            rows_failed = result.get(failed_alias)

        if rows_passed is None:
            for k in _PASSED_FALLBACKS:
                if k in result and result.get(k) is not None:
                    rows_passed = result.get(k)
                    break
        if rows_failed is None:
            for k in _FAILED_FALLBACKS:
                if k in result and result.get(k) is not None:
                    rows_failed = result.get(k)
                    break

        # Reconciliation record_count emits source_count/target_count; treat
        # the absolute difference as failed and the smaller side as passed.
        if (
            dimension == "reconciliation"
            and rows_failed is None
            and "source_count" in result
            and "target_count" in result
        ):
            try:
                src = int(result.get("source_count") or 0)
                tgt = int(result.get("target_count") or 0)
            except Exception:
                src, tgt = 0, 0
            # If the query also reports missing/extra columns (one_to_one /
            # missing_extra subtypes), use those for a row-level breakdown.
            miss = result.get("missing_in_target")
            extra = result.get("extra_in_target")
            if miss is not None or extra is not None:
                miss_i = int(miss or 0)
                extra_i = int(extra or 0)
                rows_scanned = max(src, tgt)
                rows_failed = miss_i + extra_i
                rows_passed = max(rows_scanned - rows_failed, 0)
            else:
                rows_scanned = max(src, tgt)
                rows_failed = abs(src - tgt)
                rows_passed = min(src, tgt)

        # Reconciliation aggregate emits source_agg/target_agg.
        if (
            dimension == "reconciliation"
            and rows_failed is None
            and "source_agg" in result
            and "target_agg" in result
        ):
            try:
                src_a = float(result.get("source_agg") or 0)
                tgt_a = float(result.get("target_agg") or 0)
            except Exception:
                src_a, tgt_a = 0.0, 0.0
            rows_scanned = 1
            rows_failed = 0 if abs(src_a - tgt_a) <= 1e-9 else 1
            rows_passed = 1 - rows_failed

        # Reconciliation field_level emits field_match_count / field_mismatch_count.
        if (
            dimension == "reconciliation"
            and rows_failed is None
            and "field_mismatch_count" in result
        ):
            rows_failed = int(result.get("field_mismatch_count") or 0)
            rows_passed = int(result.get("field_match_count") or 0)
            if not rows_scanned:
                rows_scanned = int(result.get("matched_count") or (rows_passed + rows_failed))

        # Reconciliation tolerance emits within_tolerance / outside_tolerance.
        if dimension == "reconciliation" and rows_failed is None and "outside_tolerance" in result:
            rows_failed = int(result.get("outside_tolerance") or 0)
            rows_passed = int(result.get("within_tolerance") or 0)
            if not rows_scanned:
                rows_scanned = int(result.get("matched_count") or (rows_passed + rows_failed))

        rows_passed = int(rows_passed or 0)
        rows_failed = int(rows_failed or 0)
        try:
            rows_scanned = int(rows_scanned or 0)
        except Exception:
            rows_scanned = 0

        # Uniqueness: the compiled SQL emits total_rows/duplicate_rows/uniqueness_rate
        # but no explicit unique_rows column, so rows_passed stays 0.
        # Derive unique_rows = total_rows - duplicate_rows when rows_passed is 0
        # and the SQL result contains a uniqueness_rate or duplicate_rows column.
        if dimension == "uniqueness" and rows_passed == 0 and rows_scanned > 0:
            if "uniqueness_rate" in result:
                # Use pre-computed rate directly from the SQL
                try:
                    uniqueness_rate = float(result["uniqueness_rate"])
                    rows_passed = int(round(rows_scanned * uniqueness_rate / 100))
                    rows_failed = rows_scanned - rows_passed
                except Exception:
                    pass
            elif "duplicate_rows" in result:
                rows_failed = int(result.get("duplicate_rows") or 0)
                rows_passed = rows_scanned - rows_failed

        # Derive scanned if missing
        if not rows_scanned:
            rows_scanned = rows_passed + rows_failed

        # Get violations (limit to prevent overflow)
        violations = []
        if violation_sql and rows_failed > 0:
            violation_limit = 1000  # Max violations to fetch
            violation_rows = await connector.execute_query(
                f"{violation_sql} LIMIT {violation_limit}"
            )
            violations = violation_rows or []

        return {
            "rows_scanned": rows_scanned,
            "rows_passed": rows_passed,
            "rows_failed": rows_failed,
            "violations": violations,
            "statistics": result,
        }

    def _get_violation_sql(self, compiled_sql: str) -> str | None:
        """
        Extract or generate violation SQL from compiled SQL.
        In practice, the compiler should provide this separately.
        """
        # This is a placeholder - the compiler already provides violation_sql
        # In the actual implementation, we'd use the violation_sql from compiler
        return None

    def _compile_violation_sql(self, rule: DQRule) -> str | None:
        """Recompile the rule from its canonical form to recover ``violation_sql``.

        The DQRule table stores aggregate compiled SQL per dialect but not the
        per-row violation SQL. Recompiling here is cheap and avoids a schema
        migration. Returns None on any failure so the executor degrades to
        "counts only" rather than crashing.
        """
        try:
            canonical = rule.canonical_rule
            if not canonical:
                return None
            target_schema = rule.target_schema or None
            target_table = rule.target_table or None
            if not target_table:
                entity = canonical.get("entity") or ""
                if "." in entity:
                    target_schema = target_schema or entity.split(".", 1)[0]
                    target_table = entity.split(".", 1)[1].split(".", 1)[0]
                else:
                    target_table = entity or None
            compiled = self.compiler.compile_rule(
                canonical_rule=canonical,
                target_schema=target_schema,
                target_table=target_table,
                target_columns=list(rule.target_columns) if rule.target_columns else None,
            )
            if isinstance(compiled, dict):
                return compiled.get("violation_sql") or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not recompile violation_sql for rule %s: %s", rule.id, exc)
        return None

    async def _store_violations(
        self,
        db: Session,
        execution_id: str,
        violations: list[dict[str, Any]],
        rule: DQRule,
        sample_limit: int = 1000,
    ) -> int:
        """
        Store violations with sampling to prevent database overflow.
        """
        canonical_rule = rule.canonical_rule
        severity = canonical_rule.get("severity", "major")
        dimension = canonical_rule.get("dimension")

        stored_count = 0

        # Sample violations if too many
        if len(violations) > sample_limit:
            # Store first N as samples
            sampled_violations = violations[:sample_limit]
            is_sample = True
        else:
            sampled_violations = violations
            is_sample = len(violations) > sample_limit

        # Create violation records
        for idx, violation_row in enumerate(sampled_violations):
            # Try to extract row identifier (primary key or unique column)
            row_identifier = None
            if rule.target_columns:
                # Use first target column as identifier if available
                col = rule.target_columns[0]
                row_identifier = str(violation_row.get(col, ""))

            # F5 fix — sanitize before INSERT: violation_details is JSONB and
            # raw `date`/`datetime`/`Decimal`/`bytes` values raise
            # "Object of type X is not JSON serializable".
            safe_details = (
                _json_safe(violation_row)
                if isinstance(violation_row, dict)
                else _json_safe({"value": violation_row})
            )

            violation = RuleViolation(
                execution_id=execution_id,
                row_identifier=row_identifier,
                row_number=idx + 1,
                violation_details=safe_details,
                severity=severity,
                category=dimension,
                is_sample=is_sample,
            )
            db.add(violation)
            stored_count += 1

        db.commit()
        return stored_count

    async def _check_thresholds(self, execution: RuleExecution, rule: DQRule) -> bool:
        """
        Check if execution meets configured thresholds.
        """
        if not rule.threshold_config:
            return True  # No thresholds configured

        pass_threshold = rule.threshold_config.get("pass_threshold")
        max_violations = rule.threshold_config.get("max_violations")

        threshold_met = True

        if pass_threshold is not None:
            if execution.pass_rate < Decimal(str(pass_threshold)):
                threshold_met = False

        if max_violations is not None:
            if execution.rows_failed > max_violations:
                threshold_met = False

        return threshold_met

    async def cancel_execution(self, db: Session, execution_id: str) -> bool:
        """
        Cancel a running execution.
        """
        execution = db.query(RuleExecution).filter(RuleExecution.id == execution_id).first()

        if not execution:
            return False

        if execution.status in [ExecutionStatus.PENDING.value, ExecutionStatus.RUNNING.value]:
            execution.status = ExecutionStatus.CANCELLED.value
            execution.completed_at = datetime.utcnow()

            if execution.started_at:
                execution.duration_seconds = int(
                    (execution.completed_at - execution.started_at).total_seconds()
                )

            db.commit()
            return True

        return False
