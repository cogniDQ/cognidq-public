"""
F071 P02 — Unit tests: Node handler base classes + SourceNodeHandler utilities

Tests NodeExecutionContext, NodeExecutionResult, BaseNodeHandler.handle_error,
SourceNodeHandler._sanitize_table_name, SourceNodeHandler.validate_config.

P02-01 .. P02-15  (15 tests)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from app.schemas.flow import NodeStatus
from app.services.flows.node_handlers.base import (
    BaseNodeHandler,
    NodeExecutionContext,
    NodeExecutionResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_db():
    return MagicMock()


def _make_context(**overrides):
    defaults = dict(
        db=_mock_db(),
        workspace_id=uuid.uuid4(),
        flow_id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
        node_id="node-1",
        node_config={"key": "val"},
        execution_config={"sample_size": 100},
    )
    defaults.update(overrides)
    return NodeExecutionContext(**defaults)


# Concrete subclass for testing handle_error (can't instantiate ABC directly)
class _StubHandler(BaseNodeHandler):
    async def execute(self, context):
        pass

    def validate_config(self, config):
        return True


# ===================================================================
# NODE EXECUTION CONTEXT
# ===================================================================
class TestNodeExecutionContext:
    def test_fields_stored(self):
        """P02-01"""
        db = _mock_db()
        org = uuid.uuid4()
        flow = uuid.uuid4()
        ex = uuid.uuid4()
        ctx = NodeExecutionContext(
            db=db,
            workspace_id=org,
            flow_id=flow,
            execution_id=ex,
            node_id="n1",
            node_config={"a": 1},
            execution_config={"b": 2},
            input_data={"c": 3},
            check_type="completeness",
        )
        assert ctx.db is db
        assert ctx.workspace_id == org
        assert ctx.flow_id == flow
        assert ctx.execution_id == ex
        assert ctx.node_id == "n1"
        assert ctx.node_config == {"a": 1}
        assert ctx.execution_config == {"b": 2}
        assert ctx.input_data == {"c": 3}
        assert ctx.check_type == "completeness"
        assert isinstance(ctx.started_at, datetime)

    def test_input_data_defaults_empty(self):
        """P02-02"""
        _make_context()
        # Default should be empty dict when input_data not passed
        ctx2 = NodeExecutionContext(
            db=_mock_db(),
            workspace_id=uuid.uuid4(),
            flow_id=uuid.uuid4(),
            execution_id=uuid.uuid4(),
            node_id="n1",
            node_config={},
            execution_config={},
        )
        assert ctx2.input_data == {}


# ===================================================================
# NODE EXECUTION RESULT
# ===================================================================
class TestNodeExecutionResult:
    def test_status_and_data(self):
        """P02-03"""
        r = NodeExecutionResult(
            status=NodeStatus.COMPLETED,
            result_data={"rows": 100},
            output_data={"table": "t1"},
        )
        assert r.status == NodeStatus.COMPLETED
        assert r.result_data == {"rows": 100}
        assert r.output_data == {"table": "t1"}
        assert isinstance(r.completed_at, datetime)

    def test_defaults(self):
        """P02-04"""
        r = NodeExecutionResult(status=NodeStatus.PENDING)
        assert r.result_data == {}
        assert r.output_data == {}
        assert r.error_message is None


# ===================================================================
# HANDLE ERROR
# ===================================================================
class TestHandleError:
    def test_produces_failed_result(self):
        """P02-05"""
        handler = _StubHandler()
        ctx = _make_context()
        result = handler.handle_error(ValueError("test error"), ctx)
        assert result.status == NodeStatus.FAILED

    def test_error_details_include_traceback(self):
        """P02-06"""
        handler = _StubHandler()
        ctx = _make_context()
        result = handler.handle_error(RuntimeError("oops"), ctx)
        assert result.error_details["error_type"] == "RuntimeError"
        assert "traceback" in result.error_details
        assert result.error_details["node_id"] == "node-1"

    def test_empty_str_error(self):
        """P02-07: When str(error) is empty, uses type name fallback"""
        handler = _StubHandler()
        ctx = _make_context()
        # Create an exception with empty message
        err = RuntimeError("")
        result = handler.handle_error(err, ctx)
        assert result.error_message  # Should not be empty
        assert "RuntimeError" in result.error_message


# ===================================================================
# SANITIZE TABLE NAME
# ===================================================================
class TestSanitizeTableName:
    def _sanitize(self, name):
        from app.services.flows.node_handlers.source_node import SourceNodeHandler

        return SourceNodeHandler._sanitize_table_name(name)

    def test_removes_extension(self):
        """P02-08"""
        assert self._sanitize("data.csv") == "data"

    def test_replaces_special_chars(self):
        """P02-09"""
        result = self._sanitize("my-file (1).csv")
        assert "-" not in result
        assert "(" not in result
        assert " " not in result
        # Should only contain alphanumeric and underscore
        assert all(c.isalnum() or c == "_" for c in result)

    def test_numeric_prefix_gets_table_prefix(self):
        """P02-10"""
        result = self._sanitize("2024_sales.csv")
        assert result.startswith("table_")

    def test_empty_becomes_file_data(self):
        """P02-11: Empty name (after sanitization) falls back to 'file_data'"""
        result = self._sanitize("")
        assert result == "file_data"


# ===================================================================
# SOURCE VALIDATE CONFIG
# ===================================================================
class TestSourceValidateConfig:
    def _handler(self):
        from app.services.flows.node_handlers.source_node import SourceNodeHandler

        return SourceNodeHandler()

    def test_file_source_valid(self):
        """P02-12"""
        h = self._handler()
        assert h.validate_config({"file_path": "/data/test.csv"}) is True

    def test_file_id_valid(self):
        """P02-13"""
        h = self._handler()
        assert h.validate_config({"file_id": "abc-123"}) is True

    def test_db_source_requires_all_fields(self):
        """P02-14"""
        h = self._handler()
        assert h.validate_config({"data_source_id": "x", "schema_name": "public"}) is False

    def test_full_db_config_valid(self):
        """P02-15"""
        h = self._handler()
        assert (
            h.validate_config(
                {
                    "data_source_id": "x",
                    "schema_name": "public",
                    "table_name": "orders",
                }
            )
            is True
        )
