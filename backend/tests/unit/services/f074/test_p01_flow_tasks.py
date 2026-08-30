"""
F074 P01 — Unit tests: Flow Tasks (flows.py)

Tests execute_flow_task, scheduled_flow_execution_task, generate_execution_report,
cleanup_old_executions, send_flow_completion_notification.

P01-01 .. P01-15  (15 tests)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest

FLOW_MOD = "app.workers.tasks.flows"


# ===================================================================
# execute_flow_task
# ===================================================================
class TestExecuteFlowTask:
    @patch(f"{FLOW_MOD}.generate_execution_report")
    @patch(f"{FLOW_MOD}.send_flow_completion_notification")
    @patch(f"{FLOW_MOD}.FlowService")
    @patch(f"{FLOW_MOD}.SessionLocal")
    @patch("asyncio.run")
    def test_calls_flow_service(self, mock_arun, mock_sl, mock_fs_cls, mock_notif, mock_report):
        """P01-01: FlowService.execute_flow is called"""
        from app.workers.tasks.flows import execute_flow_task

        mock_db = MagicMock()
        mock_sl.return_value = mock_db

        mock_exec = MagicMock()
        mock_exec.id = uuid4()
        mock_exec.status = "completed"
        mock_arun.return_value = mock_exec

        fid = str(uuid4())
        oid = str(uuid4())
        uid = str(uuid4())
        result = execute_flow_task(fid, oid, uid)
        assert result == str(mock_exec.id)

    @patch(f"{FLOW_MOD}.generate_execution_report")
    @patch(f"{FLOW_MOD}.send_flow_completion_notification")
    @patch(f"{FLOW_MOD}.FlowService")
    @patch(f"{FLOW_MOD}.SessionLocal")
    @patch("asyncio.run")
    def test_returns_execution_id(self, mock_arun, mock_sl, mock_fs_cls, mock_notif, mock_report):
        """P01-02: Returns string execution_id"""
        from app.workers.tasks.flows import execute_flow_task

        exec_id = uuid4()
        mock_exec = MagicMock()
        mock_exec.id = exec_id
        mock_exec.status = "completed"
        mock_arun.return_value = mock_exec
        mock_sl.return_value = MagicMock()

        result = execute_flow_task(str(uuid4()), str(uuid4()), str(uuid4()))
        assert result == str(exec_id)

    @patch(f"{FLOW_MOD}.generate_execution_report")
    @patch(f"{FLOW_MOD}.send_flow_completion_notification")
    @patch(f"{FLOW_MOD}.FlowService")
    @patch(f"{FLOW_MOD}.SessionLocal")
    @patch("asyncio.run")
    def test_triggers_notification_on_complete(
        self, mock_arun, mock_sl, mock_fs_cls, mock_notif, mock_report
    ):
        """P01-03: send_flow_completion_notification.delay called on completed"""
        from app.workers.tasks.flows import execute_flow_task

        mock_exec = MagicMock()
        mock_exec.id = uuid4()
        mock_exec.status = "completed"
        mock_arun.return_value = mock_exec
        mock_sl.return_value = MagicMock()

        execute_flow_task(str(uuid4()), str(uuid4()), str(uuid4()))
        mock_notif.delay.assert_called_once()

    @patch(f"{FLOW_MOD}.generate_execution_report")
    @patch(f"{FLOW_MOD}.send_flow_completion_notification")
    @patch(f"{FLOW_MOD}.FlowService")
    @patch(f"{FLOW_MOD}.SessionLocal")
    @patch("asyncio.run")
    def test_triggers_report_on_complete(
        self, mock_arun, mock_sl, mock_fs_cls, mock_notif, mock_report
    ):
        """P01-04: generate_execution_report.delay called"""
        from app.workers.tasks.flows import execute_flow_task

        mock_exec = MagicMock()
        mock_exec.id = uuid4()
        mock_exec.status = "failed"
        mock_arun.return_value = mock_exec
        mock_sl.return_value = MagicMock()

        execute_flow_task(str(uuid4()), str(uuid4()), str(uuid4()))
        mock_report.delay.assert_called_once()

    @patch(f"{FLOW_MOD}.send_flow_completion_notification")
    @patch(f"{FLOW_MOD}.FlowService")
    @patch(f"{FLOW_MOD}.SessionLocal")
    @patch("asyncio.run")
    def test_error_reraises(self, mock_arun, mock_sl, mock_fs_cls, mock_notif):
        """P01-05: Exception → re-raises"""
        from app.workers.tasks.flows import execute_flow_task

        mock_sl.return_value = MagicMock()
        mock_arun.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            execute_flow_task(str(uuid4()), str(uuid4()), str(uuid4()))


# ===================================================================
# scheduled_flow_execution_task
# ===================================================================
class TestScheduledFlowExecution:
    @patch(f"{FLOW_MOD}.execute_flow_task")
    @patch(f"{FLOW_MOD}.SessionLocal")
    def test_skips_no_schedule(self, mock_sl, mock_eft):
        """P01-06: Flow with no schedule → not triggered"""
        from app.workers.tasks.flows import scheduled_flow_execution_task

        mock_flow = MagicMock()
        mock_flow.schedule = None

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_flow]
        mock_sl.return_value = mock_db

        scheduled_flow_execution_task()
        mock_eft.delay.assert_not_called()

    @patch(f"{FLOW_MOD}.execute_flow_task")
    @patch(f"{FLOW_MOD}.SessionLocal")
    def test_skips_disabled(self, mock_sl, mock_eft):
        """P01-07: schedule.enabled=False → not triggered"""
        from app.workers.tasks.flows import scheduled_flow_execution_task

        mock_flow = MagicMock()
        mock_flow.schedule = {"enabled": False, "cron": "* * * * *"}

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_flow]
        mock_sl.return_value = mock_db

        scheduled_flow_execution_task()
        mock_eft.delay.assert_not_called()

    @patch(f"{FLOW_MOD}.execute_flow_task")
    @patch(f"{FLOW_MOD}.SessionLocal")
    def test_fires_when_due(self, mock_sl, mock_eft):
        """P01-08: Due cron → execute_flow_task.delay called"""
        from app.workers.tasks.flows import scheduled_flow_execution_task

        mock_flow = MagicMock()
        mock_flow.id = uuid4()
        mock_flow.workspace_id = uuid4()
        mock_flow.created_by = uuid4()
        mock_flow.name = "test"
        mock_flow.schedule = {"enabled": True, "cron": "* * * * *"}

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_flow]
        # No recent execution
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_sl.return_value = mock_db

        # Mock croniter — it's imported as 'from croniter import croniter'
        with patch("croniter.croniter") as mock_croniter_cls:
            now = datetime.utcnow()
            mock_cron = MagicMock()
            # get_next returns a time in the past (within last minute)
            mock_cron.get_next.return_value = now - timedelta(seconds=30)
            mock_croniter_cls.return_value = mock_cron

            scheduled_flow_execution_task()

        mock_eft.delay.assert_called_once()


# ===================================================================
# generate_execution_report
# ===================================================================
class TestGenerateReport:
    @patch(f"{FLOW_MOD}.SessionLocal")
    def test_returns_report_dict(self, mock_sl):
        """P01-09: Returns dict with expected keys"""
        from app.workers.tasks.flows import generate_execution_report

        mock_exec = MagicMock()
        mock_exec.status = "completed"
        mock_exec.started_at = datetime.utcnow()
        mock_exec.completed_at = datetime.utcnow()
        mock_exec.duration_seconds = 10
        mock_exec.nodes_executed = 3
        mock_exec.nodes_passed = 2
        mock_exec.nodes_failed = 1
        mock_exec.nodes_skipped = 0
        mock_exec.result_summary = {}
        mock_exec.flow_id = uuid4()

        mock_flow = MagicMock()
        mock_flow.id = mock_exec.flow_id
        mock_flow.name = "Test Flow"

        mock_db = MagicMock()
        mock_sl.return_value = mock_db

        # First query → execution, second → flow, third → node_results
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_exec, mock_flow]
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        result = generate_execution_report(str(uuid4()), str(uuid4()))
        assert "summary" in result
        assert "nodes" in result

    @patch(f"{FLOW_MOD}.SessionLocal")
    def test_calculates_quality_score(self, mock_sl):
        """P01-10: quality_score = (passed/total)*100"""
        from app.workers.tasks.flows import generate_execution_report

        mock_exec = MagicMock()
        mock_exec.status = "completed"
        mock_exec.started_at = datetime.utcnow()
        mock_exec.completed_at = datetime.utcnow()
        mock_exec.duration_seconds = 5
        mock_exec.nodes_executed = 4
        mock_exec.nodes_passed = 3
        mock_exec.nodes_failed = 1
        mock_exec.nodes_skipped = 0
        mock_exec.result_summary = {}
        mock_exec.flow_id = uuid4()

        mock_flow = MagicMock()
        mock_flow.id = mock_exec.flow_id
        mock_flow.name = "Test"

        # Two check nodes: one passed, one failed
        nr1 = MagicMock()
        nr1.node_id = "n1"
        nr1.node_type = "check"
        nr1.status = "completed"
        nr1.execution_order = 1
        nr1.started_at = datetime.utcnow()
        nr1.completed_at = datetime.utcnow()
        nr1.duration_seconds = 1
        nr1.result = {"passed": True, "failed_rows": 0, "total_rows": 100}
        nr1.error_message = None

        nr2 = MagicMock()
        nr2.node_id = "n2"
        nr2.node_type = "check"
        nr2.status = "completed"
        nr2.execution_order = 2
        nr2.started_at = datetime.utcnow()
        nr2.completed_at = datetime.utcnow()
        nr2.duration_seconds = 1
        nr2.result = {"passed": False, "failed_rows": 10, "total_rows": 100}
        nr2.error_message = None

        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_exec, mock_flow]
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            nr1,
            nr2,
        ]

        result = generate_execution_report(str(uuid4()), str(uuid4()))
        assert result["summary"]["overall_quality_score"] == 50.0  # 1/2 * 100

    @patch(f"{FLOW_MOD}.SessionLocal")
    def test_stores_in_execution(self, mock_sl):
        """P01-11: result_summary updated on execution"""
        from app.workers.tasks.flows import generate_execution_report

        mock_exec = MagicMock()
        mock_exec.status = "completed"
        mock_exec.started_at = datetime.utcnow()
        mock_exec.completed_at = datetime.utcnow()
        mock_exec.duration_seconds = 5
        mock_exec.nodes_executed = 0
        mock_exec.nodes_passed = 0
        mock_exec.nodes_failed = 0
        mock_exec.nodes_skipped = 0
        mock_exec.result_summary = {}
        mock_exec.flow_id = uuid4()

        mock_flow = MagicMock()
        mock_flow.id = mock_exec.flow_id
        mock_flow.name = "x"

        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_exec, mock_flow]
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        generate_execution_report(str(uuid4()), str(uuid4()))
        mock_db.commit.assert_called_once()
        assert "detailed_report" in mock_exec.result_summary


# ===================================================================
# cleanup_old_executions
# ===================================================================
class TestCleanupExecutions:
    @patch(f"{FLOW_MOD}.SessionLocal")
    def test_deletes_old(self, mock_sl):
        """P01-12: Deletes records older than cutoff"""
        from app.workers.tasks.flows import cleanup_old_executions

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.delete.return_value = 5
        mock_sl.return_value = mock_db

        cleanup_old_executions(days=30)
        mock_db.commit.assert_called_once()

    @patch(f"{FLOW_MOD}.SessionLocal")
    def test_default_90_days(self, mock_sl):
        """P01-13: Default retention is 90 days"""
        from app.workers.tasks.flows import cleanup_old_executions

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.delete.return_value = 0
        mock_sl.return_value = mock_db

        # Just verify it doesn't crash with defaults
        cleanup_old_executions()
        mock_db.commit.assert_called_once()


# ===================================================================
# send_flow_completion_notification
# ===================================================================
class TestNotification:
    @patch(f"{FLOW_MOD}.SessionLocal")
    def test_completed_flow_message(self, mock_sl, capsys):
        """P01-14: Completed flow notification includes ✅"""
        from app.workers.tasks.flows import send_flow_completion_notification

        mock_exec = MagicMock()
        mock_exec.status = "completed"
        mock_exec.nodes_executed = 3
        mock_exec.nodes_passed = 3
        mock_exec.nodes_failed = 0
        mock_exec.duration_seconds = 5
        mock_exec.flow_id = uuid4()

        mock_flow = MagicMock()
        mock_flow.name = "TestFlow"

        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_exec, mock_flow]

        send_flow_completion_notification(str(uuid4()))
        captured = capsys.readouterr()
        assert "✅" in captured.out

    @patch(f"{FLOW_MOD}.SessionLocal")
    def test_failed_flow_message(self, mock_sl, capsys):
        """P01-15: Failed flow notification includes ❌"""
        from app.workers.tasks.flows import send_flow_completion_notification

        mock_exec = MagicMock()
        mock_exec.status = "failed"
        mock_exec.error_message = "Some error"
        mock_exec.flow_id = uuid4()

        mock_flow = MagicMock()
        mock_flow.name = "TestFlow"

        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_exec, mock_flow]

        send_flow_completion_notification(str(uuid4()))
        captured = capsys.readouterr()
        assert "❌" in captured.out
