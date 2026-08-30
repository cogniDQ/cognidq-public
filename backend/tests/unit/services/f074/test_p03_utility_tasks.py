"""
F074-P03 · Utility Task Tests (data_quality + rule_validation)
15 tests — covers all 5 Celery tasks in the two stub modules.

For bind=True Celery tasks, __wrapped__ is a bound method (self = task instance).
We patch update_state on the task instance to avoid "task_id must not be empty" errors.
"""

from unittest.mock import MagicMock, patch

import pytest

DQ_MOD = "app.workers.tasks.data_quality"
RV_MOD = "app.workers.tasks.rule_validation"


def _call_bound_task(task, *args, **kwargs):
    """Call a bind=True Celery task, patching update_state to avoid task_id errors."""
    real_task = task._get_current_object()
    mock_update = MagicMock()
    with patch.object(real_task, "update_state", mock_update):
        result = task.__wrapped__(*args, **kwargs)
    return result, mock_update


# ===================================================================
# analyze_data_quality  (bind=True, 5 tests)
# ===================================================================
class TestAnalyzeQuality:
    @patch(f"{DQ_MOD}.time")
    def test_returns_scores(self, mock_time):
        """P03-01: Returns completeness, accuracy, consistency scores"""
        from app.workers.tasks.data_quality import analyze_data_quality

        mock_time.time.return_value = 1000.0
        result, _ = _call_bound_task(analyze_data_quality, "orders", "public")

        assert result["completeness_score"] == 0.95
        assert result["accuracy_score"] == 0.88
        assert result["consistency_score"] == 0.92

    @patch(f"{DQ_MOD}.time")
    def test_overall_score(self, mock_time):
        """P03-02: overall_score present and numeric"""
        from app.workers.tasks.data_quality import analyze_data_quality

        mock_time.time.return_value = 1000.0
        result, _ = _call_bound_task(analyze_data_quality, "orders")

        assert result["overall_score"] == 0.92

    @patch(f"{DQ_MOD}.time")
    def test_status_completed(self, mock_time):
        """P03-03: status → completed on success"""
        from app.workers.tasks.data_quality import analyze_data_quality

        mock_time.time.return_value = 1000.0
        result, _ = _call_bound_task(analyze_data_quality, "tbl")

        assert result["status"] == "completed"

    @patch(f"{DQ_MOD}.time")
    def test_table_name_includes_schema(self, mock_time):
        """P03-04: table_name = schema.table"""
        from app.workers.tasks.data_quality import analyze_data_quality

        mock_time.time.return_value = 1000.0
        result, _ = _call_bound_task(analyze_data_quality, "orders", "sales")

        assert result["table_name"] == "sales.orders"

    @patch(f"{DQ_MOD}.time")
    def test_error_returns_failed(self, mock_time):
        """P03-05: Exception → status=failed, error message"""
        from app.workers.tasks.data_quality import analyze_data_quality

        real_task = analyze_data_quality._get_current_object()
        mock_update = MagicMock(side_effect=RuntimeError("boom"))
        with patch.object(real_task, "update_state", mock_update):
            result = analyze_data_quality.__wrapped__("tbl")

        assert result["status"] == "failed"
        assert "boom" in result["error"]

    @patch(f"{DQ_MOD}.time")
    def test_progress_updates(self, mock_time):
        """P03-06: update_state called 4 times for progress"""
        from app.workers.tasks.data_quality import analyze_data_quality

        mock_time.time.return_value = 1000.0
        _, mock_update = _call_bound_task(analyze_data_quality, "tbl")

        assert mock_update.call_count == 4


# ===================================================================
# generate_quality_report  (3 tests)
# ===================================================================
class TestQualityReport:
    @patch(f"{DQ_MOD}.time")
    def test_report_dict(self, mock_time):
        """P03-07: Returns dict with expected keys"""
        from app.workers.tasks.data_quality import generate_quality_report

        mock_time.time.return_value = 2000.0
        result = generate_quality_report("my_db")

        assert result["database"] == "my_db"
        assert result["status"] == "completed"
        assert "tables_analyzed" in result

    @patch(f"{DQ_MOD}.time")
    def test_report_url(self, mock_time):
        """P03-08: report_url includes database name"""
        from app.workers.tasks.data_quality import generate_quality_report

        mock_time.time.return_value = 2000.0
        result = generate_quality_report("testdb")

        assert "testdb" in result["report_url"]

    @patch(f"{DQ_MOD}.time")
    def test_report_error(self, mock_time):
        """P03-09: Exception → failed status"""
        from app.workers.tasks.data_quality import generate_quality_report

        mock_time.sleep.side_effect = RuntimeError("timeout")
        result = generate_quality_report("db")

        assert result["status"] == "failed"
        assert "timeout" in result["error"]


# ===================================================================
# schedule_quality_check  (3 tests)
# ===================================================================
class TestScheduleCheck:
    @patch(f"{DQ_MOD}.time")
    def test_schedule_id(self, mock_time):
        """P03-10: Returns schedule_id starting with sched_"""
        from app.workers.tasks.data_quality import schedule_quality_check

        mock_time.time.return_value = 9999.0
        result = schedule_quality_check({"frequency": "weekly"})

        assert result["schedule_id"].startswith("sched_")

    @patch(f"{DQ_MOD}.time")
    def test_default_frequency(self, mock_time):
        """P03-11: Missing frequency key defaults to daily"""
        from app.workers.tasks.data_quality import schedule_quality_check

        mock_time.time.return_value = 9999.0
        result = schedule_quality_check({})

        assert result["frequency"] == "daily"

    @patch(f"{DQ_MOD}.time")
    def test_next_run(self, mock_time):
        """P03-12: next_run = now + 86400"""
        from app.workers.tasks.data_quality import schedule_quality_check

        mock_time.time.return_value = 10000.0
        result = schedule_quality_check({"frequency": "daily"})

        assert result["next_run"] == 10000.0 + 86400


# ===================================================================
# validate_rule_async  (bind=True, 2 tests)
# ===================================================================
class TestValidateRuleAsync:
    @patch(f"{RV_MOD}.time")
    def test_valid_result(self, mock_time):
        """P03-13: Returns syntax_valid, schema_valid, test_passed all True"""
        from app.workers.tasks.rule_validation import validate_rule_async

        mock_time.time.return_value = 5000.0
        result, _ = _call_bound_task(validate_rule_async, "r1", "SELECT 1")

        assert result["syntax_valid"] is True
        assert result["schema_valid"] is True
        assert result["test_passed"] is True
        assert result["status"] == "completed"

    @patch(f"{RV_MOD}.time")
    def test_error_returns_failed(self, mock_time):
        """P03-14: Exception → status=failed"""
        from app.workers.tasks.rule_validation import validate_rule_async

        real_task = validate_rule_async._get_current_object()
        mock_update = MagicMock(side_effect=RuntimeError("explode"))
        with patch.object(real_task, "update_state", mock_update):
            result = validate_rule_async.__wrapped__("r2", "SELECT 1")

        assert result["status"] == "failed"
        assert "explode" in result["error"]


# ===================================================================
# batch_validate_rules  (1 test)
# ===================================================================
class TestBatchValidate:
    @patch(f"{RV_MOD}.time")
    def test_processes_all(self, mock_time):
        """P03-15: Validates all rule_ids, returns total and results"""
        from app.workers.tasks.rule_validation import batch_validate_rules

        mock_time.time.return_value = 6000.0
        result = batch_validate_rules(["r1", "r2", "r3"])

        assert result["total"] == 3
        assert result["validated"] == 3
        assert len(result["results"]) == 3
        assert result["status"] == "completed"
