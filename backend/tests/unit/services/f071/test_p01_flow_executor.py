"""
F071 P01 — Unit tests: FlowExecutor core logic

Tests _aggregate_results, _create_node_result, cancel_execution,
and execute_flow (validation failure, success, exception, reuse record).
All DB/validator/handler interactions mocked.

P01-01 .. P01-15  (15 tests)
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from app.schemas.flow import ExecutionStatus, NodeStatus, NodeType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


def _mock_node_result(status: str = "completed", node_type: str = "check", result_data=None):
    """Build a mock FlowNodeResult."""
    r = MagicMock()
    r.status = status
    r.node_type = node_type
    r.result_data = result_data
    return r


def _new_executor():
    """Create FlowExecutor with mocked sub-components."""
    with (
        patch("app.services.flows.executor.FlowValidator") as MockVal,
        patch("app.services.flows.executor.SourceNodeHandler"),
        patch("app.services.flows.executor.CheckNodeHandler"),
    ):
        from app.services.flows.executor import FlowExecutor

        ex = FlowExecutor()
        ex.validator = MockVal.return_value
    return ex


def _mock_flow(flow_def: dict | None = None):
    """Build a minimal mock DQFlow."""
    flow = MagicMock()
    flow.id = uuid.uuid4()
    flow.flow_definition = flow_def or {
        "nodes": [
            {"id": "src-1", "type": "source", "label": "Source", "config": {}},
            {
                "id": "chk-1",
                "type": "check",
                "label": "Check",
                "config": {},
                "checkType": "completeness",
            },
        ],
        "connections": [
            {"id": "c-1", "from": "src-1", "to": "chk-1"},
        ],
    }
    return flow


def _mock_execution(status: str = "running"):
    ex = MagicMock()
    ex.id = uuid.uuid4()
    ex.status = status
    ex.started_at = datetime.utcnow()
    ex.completed_at = None
    ex.duration_seconds = None
    ex.execution_config = {}
    ex.nodes_executed = 0
    ex.nodes_passed = 0
    ex.nodes_failed = 0
    ex.nodes_skipped = 0
    ex.result_summary = None
    ex.error_message = None
    ex.error_details = None
    return ex


# ===================================================================
# INIT
# ===================================================================
class TestFlowExecutorInit:
    def test_registers_source_and_check_handlers(self):
        """P01-01"""
        executor = _new_executor()
        assert NodeType.SOURCE in executor.node_handlers
        assert NodeType.CHECK in executor.node_handlers


# ===================================================================
# AGGREGATE RESULTS
# ===================================================================
class TestAggregateResults:
    def test_all_passed(self):
        """P01-02"""
        executor = _new_executor()
        results = {
            "n1": _mock_node_result("completed"),
            "n2": _mock_node_result("completed"),
            "n3": _mock_node_result("completed"),
        }
        summary = executor._aggregate_results(results)
        assert summary["all_passed"] is True
        assert summary["nodes_failed"] == 0
        assert summary["nodes_executed"] == 3

    def test_some_failed(self):
        """P01-03"""
        executor = _new_executor()
        results = {
            "n1": _mock_node_result("completed"),
            "n2": _mock_node_result("completed"),
            "n3": _mock_node_result("failed"),
        }
        summary = executor._aggregate_results(results)
        assert summary["all_passed"] is False
        assert summary["nodes_failed"] == 1
        assert summary["nodes_passed"] == 2

    def test_skipped_counted(self):
        """P01-04"""
        executor = _new_executor()
        results = {
            "n1": _mock_node_result("completed"),
            "n2": _mock_node_result("skipped"),
        }
        summary = executor._aggregate_results(results)
        assert summary["nodes_skipped"] == 1

    def test_check_rows_aggregated(self):
        """P01-05"""
        executor = _new_executor()
        results = {
            "n1": _mock_node_result(
                "completed", "check", {"rows_scanned": 100, "violation_count": 5}
            ),
            "n2": _mock_node_result(
                "completed", "check", {"rows_scanned": 200, "violation_count": 10}
            ),
        }
        summary = executor._aggregate_results(results)
        assert summary["summary"]["total_rows_scanned"] == 300
        assert summary["summary"]["total_violations"] == 15

    def test_empty_results(self):
        """P01-06"""
        executor = _new_executor()
        summary = executor._aggregate_results({})
        assert summary["nodes_executed"] == 0
        assert summary["summary"]["success_rate"] == 0


# ===================================================================
# CREATE NODE RESULT
# ===================================================================
class TestCreateNodeResult:
    def test_creates_record_with_correct_fields(self):
        """P01-07"""
        executor = _new_executor()
        db = _mock_db()

        with patch("app.services.flows.executor.FlowNodeResult") as MockFNR:
            mock_inst = MagicMock()
            MockFNR.return_value = mock_inst

            executor._create_node_result(
                db, uuid.uuid4(), "node-1", "source", NodeStatus.COMPLETED, 0
            )

        MockFNR.assert_called_once()
        kwargs = MockFNR.call_args[1]
        assert kwargs["node_id"] == "node-1"
        assert kwargs["node_type"] == "source"
        assert kwargs["status"] == "completed"
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_error_message_stored(self):
        """P01-08"""
        executor = _new_executor()
        db = _mock_db()

        with patch("app.services.flows.executor.FlowNodeResult") as MockFNR:
            mock_inst = MagicMock()
            MockFNR.return_value = mock_inst

            executor._create_node_result(
                db, uuid.uuid4(), "n1", "check", NodeStatus.FAILED, 0, error_message="boom"
            )

        kwargs = MockFNR.call_args[1]
        assert kwargs["error_message"] == "boom"


# ===================================================================
# CANCEL EXECUTION
# ===================================================================
class TestCancelExecution:
    @pytest.mark.asyncio
    async def test_cancel_running_succeeds(self):
        """P01-09"""
        executor = _new_executor()
        db = _mock_db()
        ex = _mock_execution("running")
        db.query.return_value.filter.return_value.first.return_value = ex

        result = await executor.cancel_execution(db, ex.id)
        assert result is True
        assert ex.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_non_running_fails(self):
        """P01-10"""
        executor = _new_executor()
        db = _mock_db()
        ex = _mock_execution("completed")
        db.query.return_value.filter.return_value.first.return_value = ex

        result = await executor.cancel_execution(db, ex.id)
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_not_found_fails(self):
        """P01-11"""
        executor = _new_executor()
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        result = await executor.cancel_execution(db, uuid.uuid4())
        assert result is False


# ===================================================================
# EXECUTE FLOW
# ===================================================================
class TestExecuteFlow:
    @pytest.mark.asyncio
    async def test_validation_failure_returns_failed(self):
        """P01-12"""
        executor = _new_executor()
        db = _mock_db()
        flow = _mock_flow()

        # Make validator return invalid
        from app.schemas.flow import FlowValidationResponse
        from app.schemas.flow import ValidationError as VE

        executor.validator.validate_flow.return_value = FlowValidationResponse(
            is_valid=False,
            errors=[VE(type="test", message="bad flow")],
            node_count=2,
            connection_count=1,
            has_source=True,
            has_checks=True,
            has_circular_dependencies=False,
        )

        with patch("app.services.flows.executor.FlowExecution") as MockExec:
            mock_ex = _mock_execution("failed")
            MockExec.return_value = mock_ex

            result = await executor.execute_flow(db, flow, uuid.uuid4(), uuid.uuid4())

        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_successful_flow_completes(self):
        """P01-13"""
        executor = _new_executor()
        db = _mock_db()
        flow = _mock_flow()

        # Valid flow
        from app.schemas.flow import FlowValidationResponse

        executor.validator.validate_flow.return_value = FlowValidationResponse(
            is_valid=True,
            errors=[],
            node_count=2,
            connection_count=1,
            has_source=True,
            has_checks=True,
            has_circular_dependencies=False,
        )
        executor.validator.get_execution_levels.return_value = [["src-1"], ["chk-1"]]

        # Mock the parallel execution
        async def fake_parallel(*args, **kwargs):
            return {
                "src-1": _mock_node_result("completed", "source"),
                "chk-1": _mock_node_result("completed", "check"),
            }

        executor._execute_nodes_parallel = fake_parallel

        with patch("app.services.flows.executor.FlowExecution") as MockExec:
            mock_ex = _mock_execution("running")
            MockExec.return_value = mock_ex

            result = await executor.execute_flow(db, flow, uuid.uuid4(), uuid.uuid4())

        assert result.status == "completed"
        assert result.nodes_executed == 2

    @pytest.mark.asyncio
    async def test_exception_marks_failed(self):
        """P01-14"""
        executor = _new_executor()
        db = _mock_db()
        flow = _mock_flow()

        from app.schemas.flow import FlowValidationResponse

        executor.validator.validate_flow.return_value = FlowValidationResponse(
            is_valid=True,
            errors=[],
            node_count=2,
            connection_count=1,
            has_source=True,
            has_checks=True,
            has_circular_dependencies=False,
        )
        executor.validator.get_execution_levels.return_value = [["src-1"], ["chk-1"]]

        async def fail_parallel(*args, **kwargs):
            raise RuntimeError("parallel boom")

        executor._execute_nodes_parallel = fail_parallel

        with patch("app.services.flows.executor.FlowExecution") as MockExec:
            mock_ex = _mock_execution("running")
            MockExec.return_value = mock_ex
            # The exception handler re-fetches the execution from DB after rollback
            db.query.return_value.filter.return_value.first.return_value = mock_ex

            with pytest.raises(RuntimeError, match="parallel boom"):
                await executor.execute_flow(db, flow, uuid.uuid4(), uuid.uuid4())

        assert mock_ex.status == "failed"
        assert "parallel boom" in (mock_ex.error_message or "")

    @pytest.mark.asyncio
    async def test_uses_existing_execution_record(self):
        """P01-15"""
        executor = _new_executor()
        db = _mock_db()
        flow = _mock_flow()

        from app.schemas.flow import FlowValidationResponse

        executor.validator.validate_flow.return_value = FlowValidationResponse(
            is_valid=True,
            errors=[],
            node_count=2,
            connection_count=1,
            has_source=True,
            has_checks=True,
            has_circular_dependencies=False,
        )
        executor.validator.get_execution_levels.return_value = [["src-1"], ["chk-1"]]

        async def fake_parallel(*args, **kwargs):
            return {
                "src-1": _mock_node_result("completed", "source"),
                "chk-1": _mock_node_result("completed", "check"),
            }

        executor._execute_nodes_parallel = fake_parallel

        existing_exec = _mock_execution("pending")
        result = await executor.execute_flow(
            db, flow, uuid.uuid4(), uuid.uuid4(), execution_record=existing_exec
        )

        # Should reuse, not create new
        assert result is existing_exec
        assert result.status == "completed"
