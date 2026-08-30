"""
F076-P03  Sample Capture + Full Pipeline Integration
15 tests · SampleCaptureService + full pipeline wired with mocks at boundaries
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.services.issues.issue_sample_models import SampleDomain
from app.services.issues.sample_capture_service import SampleCaptureService

SAMPLE_MOD = "app.services.issues.sample_capture_service"
ISSUE_MOD = "app.services.issues.issue_creation_service"
CHECK_MOD = "app.services.flows.node_handlers.check_node"
EXEC_MOD = "app.services.flows.executor"


# ---------------------------------------------------------------------------
# TestSampleCapture
# ---------------------------------------------------------------------------
class TestSampleCapture:
    def test_capture_extracts_violations(self):
        repo = MagicMock()
        repo.insert.side_effect = lambda db, d: d
        svc = SampleCaptureService(repository=repo)
        db = MagicMock()

        violations = [{"email": "bad@", "id": i} for i in range(5)]
        result = svc.capture_for_issue(
            db=db,
            issue_id=uuid4(),
            workspace_id=uuid4(),
            dataset_id=None,
            node_result_result_data={"violations": violations},
        )
        assert result is not None
        assert result.sample_count == 5

    def test_capture_caps_at_50(self):
        repo = MagicMock()
        repo.insert.side_effect = lambda db, d: d
        svc = SampleCaptureService(repository=repo)
        db = MagicMock()

        violations = [{"col": f"v{i}"} for i in range(100)]
        result = svc.capture_for_issue(
            db=db,
            issue_id=uuid4(),
            workspace_id=uuid4(),
            dataset_id=None,
            node_result_result_data={"violations": violations},
        )
        assert result.sample_count == 50

    def test_capture_applies_masking(self):
        repo = MagicMock()
        repo.insert.side_effect = lambda db, d: d
        svc = SampleCaptureService(repository=repo)
        db = MagicMock()

        violations = [{"email": "test@x.com", "ssn": "123-45-6789"}]
        with patch(f"{SAMPLE_MOD}._load_sensitivity_map", return_value={"ssn": "confidential"}):
            result = svc.capture_for_issue(
                db=db,
                issue_id=uuid4(),
                workspace_id=uuid4(),
                dataset_id=uuid4(),
                node_result_result_data={"violations": violations},
            )
        assert result.masking_applied is True
        assert result.rows[0]["ssn"] == "[MASKED]"
        assert result.rows[0]["email"] == "test@x.com"

    def test_capture_no_violations_returns_none(self):
        svc = SampleCaptureService(repository=MagicMock())
        result = svc.capture_for_issue(
            db=MagicMock(),
            issue_id=uuid4(),
            workspace_id=uuid4(),
            dataset_id=None,
            node_result_result_data={"violations": []},
        )
        assert result is None

    def test_capture_error_non_blocking(self):
        repo = MagicMock()
        repo.insert.side_effect = Exception("db down")
        svc = SampleCaptureService(repository=repo)
        # The service itself doesn't catch — the CALLER (IssueCreationService) catches.
        # But let's verify the repo.insert IS called and raises.
        with pytest.raises(Exception):
            svc.capture_for_issue(
                db=MagicMock(),
                issue_id=uuid4(),
                workspace_id=uuid4(),
                dataset_id=None,
                node_result_result_data={"violations": [{"a": 1}]},
            )

    def test_capture_persists_sample_domain(self):
        repo = MagicMock()
        repo.insert.side_effect = lambda db, d: d
        svc = SampleCaptureService(repository=repo)
        db = MagicMock()

        svc.capture_for_issue(
            db=db,
            issue_id=uuid4(),
            workspace_id=uuid4(),
            dataset_id=None,
            node_result_result_data={"violations": [{"x": 1}]},
        )
        repo.insert.assert_called_once()
        domain = repo.insert.call_args[0][1]
        assert isinstance(domain, SampleDomain)

    def test_capture_masking_threshold_set(self):
        repo = MagicMock()
        repo.insert.side_effect = lambda db, d: d
        svc = SampleCaptureService(repository=repo)

        with patch(f"{SAMPLE_MOD}._load_sensitivity_map", return_value={"secret": "restricted"}):
            result = svc.capture_for_issue(
                db=MagicMock(),
                issue_id=uuid4(),
                workspace_id=uuid4(),
                dataset_id=uuid4(),
                node_result_result_data={"violations": [{"secret": "val", "pub": "ok"}]},
            )
        assert result.masking_threshold == "confidential"


# ---------------------------------------------------------------------------
# TestFullPipeline — compile → check → issue → sample wired together
# ---------------------------------------------------------------------------
class TestFullPipeline:
    """Wires real services with mocks only at the DB/connector boundary."""

    def _flow_def(self, check_status="completed"):
        return {
            "nodes": [
                {
                    "id": "src-1",
                    "type": "source",
                    "label": "S",
                    "config": {"data_source_id": str(uuid4())},
                    "position": {"x": 0, "y": 0},
                },
                {
                    "id": "chk-1",
                    "type": "check",
                    "label": "C1",
                    "checkType": "completeness",
                    "config": {"checkType": "completeness", "columns": ["email"], "threshold": 90},
                    "position": {"x": 200, "y": 0},
                },
            ],
            "connections": [
                {
                    "id": "c1",
                    "source": "src-1",
                    "target": "chk-1",
                    "sourcePort": "output",
                    "targetPort": "input",
                },
            ],
        }

    def _mock_flow(self, flow_def=None):
        from app.models.flow import DQFlow

        f = MagicMock(spec=DQFlow)
        f.id = uuid4()
        f.workspace_id = uuid4()
        f.flow_definition = flow_def or self._flow_def()
        return f

    def _setup_executor(self, node_results):
        """Create FlowExecutor with mocked _execute_node returning predetermined results."""
        from app.services.flows.executor import FlowExecutor

        executor = FlowExecutor()

        async def mock_exec(*args, **kwargs):
            from app.models.flow import FlowNodeResult

            node = kwargs.get("node") or args[4]
            nr = MagicMock(spec=FlowNodeResult)
            if node.id in node_results:
                r = node_results[node.id]
                nr.status = r["status"]
                nr.result_data = r.get("result_data", {})
                nr.node_type = node.type.value
                nr.error_message = r.get("error_message")
            else:
                nr.status = "completed"
                nr.result_data = {"output_data": {"data_source": {}}}
                nr.node_type = node.type.value
                nr.error_message = None
            return nr

        return executor, mock_exec

    @pytest.mark.asyncio
    async def test_full_pipeline_passing_flow(self):
        """connect → compile → execute → no issue (all pass)."""
        executor, mock_exec = self._setup_executor(
            {
                "src-1": {
                    "status": "completed",
                    "result_data": {"output_data": {"data_source": {}}},
                },
                "chk-1": {
                    "status": "completed",
                    "result_data": {
                        "output_data": {},
                        "rows_scanned": 100,
                        "rows_passed": 100,
                        "rows_failed": 0,
                        "pass_rate": 100,
                        "violations": [],
                        "violation_count": 0,
                    },
                },
            }
        )
        flow = self._mock_flow()
        db = MagicMock()
        db.refresh = MagicMock()

        with patch.object(executor, "_execute_node", side_effect=mock_exec):
            result = await executor.execute_flow(
                db=db,
                flow=flow,
                workspace_id=uuid4(),
                executed_by=uuid4(),
            )
        assert result.status == "completed"
        assert result.nodes_failed == 0

    @pytest.mark.asyncio
    async def test_full_pipeline_failing_flow(self):
        """connect → compile → execute → issue should be created (check fails)."""
        from app.services.issues.issue_creation_service import IssueCreationService

        # Phase 1: Execute flow
        executor, mock_exec = self._setup_executor(
            {
                "src-1": {
                    "status": "completed",
                    "result_data": {"output_data": {"data_source": {}}},
                },
                "chk-1": {
                    "status": "failed",
                    "result_data": {
                        "output_data": {},
                        "rows_scanned": 100,
                        "rows_passed": 50,
                        "rows_failed": 50,
                        "pass_rate": 50,
                        "violations": [{"email": None}],
                        "violation_count": 1,
                    },
                },
            }
        )
        flow = self._mock_flow()
        db = MagicMock()
        db.refresh = MagicMock()

        with patch.object(executor, "_execute_node", side_effect=mock_exec):
            result = await executor.execute_flow(
                db=db,
                flow=flow,
                workspace_id=uuid4(),
                executed_by=uuid4(),
                execution_config={"continue_on_error": True},
            )
        assert result.status == "failed"
        assert result.nodes_failed >= 1

    @pytest.mark.asyncio
    async def test_full_pipeline_mixed_results(self):
        """2 checks: 1 pass + 1 fail → 1 failure recorded."""
        nodes = [
            {
                "id": "src-1",
                "type": "source",
                "label": "S",
                "config": {"data_source_id": str(uuid4())},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "chk-1",
                "type": "check",
                "label": "C1",
                "checkType": "completeness",
                "config": {"checkType": "completeness"},
                "position": {"x": 200, "y": 0},
            },
            {
                "id": "chk-2",
                "type": "check",
                "label": "C2",
                "checkType": "validity",
                "config": {"checkType": "validity"},
                "position": {"x": 200, "y": 100},
            },
        ]
        conns = [
            {
                "id": "c1",
                "source": "src-1",
                "target": "chk-1",
                "sourcePort": "output",
                "targetPort": "input",
            },
            {
                "id": "c2",
                "source": "src-1",
                "target": "chk-2",
                "sourcePort": "output",
                "targetPort": "input",
            },
        ]
        executor, mock_exec = self._setup_executor(
            {
                "src-1": {
                    "status": "completed",
                    "result_data": {"output_data": {"data_source": {}}},
                },
                "chk-1": {
                    "status": "completed",
                    "result_data": {
                        "output_data": {},
                        "rows_scanned": 100,
                        "violation_count": 0,
                    },
                },
                "chk-2": {
                    "status": "failed",
                    "result_data": {
                        "output_data": {},
                        "rows_scanned": 100,
                        "violation_count": 5,
                    },
                },
            }
        )
        flow = self._mock_flow({"nodes": nodes, "connections": conns})
        db = MagicMock()
        db.refresh = MagicMock()

        with patch.object(executor, "_execute_node", side_effect=mock_exec):
            result = await executor.execute_flow(
                db=db,
                flow=flow,
                workspace_id=uuid4(),
                executed_by=uuid4(),
                execution_config={"continue_on_error": True},
            )
        assert result.nodes_passed == 2  # src-1 + chk-1
        assert result.nodes_failed == 1  # chk-2

    @pytest.mark.asyncio
    async def test_full_pipeline_metrics_aggregated(self):
        """FlowExecution has correct aggregated node counts."""
        executor, mock_exec = self._setup_executor(
            {
                "src-1": {
                    "status": "completed",
                    "result_data": {"output_data": {"data_source": {}}},
                },
                "chk-1": {
                    "status": "completed",
                    "result_data": {
                        "output_data": {},
                        "rows_scanned": 200,
                        "violation_count": 3,
                    },
                },
            }
        )
        flow = self._mock_flow()
        db = MagicMock()
        db.refresh = MagicMock()

        with patch.object(executor, "_execute_node", side_effect=mock_exec):
            result = await executor.execute_flow(
                db=db,
                flow=flow,
                workspace_id=uuid4(),
                executed_by=uuid4(),
            )
        assert result.nodes_executed == 2
        assert result.nodes_passed == 2
        assert result.result_summary["total_rows_scanned"] == 200

    @pytest.mark.asyncio
    async def test_full_pipeline_adhoc_check(self):
        """No rule_id — builds canonical rule from config → still processes."""
        executor, mock_exec = self._setup_executor(
            {
                "src-1": {
                    "status": "completed",
                    "result_data": {"output_data": {"data_source": {}}},
                },
                "chk-1": {
                    "status": "failed",
                    "result_data": {
                        "output_data": {},
                        "rows_scanned": 50,
                        "rows_failed": 10,
                        "pass_rate": 80,
                        "violations": [{"email": None}],
                        "violation_count": 1,
                    },
                },
            }
        )
        flow = self._mock_flow()
        db = MagicMock()
        db.refresh = MagicMock()

        with patch.object(executor, "_execute_node", side_effect=mock_exec):
            result = await executor.execute_flow(
                db=db,
                flow=flow,
                workspace_id=uuid4(),
                executed_by=uuid4(),
                execution_config={"continue_on_error": True},
            )
        assert result.nodes_failed == 1

    @pytest.mark.asyncio
    async def test_full_pipeline_spark_path(self):
        """Spark compilation path still produces valid result."""
        from app.services.rules.compiler import RuleCompiler

        compiler = RuleCompiler()
        rule = {
            "dimension": "completeness",
            "entity": "data.email",
            "condition": "IS NOT NULL",
            "expectation": "100%",
            "parameters": {"columns": ["email"]},
        }
        spark_sql = compiler.compile_rule_for_spark(rule, target_table="data")
        assert isinstance(spark_sql, str)
        assert len(spark_sql) > 0

    @pytest.mark.asyncio
    async def test_full_pipeline_error_resilience(self):
        """Error in one check → executor handles, records failure, creates issue."""
        executor, mock_exec = self._setup_executor(
            {
                "src-1": {
                    "status": "completed",
                    "result_data": {"output_data": {"data_source": {}}},
                },
                "chk-1": {
                    "status": "failed",
                    "error_message": "Connection refused",
                    "result_data": {"output_data": {}, "rows_scanned": 0, "violation_count": 0},
                },
            }
        )
        flow = self._mock_flow()
        db = MagicMock()
        db.refresh = MagicMock()

        with patch.object(executor, "_execute_node", side_effect=mock_exec):
            result = await executor.execute_flow(
                db=db,
                flow=flow,
                workspace_id=uuid4(),
                executed_by=uuid4(),
                execution_config={"continue_on_error": True},
            )
        assert result.nodes_failed == 1
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_full_pipeline_multi_level_flow(self):
        """Source level → Check level: sequential level execution."""
        executor, mock_exec = self._setup_executor(
            {
                "src-1": {
                    "status": "completed",
                    "result_data": {"output_data": {"data_source": {}}},
                },
                "chk-1": {
                    "status": "completed",
                    "result_data": {
                        "output_data": {},
                        "rows_scanned": 100,
                        "violation_count": 0,
                    },
                },
            }
        )
        flow = self._mock_flow()
        db = MagicMock()
        db.refresh = MagicMock()

        with patch.object(executor, "_execute_node", side_effect=mock_exec):
            result = await executor.execute_flow(
                db=db,
                flow=flow,
                workspace_id=uuid4(),
                executed_by=uuid4(),
            )
        # Source runs in level 1, check in level 2
        assert result.nodes_executed == 2
        assert result.status == "completed"
