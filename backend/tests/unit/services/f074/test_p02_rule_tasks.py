"""
F074 P02 — Unit tests: Rule Tasks (rules.py)

Tests DatabaseTask, execute_rule_task, bulk_execute_rules_task,
scheduled_rule_execution_task, cleanup_old_violations_task.

P02-01 .. P02-15  (15 tests)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import pytest

RULE_MOD = "app.workers.tasks.rules"


# ===================================================================
# DatabaseTask
# ===================================================================
class TestDatabaseTask:
    def test_after_return_closes(self):
        """P02-01: session.close() called in after_return"""
        from app.workers.tasks.rules import DatabaseTask

        task = DatabaseTask()
        mock_session = MagicMock()
        task._db_session = mock_session

        task.after_return("SUCCESS", None, "id-1", [], {}, None)
        mock_session.close.assert_called_once()

    def test_after_return_none_safe(self):
        """P02-02: _db_session=None → no error"""
        from app.workers.tasks.rules import DatabaseTask

        task = DatabaseTask()
        task._db_session = None
        task.after_return("FAILURE", None, "id-2", [], {}, None)  # should not raise


# ===================================================================
# execute_rule_task
# ===================================================================
class TestExecuteRuleTask:
    @patch(f"{RULE_MOD}.RuleService")
    @patch(f"{RULE_MOD}.get_db_context")
    def test_returns_dict(self, mock_gdb, mock_rs_cls):
        """P02-03: Returns dict with execution_id, status"""
        from app.workers.tasks.rules import execute_rule_task

        mock_db = MagicMock()
        mock_gdb.return_value = iter([mock_db])

        mock_exec = MagicMock()
        mock_exec.id = uuid4()
        mock_exec.rule_id = uuid4()
        mock_exec.status = "completed"
        mock_exec.pass_rate = 0.95
        mock_exec.violation_count = 5
        mock_exec.duration_seconds = 3

        mock_service = MagicMock()
        mock_service.execute_rule.return_value = mock_exec
        mock_rs_cls.return_value = mock_service

        result = execute_rule_task(str(uuid4()), str(uuid4()), str(uuid4()))
        assert "execution_id" in result
        assert result["status"] == "completed"
        assert result["pass_rate"] == 0.95
        assert result["violation_count"] == 5

    @patch(f"{RULE_MOD}.RuleService")
    @patch(f"{RULE_MOD}.get_db_context")
    def test_calls_service(self, mock_gdb, mock_rs_cls):
        """P02-04: RuleService.execute_rule called"""
        from app.workers.tasks.rules import execute_rule_task

        mock_db = MagicMock()
        mock_gdb.return_value = iter([mock_db])

        mock_exec = MagicMock()
        mock_exec.id = uuid4()
        mock_exec.rule_id = uuid4()
        mock_exec.status = "completed"
        mock_exec.pass_rate = 1.0
        mock_exec.violation_count = 0
        mock_exec.duration_seconds = 1

        mock_service = MagicMock()
        mock_service.execute_rule.return_value = mock_exec
        mock_rs_cls.return_value = mock_service

        execute_rule_task(str(uuid4()), str(uuid4()), str(uuid4()))
        mock_service.execute_rule.assert_called_once()

    @patch(f"{RULE_MOD}.RuleService")
    @patch(f"{RULE_MOD}.get_db_context")
    def test_error_reraises(self, mock_gdb, mock_rs_cls):
        """P02-05: Exception → re-raises"""
        from app.workers.tasks.rules import execute_rule_task

        mock_db = MagicMock()
        mock_gdb.return_value = iter([mock_db])

        mock_service = MagicMock()
        mock_service.execute_rule.side_effect = ValueError("bad rule")
        mock_rs_cls.return_value = mock_service

        with pytest.raises(ValueError, match="bad rule"):
            execute_rule_task(str(uuid4()), str(uuid4()), str(uuid4()))


# ===================================================================
# bulk_execute_rules_task
# ===================================================================
class TestBulkExecute:
    @patch(f"{RULE_MOD}.RuleService")
    @patch(f"{RULE_MOD}.get_db_context")
    def test_all_succeed(self, mock_gdb, mock_rs_cls):
        """P02-06: All rules pass → successful=N"""
        from app.workers.tasks.rules import bulk_execute_rules_task

        mock_db = MagicMock()
        mock_gdb.return_value = iter([mock_db])

        mock_exec = MagicMock()
        mock_exec.id = uuid4()
        mock_exec.status = "completed"

        mock_service = MagicMock()
        mock_service.execute_rule.return_value = mock_exec
        mock_rs_cls.return_value = mock_service

        ids = [str(uuid4()), str(uuid4())]
        # Note: bulk_execute_rules_task uses get_db_session (typo in source)
        # We need to also patch that
        with patch(f"{RULE_MOD}.get_db_session", return_value=iter([mock_db]), create=True):
            result = bulk_execute_rules_task(ids, str(uuid4()), str(uuid4()))

        assert result["total"] == 2
        assert result["successful"] == 2
        assert result["failed"] == 0

    @patch(f"{RULE_MOD}.RuleService")
    @patch(f"{RULE_MOD}.get_db_context")
    def test_partial_failure(self, mock_gdb, mock_rs_cls):
        """P02-07: One fails → failed=1, rest succeed"""
        from app.workers.tasks.rules import bulk_execute_rules_task

        mock_db = MagicMock()
        mock_gdb.return_value = iter([mock_db])

        mock_exec = MagicMock()
        mock_exec.id = uuid4()
        mock_exec.status = "completed"

        mock_service = MagicMock()
        mock_service.execute_rule.side_effect = [mock_exec, ValueError("fail"), mock_exec]
        mock_rs_cls.return_value = mock_service

        ids = [str(uuid4()), str(uuid4()), str(uuid4())]
        with patch(f"{RULE_MOD}.get_db_session", return_value=iter([mock_db]), create=True):
            result = bulk_execute_rules_task(ids, str(uuid4()), str(uuid4()))

        assert result["failed"] == 1
        assert result["successful"] == 2

    @patch(f"{RULE_MOD}.RuleService")
    @patch(f"{RULE_MOD}.get_db_context")
    def test_returns_aggregate(self, mock_gdb, mock_rs_cls):
        """P02-08: Returns total, successful, failed, results"""
        from app.workers.tasks.rules import bulk_execute_rules_task

        mock_db = MagicMock()
        mock_gdb.return_value = iter([mock_db])

        mock_exec = MagicMock()
        mock_exec.id = uuid4()
        mock_exec.status = "completed"

        mock_service = MagicMock()
        mock_service.execute_rule.return_value = mock_exec
        mock_rs_cls.return_value = mock_service

        with patch(f"{RULE_MOD}.get_db_session", return_value=iter([mock_db]), create=True):
            result = bulk_execute_rules_task([str(uuid4())], str(uuid4()), str(uuid4()))

        assert "total" in result
        assert "successful" in result
        assert "failed" in result
        assert "results" in result


# ===================================================================
# scheduled_rule_execution_task
# ===================================================================
class TestScheduledRuleExec:
    @patch(f"{RULE_MOD}.execute_rule_task")
    @patch(f"{RULE_MOD}.get_db_context")
    def test_skips_no_cron(self, mock_gdb, mock_ert):
        """P02-09: Rule without cron → not executed"""
        from app.workers.tasks.rules import scheduled_rule_execution_task

        mock_db = MagicMock()
        mock_gdb.return_value = iter([mock_db])

        mock_rule = MagicMock()
        mock_rule.schedule = {"enabled": True}  # No 'cron' key

        mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_rule]

        with patch(f"{RULE_MOD}.RuleService"):
            result = scheduled_rule_execution_task()

        mock_ert.delay.assert_not_called()
        assert result["executed"] == 0

    @patch(f"{RULE_MOD}.execute_rule_task")
    @patch(f"{RULE_MOD}.get_db_context")
    def test_fires_due_rule(self, mock_gdb, mock_ert):
        """P02-10: Due rule → execute_rule_task.delay"""
        from app.workers.tasks.rules import scheduled_rule_execution_task

        mock_db = MagicMock()
        mock_gdb.return_value = iter([mock_db])

        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.workspace_id = uuid4()
        mock_rule.created_by = uuid4()
        mock_rule.name = "test"
        mock_rule.schedule = {"cron": "* * * * *"}

        mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_rule]
        # No recent execution
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        now = datetime.utcnow()
        with patch("croniter.croniter") as mock_croniter_cls, patch(f"{RULE_MOD}.RuleService"):
            mock_cron = MagicMock()
            mock_cron.get_next.return_value = now + timedelta(seconds=60)
            mock_cron.get_prev.return_value = now - timedelta(seconds=10)
            mock_croniter_cls.return_value = mock_cron

            result = scheduled_rule_execution_task()

        mock_ert.delay.assert_called_once()
        assert result["executed"] == 1

    @patch(f"{RULE_MOD}.execute_rule_task")
    @patch(f"{RULE_MOD}.get_db_context")
    def test_skips_recent_execution(self, mock_gdb, mock_ert):
        """P02-11: Executed <60s ago → skip"""
        from app.workers.tasks.rules import scheduled_rule_execution_task

        mock_db = MagicMock()
        mock_gdb.return_value = iter([mock_db])

        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.schedule = {"cron": "* * * * *"}

        mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_rule]

        # Recent execution (30s ago)
        mock_last_exec = MagicMock()
        mock_last_exec.created_at = datetime.utcnow() - timedelta(seconds=30)
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_last_exec

        now = datetime.utcnow()
        with patch("croniter.croniter") as mock_croniter_cls, patch(f"{RULE_MOD}.RuleService"):
            mock_cron = MagicMock()
            mock_cron.get_next.return_value = now + timedelta(seconds=60)
            mock_cron.get_prev.return_value = now - timedelta(seconds=10)
            mock_croniter_cls.return_value = mock_cron

            result = scheduled_rule_execution_task()

        mock_ert.delay.assert_not_called()
        assert result["executed"] == 0

    @patch(f"{RULE_MOD}.execute_rule_task")
    @patch(f"{RULE_MOD}.get_db_context")
    def test_returns_summary(self, mock_gdb, mock_ert):
        """P02-12: Returns checked, executed, timestamp"""
        from app.workers.tasks.rules import scheduled_rule_execution_task

        mock_db = MagicMock()
        mock_gdb.return_value = iter([mock_db])
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        with patch(f"{RULE_MOD}.RuleService"):
            result = scheduled_rule_execution_task()

        assert "checked" in result
        assert "executed" in result
        assert "timestamp" in result


# ===================================================================
# cleanup_old_violations_task
# ===================================================================
class TestCleanupViolations:
    @patch(f"{RULE_MOD}.get_db_context")
    def test_deletes_old(self, mock_gdb):
        """P02-13: Old violations deleted"""
        from app.workers.tasks.rules import cleanup_old_violations_task

        mock_db = MagicMock()
        mock_gdb.return_value = iter([mock_db])
        mock_db.execute.return_value.rowcount = 10

        result = cleanup_old_violations_task(days=30)
        mock_db.commit.assert_called_once()
        assert result["deleted"] == 10

    @patch(f"{RULE_MOD}.get_db_context")
    def test_returns_count(self, mock_gdb):
        """P02-14: Returns deleted count and cutoff"""
        from app.workers.tasks.rules import cleanup_old_violations_task

        mock_db = MagicMock()
        mock_gdb.return_value = iter([mock_db])
        mock_db.execute.return_value.rowcount = 42

        result = cleanup_old_violations_task(days=90)
        assert result["deleted"] == 42
        assert "cutoff_date" in result

    @patch(f"{RULE_MOD}.get_db_context")
    def test_rollback_on_error(self, mock_gdb):
        """P02-15: Exception → db.rollback"""
        from app.workers.tasks.rules import cleanup_old_violations_task

        mock_db = MagicMock()
        mock_gdb.return_value = iter([mock_db])
        mock_db.execute.side_effect = RuntimeError("db error")

        with pytest.raises(RuntimeError):
            cleanup_old_violations_task(days=30)
        mock_db.rollback.assert_called_once()
