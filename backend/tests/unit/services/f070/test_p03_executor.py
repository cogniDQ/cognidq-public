"""
F070 P03 — Unit tests: RuleExecutor lifecycle, parsing, violations, thresholds, cancel

All DB sessions and connector calls are mocked.

P03-01 .. P03-21  (21 tests)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from app.schemas.rule import ExecutionStatus, ExecutionType
from app.services.rules.executor import RuleExecutor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _make_rule(
    dimension: str = "completeness",
    ds_type: str = "postgresql",
    threshold_config: dict | None = None,
    target_columns: list | None = None,
):
    """
    Build a lightweight mock DQRule that satisfies RuleExecutor's attribute
    access without importing the real ORM model.
    """
    rule = MagicMock()
    rule.id = uuid.uuid4()
    rule.canonical_rule = {"dimension": dimension, "severity": "major"}
    rule.compiled_sql = "SELECT COUNT(*) as total_rows FROM t"
    rule.compiled_postgres = "SELECT COUNT(*) as total_rows FROM t"
    rule.compiled_mysql = None
    rule.compiled_snowflake = None
    rule.threshold_config = threshold_config
    rule.target_columns = target_columns

    # data_source sub-object
    ds = MagicMock()
    ds.type = ds_type
    ds.connection_config = {"host": "localhost"}
    rule.data_source = ds
    return rule


def _make_execution(**overrides):
    """Build a mock RuleExecution."""
    ex = MagicMock()
    ex.id = uuid.uuid4()
    ex.status = ExecutionStatus.PENDING.value
    ex.started_at = None
    ex.completed_at = None
    ex.duration_seconds = None
    ex.rows_scanned = 0
    ex.rows_passed = 0
    ex.rows_failed = 0
    ex.pass_rate = Decimal("0.00")
    ex.error_message = None
    ex.error_details = None
    ex.result_details = None
    for k, v in overrides.items():
        setattr(ex, k, v)
    return ex


def _mock_db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


def _new_executor():
    """
    Return an RuleExecutor with its ConnectionManager mocked out.
    """
    with patch("app.services.rules.executor.ConnectionManager"):
        ex = RuleExecutor()
    # get_connector is awaited; replace with AsyncMock
    ex.connection_manager.get_connector = AsyncMock()
    return ex


def _setup_connector(executor, return_value=None, side_effect=None):
    """Wire up an async connector mock on *executor*."""
    connector = MagicMock()
    if side_effect is not None:
        connector.execute_query = AsyncMock(side_effect=side_effect)
    else:
        connector.execute_query = AsyncMock(return_value=return_value or [])
    executor.connection_manager.get_connector = AsyncMock(return_value=connector)
    return connector


# ===================================================================
# LIFECYCLE  (P03-01 .. P03-04)
# ===================================================================
class TestExecuteRuleLifecycle:
    @pytest.mark.asyncio
    async def test_success_transitions_pending_running_completed(self):
        """P03-01"""
        executor = _new_executor()
        rule = _make_rule(dimension="completeness")

        _setup_connector(
            executor, return_value=[{"total_rows": 100, "non_null_rows": 95, "null_rows": 5}]
        )

        db = _mock_db()

        # Capture the RuleExecution created inside execute_rule
        captured = {}

        original_add = db.add

        def _capture_add(obj):
            # First add call is the RuleExecution object
            if not captured:
                captured["execution"] = obj
            original_add(obj)

        db.add = _capture_add

        with patch("app.services.rules.executor.RuleExecution") as MockExec:
            ex_inst = _make_execution()
            MockExec.return_value = ex_inst

            result = await executor.execute_rule(db, rule, ExecutionType.MANUAL)

        assert result.status == ExecutionStatus.COMPLETED.value
        assert result.started_at is not None
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_failure_transitions_to_failed(self):
        """P03-02"""
        executor = _new_executor()
        rule = _make_rule()

        _setup_connector(executor, side_effect=RuntimeError("DB exploded"))

        db = _mock_db()

        with patch("app.services.rules.executor.RuleExecution") as MockExec:
            ex_inst = _make_execution()
            MockExec.return_value = ex_inst

            result = await executor.execute_rule(db, rule, ExecutionType.MANUAL)

        assert result.status == ExecutionStatus.FAILED.value
        assert result.error_message is not None
        assert "DB exploded" in result.error_message

    @pytest.mark.asyncio
    async def test_duration_seconds_calculated(self):
        """P03-03"""
        executor = _new_executor()
        rule = _make_rule()

        _setup_connector(
            executor, return_value=[{"total_rows": 10, "non_null_rows": 10, "null_rows": 0}]
        )

        db = _mock_db()

        with patch("app.services.rules.executor.RuleExecution") as MockExec:
            ex_inst = _make_execution()
            MockExec.return_value = ex_inst

            result = await executor.execute_rule(db, rule, ExecutionType.MANUAL)

        assert result.duration_seconds is not None

    @pytest.mark.asyncio
    async def test_no_data_source_raises(self):
        """P03-04"""
        executor = _new_executor()
        rule = _make_rule()
        rule.data_source = None  # No data source

        db = _mock_db()

        with patch("app.services.rules.executor.RuleExecution") as MockExec:
            ex_inst = _make_execution()
            MockExec.return_value = ex_inst

            result = await executor.execute_rule(db, rule, ExecutionType.MANUAL)

        # Should mark failed with error
        assert result.status == ExecutionStatus.FAILED.value


# ===================================================================
# RESULT PARSING  (P03-05 .. P03-10)
# ===================================================================
class TestResultParsing:
    @pytest.mark.asyncio
    async def test_completeness_maps_non_null_rows(self):
        """P03-05"""
        executor = _new_executor()
        rule = _make_rule(dimension="completeness")

        _setup_connector(
            executor, return_value=[{"total_rows": 100, "non_null_rows": 90, "null_rows": 10}]
        )

        db = _mock_db()

        with patch("app.services.rules.executor.RuleExecution") as MockExec:
            ex_inst = _make_execution()
            MockExec.return_value = ex_inst

            result = await executor.execute_rule(db, rule, ExecutionType.MANUAL)

        assert result.rows_passed == 90
        assert result.rows_failed == 10

    @pytest.mark.asyncio
    async def test_validity_maps_valid_rows(self):
        """P03-06"""
        executor = _new_executor()
        rule = _make_rule(dimension="validity")

        _setup_connector(
            executor, return_value=[{"total_rows": 200, "valid_rows": 180, "invalid_rows": 20}]
        )

        db = _mock_db()

        with patch("app.services.rules.executor.RuleExecution") as MockExec:
            ex_inst = _make_execution()
            MockExec.return_value = ex_inst

            result = await executor.execute_rule(db, rule, ExecutionType.MANUAL)

        assert result.rows_passed == 180
        assert result.rows_failed == 20

    @pytest.mark.asyncio
    async def test_uniqueness_maps_duplicate_rows(self):
        """P03-07"""
        executor = _new_executor()
        rule = _make_rule(dimension="uniqueness")

        _setup_connector(
            executor,
            return_value=[
                {
                    "total_rows": 300,
                    "duplicate_rows": 15,
                    "unique_values": 285,
                    "uniqueness_rate": 95.00,
                }
            ],
        )

        db = _mock_db()

        with patch("app.services.rules.executor.RuleExecution") as MockExec:
            ex_inst = _make_execution()
            MockExec.return_value = ex_inst

            result = await executor.execute_rule(db, rule, ExecutionType.MANUAL)

        assert result.rows_failed == 15
        assert result.rows_passed == 285

    @pytest.mark.asyncio
    async def test_generic_dimension_fallback(self):
        """P03-08"""
        executor = _new_executor()
        rule = _make_rule(dimension="reconciliation")

        _setup_connector(
            executor, return_value=[{"total_rows": 50, "passed_rows": 45, "failed_rows": 5}]
        )

        db = _mock_db()

        with patch("app.services.rules.executor.RuleExecution") as MockExec:
            ex_inst = _make_execution()
            MockExec.return_value = ex_inst

            result = await executor.execute_rule(db, rule, ExecutionType.MANUAL)

        assert result.rows_passed == 45
        assert result.rows_failed == 5

    @pytest.mark.asyncio
    async def test_pass_rate_calculated(self):
        """P03-09"""
        executor = _new_executor()
        rule = _make_rule()

        _setup_connector(
            executor, return_value=[{"total_rows": 200, "non_null_rows": 180, "null_rows": 20}]
        )

        db = _mock_db()

        with patch("app.services.rules.executor.RuleExecution") as MockExec:
            ex_inst = _make_execution()
            MockExec.return_value = ex_inst

            result = await executor.execute_rule(db, rule, ExecutionType.MANUAL)

        assert result.pass_rate == Decimal("90.00")

    @pytest.mark.asyncio
    async def test_zero_rows_scanned_pass_rate_zero(self):
        """P03-10"""
        executor = _new_executor()
        rule = _make_rule()

        _setup_connector(
            executor, return_value=[{"total_rows": 0, "non_null_rows": 0, "null_rows": 0}]
        )

        db = _mock_db()

        with patch("app.services.rules.executor.RuleExecution") as MockExec:
            ex_inst = _make_execution()
            MockExec.return_value = ex_inst

            result = await executor.execute_rule(db, rule, ExecutionType.MANUAL)

        assert result.pass_rate == Decimal("0.00")


# ===================================================================
# VIOLATION STORAGE  (P03-11 .. P03-13)
# ===================================================================
class TestViolationStorage:
    @pytest.mark.asyncio
    async def test_violations_stored_up_to_limit(self):
        """P03-11: 1500 violations → only 1000 stored."""
        executor = _new_executor()
        rule = _make_rule()

        violations = [{"id": i, "col": f"v{i}"} for i in range(1500)]

        db = _mock_db()
        count = await executor._store_violations(
            db, uuid.uuid4(), violations, rule, sample_limit=1000
        )
        assert count == 1000

    @pytest.mark.asyncio
    async def test_few_violations_all_stored(self):
        """P03-12"""
        executor = _new_executor()
        rule = _make_rule()

        violations = [{"id": i} for i in range(5)]

        db = _mock_db()
        count = await executor._store_violations(
            db, uuid.uuid4(), violations, rule, sample_limit=1000
        )
        assert count == 5

    @pytest.mark.asyncio
    async def test_violation_fields_populated(self):
        """P03-13: Each RuleViolation gets execution_id, severity, category."""
        executor = _new_executor()
        rule = _make_rule(dimension="validity")
        rule.canonical_rule["severity"] = "critical"

        violations = [{"amount": 999}]

        db = _mock_db()

        added_objects = []
        original_add = db.add

        def _capture(obj):
            added_objects.append(obj)
            original_add(obj)

        db.add = _capture

        with patch("app.services.rules.executor.RuleViolation") as MockViol:
            mock_inst = MagicMock()
            MockViol.return_value = mock_inst

            await executor._store_violations(db, uuid.uuid4(), violations, rule, sample_limit=1000)

        # RuleViolation was constructed with the right kwargs
        MockViol.assert_called_once()
        kwargs = MockViol.call_args[1]
        assert "execution_id" in kwargs
        assert kwargs["severity"] == "critical"
        assert kwargs["category"] == "validity"


# ===================================================================
# THRESHOLD CHECKS  (P03-14 .. P03-17)
# ===================================================================
class TestThresholdChecks:
    @pytest.mark.asyncio
    async def test_pass_rate_below_threshold_fails(self):
        """P03-14"""
        executor = _new_executor()
        execution = _make_execution(pass_rate=Decimal("80.00"), rows_failed=20)
        rule = _make_rule(threshold_config={"pass_threshold": 90})

        result = await executor._check_thresholds(execution, rule)
        assert result is False

    @pytest.mark.asyncio
    async def test_pass_rate_above_threshold_passes(self):
        """P03-15"""
        executor = _new_executor()
        execution = _make_execution(pass_rate=Decimal("95.00"), rows_failed=5)
        rule = _make_rule(threshold_config={"pass_threshold": 90})

        result = await executor._check_thresholds(execution, rule)
        assert result is True

    @pytest.mark.asyncio
    async def test_max_violations_exceeded_fails(self):
        """P03-16"""
        executor = _new_executor()
        execution = _make_execution(pass_rate=Decimal("80.00"), rows_failed=200)
        rule = _make_rule(threshold_config={"max_violations": 100})

        result = await executor._check_thresholds(execution, rule)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_thresholds_returns_true(self):
        """P03-17"""
        executor = _new_executor()
        execution = _make_execution(pass_rate=Decimal("50.00"), rows_failed=500)
        rule = _make_rule(threshold_config=None)

        result = await executor._check_thresholds(execution, rule)
        assert result is True


# ===================================================================
# CANCEL EXECUTION  (P03-18 .. P03-21)
# ===================================================================
class TestCancelExecution:
    @pytest.mark.asyncio
    async def test_cancel_pending_succeeds(self):
        """P03-18"""
        executor = _new_executor()
        db = _mock_db()

        ex = _make_execution(status=ExecutionStatus.PENDING.value, started_at=None)
        db.query.return_value.filter.return_value.first.return_value = ex

        result = await executor.cancel_execution(db, str(ex.id))
        assert result is True
        assert ex.status == ExecutionStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_cancel_running_succeeds(self):
        """P03-19"""
        executor = _new_executor()
        db = _mock_db()

        ex = _make_execution(
            status=ExecutionStatus.RUNNING.value,
            started_at=datetime.utcnow(),
        )
        db.query.return_value.filter.return_value.first.return_value = ex

        result = await executor.cancel_execution(db, str(ex.id))
        assert result is True
        assert ex.status == ExecutionStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_cancel_completed_fails(self):
        """P03-20"""
        executor = _new_executor()
        db = _mock_db()

        ex = _make_execution(status=ExecutionStatus.COMPLETED.value)
        db.query.return_value.filter.return_value.first.return_value = ex

        result = await executor.cancel_execution(db, str(ex.id))
        assert result is False
        assert ex.status == ExecutionStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_returns_false(self):
        """P03-21"""
        executor = _new_executor()
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        result = await executor.cancel_execution(db, str(uuid.uuid4()))
        assert result is False
