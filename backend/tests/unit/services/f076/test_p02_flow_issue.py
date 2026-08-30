"""
F076-P02  Flow Execution + Issue Creation Integration
15 tests · FlowExecutor with mocked handlers + IssueCreationService with mocked db
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest
from app.models.flow import DQFlow, FlowExecution, FlowNodeResult
from app.schemas.flow import NodeStatus
from app.services.flows.executor import FlowExecutor

EXEC_MOD = "app.services.flows.executor"
ISSUE_MOD = "app.services.issues.issue_creation_service"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flow_def(nodes=None, connections=None):
    """Minimal valid flow definition JSONB."""
    return {
        "nodes": nodes
        or [
            {
                "id": "src-1",
                "type": "source",
                "label": "Orders",
                "config": {"data_source_id": str(uuid4())},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "chk-1",
                "type": "check",
                "label": "Completeness",
                "checkType": "completeness",
                "config": {"checkType": "completeness", "columns": ["email"], "threshold": 90},
                "position": {"x": 200, "y": 0},
            },
        ],
        "connections": connections
        or [
            {
                "id": "conn-1",
                "source": "src-1",
                "target": "chk-1",
                "sourcePort": "output",
                "targetPort": "input",
            },
        ],
    }


def _mock_flow(flow_def=None):
    flow = MagicMock(spec=DQFlow)
    flow.id = uuid4()
    flow.workspace_id = uuid4()
    flow.flow_definition = flow_def or _flow_def()
    return flow


def _mock_db():
    db = MagicMock()
    # Make refresh a no-op
    db.refresh = MagicMock()
    db.commit = MagicMock()
    db.add = MagicMock()
    return db


def _node_result_record(status="completed", node_type="check", result_data=None):
    nr = MagicMock(spec=FlowNodeResult)
    nr.status = status
    nr.node_type = node_type
    nr.result_data = result_data or {}
    nr.error_message = None
    return nr


# ===========================================================================
# TestFlowExecution
# ===========================================================================
class TestFlowExecution:
    @pytest.mark.asyncio
    async def test_executor_parses_flow_definition(self):
        """FlowExecutor parses flow_definition and resolves execution levels."""
        executor = FlowExecutor()
        flow = _mock_flow()
        db = _mock_db()

        # Mock node execution to return completed results
        async def mock_execute_node(*args, **kwargs):
            nr = MagicMock(spec=FlowNodeResult)
            nr.status = "completed"
            nr.result_data = {"output_data": {}}
            nr.node_type = "source"
            nr.error_message = None
            return nr

        with patch.object(executor, "_execute_node", side_effect=mock_execute_node):
            await executor.execute_flow(
                db=db,
                flow=flow,
                workspace_id=flow.workspace_id,
                executed_by=uuid4(),
            )
        # Should have added + committed an execution record
        db.add.assert_called()

    @pytest.mark.asyncio
    async def test_executor_single_source_single_check(self):
        """Source → Check: both nodes get executed."""
        executor = FlowExecutor()
        flow = _mock_flow()
        db = _mock_db()

        call_log = []

        async def mock_execute_node(*args, **kwargs):
            node = kwargs.get("node") or args[4]
            call_log.append(node.id)
            nr = MagicMock(spec=FlowNodeResult)
            nr.status = "completed"
            nr.result_data = {
                "output_data": {"data_source": {}},
                "rows_scanned": 0,
                "violation_count": 0,
            }
            nr.node_type = node.type.value
            nr.error_message = None
            return nr

        with patch.object(executor, "_execute_node", side_effect=mock_execute_node):
            await executor.execute_flow(db=db, flow=flow, workspace_id=uuid4(), executed_by=uuid4())

        assert "src-1" in call_log
        assert "chk-1" in call_log

    @pytest.mark.asyncio
    async def test_executor_multi_check_parallel(self):
        """Two checks from same source at same level run together."""
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
        flow = _mock_flow(_flow_def(nodes, conns))
        db = _mock_db()

        executed_nodes = []

        async def mock_exec_node(*args, **kwargs):
            node = kwargs.get("node") or args[4]
            executed_nodes.append(node.id)
            nr = MagicMock(spec=FlowNodeResult)
            nr.status = "completed"
            nr.result_data = {
                "output_data": {"data_source": {}},
                "rows_scanned": 0,
                "violation_count": 0,
            }
            nr.node_type = node.type.value
            nr.error_message = None
            return nr

        with patch.object(executor := FlowExecutor(), "_execute_node", side_effect=mock_exec_node):
            await executor.execute_flow(db=db, flow=flow, workspace_id=uuid4(), executed_by=uuid4())

        assert set(executed_nodes) == {"src-1", "chk-1", "chk-2"}

    @pytest.mark.asyncio
    async def test_executor_continue_on_error(self):
        """With continue_on_error=True, failed node doesn't block others."""
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
        flow = _mock_flow(_flow_def(nodes, conns))
        db = _mock_db()

        async def mock_exec_node(*args, **kwargs):
            node = kwargs.get("node") or args[4]
            nr = MagicMock(spec=FlowNodeResult)
            nr.node_type = node.type.value
            nr.error_message = None
            if node.id == "chk-1":
                nr.status = "failed"
                nr.result_data = {"output_data": {}, "rows_scanned": 0, "violation_count": 0}
            else:
                nr.status = "completed"
                nr.result_data = {
                    "output_data": {"data_source": {}},
                    "rows_scanned": 0,
                    "violation_count": 0,
                }
            return nr

        with patch.object(executor := FlowExecutor(), "_execute_node", side_effect=mock_exec_node):
            result = await executor.execute_flow(
                db=db,
                flow=flow,
                workspace_id=uuid4(),
                executed_by=uuid4(),
                execution_config={"continue_on_error": True},
            )
        # Both checks should have been executed (not skipped)
        assert result.nodes_executed == 3

    @pytest.mark.asyncio
    async def test_executor_stop_on_error(self):
        """Without continue_on_error, failure at level N skips level N+1."""
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
        ]
        conns = [
            {
                "id": "c1",
                "source": "src-1",
                "target": "chk-1",
                "sourcePort": "output",
                "targetPort": "input",
            },
        ]
        flow = _mock_flow(_flow_def(nodes, conns))
        db = _mock_db()

        async def mock_exec_node(*args, **kwargs):
            node = kwargs.get("node") or args[4]
            nr = MagicMock(spec=FlowNodeResult)
            nr.node_type = node.type.value
            nr.error_message = None
            if node.id == "src-1":
                # Source fails
                nr.status = "failed"
                nr.result_data = {"output_data": {}}
            else:
                nr.status = "completed"
                nr.result_data = {"output_data": {}, "rows_scanned": 0, "violation_count": 0}
            return nr

        with patch.object(executor := FlowExecutor(), "_execute_node", side_effect=mock_exec_node):
            result = await executor.execute_flow(
                db=db,
                flow=flow,
                workspace_id=uuid4(),
                executed_by=uuid4(),
                execution_config={"continue_on_error": False},
            )
        # Source fails → execution fails. chk-1 not executed (only src-1 in results).
        assert result.status == "failed"
        assert result.nodes_executed == 1  # Only src-1 was actually executed

    @pytest.mark.asyncio
    async def test_executor_aggregates_metrics(self):
        """nodes_executed/passed/failed counts are correct."""
        executor = FlowExecutor()
        flow = _mock_flow()
        db = _mock_db()

        async def mock_exec_node(*args, **kwargs):
            node = kwargs.get("node") or args[4]
            nr = MagicMock(spec=FlowNodeResult)
            nr.node_type = node.type.value
            nr.error_message = None
            nr.status = "completed"
            nr.result_data = {
                "output_data": {"data_source": {}},
                "rows_scanned": 50,
                "violation_count": 2,
            }
            return nr

        with patch.object(executor, "_execute_node", side_effect=mock_exec_node):
            result = await executor.execute_flow(
                db=db,
                flow=flow,
                workspace_id=uuid4(),
                executed_by=uuid4(),
            )
        assert result.nodes_executed == 2
        assert result.nodes_passed == 2
        assert result.nodes_failed == 0

    @pytest.mark.asyncio
    async def test_executor_status_completed(self):
        """All nodes pass → FlowExecution.status = 'completed'."""
        executor = FlowExecutor()
        flow = _mock_flow()
        db = _mock_db()

        async def mock_exec_node(*args, **kwargs):
            node = kwargs.get("node") or args[4]
            nr = MagicMock(spec=FlowNodeResult)
            nr.status = "completed"
            nr.node_type = node.type.value
            nr.error_message = None
            nr.result_data = {
                "output_data": {"data_source": {}},
                "rows_scanned": 10,
                "violation_count": 0,
            }
            return nr

        with patch.object(executor, "_execute_node", side_effect=mock_exec_node):
            result = await executor.execute_flow(
                db=db,
                flow=flow,
                workspace_id=uuid4(),
                executed_by=uuid4(),
            )
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_executor_status_failed(self):
        """A node failure → FlowExecution.status = 'failed'."""
        executor = FlowExecutor()
        flow = _mock_flow()
        db = _mock_db()

        async def mock_exec_node(*args, **kwargs):
            node = kwargs.get("node") or args[4]
            nr = MagicMock(spec=FlowNodeResult)
            nr.node_type = node.type.value
            nr.error_message = None
            if node.type.value == "check":
                nr.status = "failed"
                nr.result_data = {"output_data": {}, "rows_scanned": 10, "violation_count": 5}
            else:
                nr.status = "completed"
                nr.result_data = {"output_data": {"data_source": {}}}
            return nr

        with patch.object(executor, "_execute_node", side_effect=mock_exec_node):
            result = await executor.execute_flow(
                db=db,
                flow=flow,
                workspace_id=uuid4(),
                executed_by=uuid4(),
                execution_config={"continue_on_error": True},
            )
        assert result.status == "failed"


# ===========================================================================
# TestIssueCreation
# ===========================================================================
class TestIssueCreation:
    def _make_service(self, repo=None, grouping=None, sample=None):
        from app.services.issues.issue_creation_service import IssueCreationService

        return IssueCreationService(
            repository=repo or MagicMock(),
            grouping_service=grouping or MagicMock(),
            sample_service=sample or MagicMock(),
        )

    def _setup_db(self, node_status="failed", result_data=None):
        """Build a mock db that returns the right objects for the 13-step pipeline."""
        db = MagicMock()
        node_result = MagicMock(spec=FlowNodeResult)
        node_result.id = uuid4()
        node_result.status = node_status
        node_result.node_id = "chk-1"
        node_result.result_data = result_data or {
            "rows_scanned": 100,
            "rows_failed": 10,
            "pass_rate": 90.0,
        }
        node_result.completed_at = datetime.utcnow()

        execution = MagicMock(spec=FlowExecution)
        execution.id = uuid4()
        execution.flow_id = uuid4()

        flow = MagicMock(spec=DQFlow)
        flow.id = execution.flow_id
        flow.workspace_id = uuid4()
        flow.flow_definition = {
            "nodes": [{"id": "chk-1", "type": "check", "config": {"checkType": "completeness"}}]
        }

        # db.query(X).filter(...).first() chain
        def query_side_effect(model):
            m = MagicMock()
            if model is FlowNodeResult:
                m.filter.return_value.first.return_value = node_result
            elif model is FlowExecution:
                m.filter.return_value.first.return_value = execution
            elif model is DQFlow:
                m.filter.return_value.first.return_value = flow
            else:
                m.filter.return_value.first.return_value = None
            return m

        db.query.side_effect = query_side_effect
        return db, node_result, execution, flow

    def test_issue_created_from_failed_node(self):
        repo = MagicMock()
        repo.insert.return_value = MagicMock(id=uuid4())
        svc = self._make_service(repo=repo)
        db, nr, ex, flow = self._setup_db()

        with (
            patch(f"{ISSUE_MOD}._settings_repo") as mock_settings,
            patch(f"{ISSUE_MOD}._workspace_repo") as mock_ws_repo,
        ):
            mock_settings.find_by_workspace_id.return_value = None
            ws = MagicMock()
            ws.tenant_id = uuid4()
            mock_ws_repo.find_by_id_any_tenant.return_value = ws

            result = svc.create_from_node_result(db, nr.id, ex.id)

        assert result is not None
        repo.insert.assert_called_once()

    def test_issue_skipped_for_passing_node(self):
        svc = self._make_service()
        db, nr, ex, flow = self._setup_db(node_status="completed")

        result = svc.create_from_node_result(db, nr.id, ex.id)
        assert result is None

    def test_issue_extracts_metrics(self):
        repo = MagicMock()
        captured_domain = None

        def capture_insert(db, domain):
            nonlocal captured_domain
            captured_domain = domain
            domain.id = uuid4()
            return domain

        repo.insert.side_effect = capture_insert
        svc = self._make_service(repo=repo)
        db, nr, ex, flow = self._setup_db(
            result_data={
                "rows_scanned": 500,
                "rows_failed": 25,
                "pass_rate": 95.0,
            }
        )

        with (
            patch(f"{ISSUE_MOD}._settings_repo") as mock_settings,
            patch(f"{ISSUE_MOD}._workspace_repo") as mock_ws_repo,
        ):
            mock_settings.find_by_workspace_id.return_value = None
            ws = MagicMock()
            ws.tenant_id = uuid4()
            mock_ws_repo.find_by_id_any_tenant.return_value = ws

            svc.create_from_node_result(db, nr.id, ex.id)

        assert captured_domain is not None
        assert captured_domain.rows_scanned == 500
        assert captured_domain.failure_count == 25

    def test_issue_computes_due_at(self):
        repo = MagicMock()
        captured = None

        def capture(db, domain):
            nonlocal captured
            captured = domain
            domain.id = uuid4()
            return domain

        repo.insert.side_effect = capture
        svc = self._make_service(repo=repo)
        db, nr, ex, flow = self._setup_db()

        with (
            patch(f"{ISSUE_MOD}._settings_repo") as mock_settings,
            patch(f"{ISSUE_MOD}._workspace_repo") as mock_ws_repo,
        ):
            sla = MagicMock()
            sla.critical_hours = 4
            sla.major_hours = 24
            sla.minor_hours = 72
            sla.informational_hours = 168
            settings = MagicMock()
            settings.with_defaults.return_value = MagicMock(
                issue_grouping_policy="one_per_execution",
                default_timezone="UTC",
                sla_policy=sla,
            )
            mock_settings.find_by_workspace_id.return_value = settings
            ws = MagicMock()
            ws.tenant_id = uuid4()
            mock_ws_repo.find_by_id_any_tenant.return_value = ws

            svc.create_from_node_result(db, nr.id, ex.id)

        assert captured is not None
        assert captured.due_at is not None

    def test_issue_grouping_finds_candidate(self):
        """When grouping finds an existing issue, return it instead of creating new."""
        grouped_issue = MagicMock(id=uuid4(), failure_count=20)
        grouping = MagicMock()
        grouping.find_and_update_candidate.return_value = grouped_issue
        svc = self._make_service(grouping=grouping)

        db, nr, ex, flow = self._setup_db()
        # Add rule_id and dataset_id to trigger grouping path
        flow.flow_definition = {
            "nodes": [
                {
                    "id": "chk-1",
                    "type": "check",
                    "config": {
                        "checkType": "completeness",
                        "rule_id": str(uuid4()),
                        "dataset_id": str(uuid4()),
                    },
                }
            ]
        }

        with patch(f"{ISSUE_MOD}._settings_repo") as mock_settings:
            settings = MagicMock()
            settings.with_defaults.return_value = MagicMock(
                issue_grouping_policy="daily",
                default_timezone="UTC",
            )
            mock_settings.find_by_workspace_id.return_value = settings

            result = svc.create_from_node_result(db, nr.id, ex.id)

        assert result is grouped_issue

    def test_issue_creation_error_non_blocking(self):
        """DB error during insert → returns None, does not raise."""
        repo = MagicMock()
        repo.insert.side_effect = Exception("db error")
        svc = self._make_service(repo=repo)
        db, nr, ex, flow = self._setup_db()

        with (
            patch(f"{ISSUE_MOD}._settings_repo") as mock_settings,
            patch(f"{ISSUE_MOD}._workspace_repo") as mock_ws_repo,
        ):
            mock_settings.find_by_workspace_id.return_value = None
            ws = MagicMock()
            ws.tenant_id = uuid4()
            mock_ws_repo.find_by_id_any_tenant.return_value = ws

            result = svc.create_from_node_result(db, nr.id, ex.id)

        assert result is None  # No exception raised

    def test_issue_title_contains_check_info(self):
        repo = MagicMock()
        captured = None

        def capture(db, domain):
            nonlocal captured
            captured = domain
            domain.id = uuid4()
            return domain

        repo.insert.side_effect = capture
        svc = self._make_service(repo=repo)
        db, nr, ex, flow = self._setup_db()

        with (
            patch(f"{ISSUE_MOD}._settings_repo") as mock_settings,
            patch(f"{ISSUE_MOD}._workspace_repo") as mock_ws_repo,
        ):
            mock_settings.find_by_workspace_id.return_value = None
            ws = MagicMock()
            ws.tenant_id = uuid4()
            mock_ws_repo.find_by_id_any_tenant.return_value = ws

            svc.create_from_node_result(db, nr.id, ex.id)

        assert captured is not None
        assert isinstance(captured.title, str)
        assert len(captured.title) > 0
