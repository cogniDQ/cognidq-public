"""
F071 P03 — Unit tests: CheckNodeHandler

Tests _build_canonical_rule, validate_config, and execute error paths.

P03-01 .. P03-15  (15 tests)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.schemas.flow import NodeStatus
from app.services.flows.node_handlers.base import NodeExecutionContext, NodeExecutionResult


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
        node_id="chk-1",
        node_config={},
        execution_config={},
    )
    defaults.update(overrides)
    return NodeExecutionContext(**defaults)


def _handler():
    """Create a CheckNodeHandler with mocked dependencies."""
    with (
        patch("app.services.flows.node_handlers.check_node.RuleExecutor"),
        patch("app.services.flows.node_handlers.check_node.RuleCompiler"),
        patch("app.services.flows.node_handlers.check_node.SparkCheckExecutor"),
    ):
        from app.services.flows.node_handlers.check_node import CheckNodeHandler

        return CheckNodeHandler()


# ===================================================================
# _build_canonical_rule
# ===================================================================
class TestBuildCanonicalRule:
    def test_completeness_rule(self):
        """P03-01: completeness → dimension='completeness', entity='table.col'"""
        h = _handler()
        rule = h._build_canonical_rule(
            "completeness",
            {"columns": ["email"], "threshold": 95},
            "public",
            "users",
        )
        assert rule["dimension"] == "completeness"
        assert rule["entity"] == "users.email"

    def test_completeness_multi_column(self):
        """P03-02: multiple columns → parameters.columns preserved"""
        h = _handler()
        rule = h._build_canonical_rule(
            "completeness",
            {"columns": ["a", "b"]},
            "public",
            "t",
        )
        assert rule["parameters"]["columns"] == ["a", "b"]

    def test_validity_regex(self):
        """P03-03: pattern set → parameters.regex_pattern present"""
        h = _handler()
        rule = h._build_canonical_rule(
            "validity",
            {"columns": ["email"], "pattern": r"^.+@.+$"},
            "public",
            "t",
        )
        assert rule["parameters"]["regex_pattern"] == r"^.+@.+$"

    def test_validity_allowed_values(self):
        """P03-04: allowed_values set → parameters.allowed_values present"""
        h = _handler()
        rule = h._build_canonical_rule(
            "validity",
            {"columns": ["status"], "allowed_values": ["A", "B"]},
            "public",
            "t",
        )
        assert rule["parameters"]["allowed_values"] == ["A", "B"]

    def test_validity_range(self):
        """P03-05: min_value / max_value → parameters contain range"""
        h = _handler()
        rule = h._build_canonical_rule(
            "validity",
            {"columns": ["age"], "min_value": 1, "max_value": 150},
            "public",
            "t",
        )
        assert rule["parameters"]["min_value"] == 1
        assert rule["parameters"]["max_value"] == 150

    def test_uniqueness_rule(self):
        """P03-06: uniqueness → dimension='uniqueness'"""
        h = _handler()
        rule = h._build_canonical_rule(
            "uniqueness",
            {"columns": ["id"]},
            "public",
            "t",
        )
        assert rule["dimension"] == "uniqueness"

    def test_default_rule(self):
        """P03-07: unknown check_type → uses check_type as dimension"""
        h = _handler()
        rule = h._build_canonical_rule(
            "freshness",
            {"columns": ["updated_at"]},
            "public",
            "t",
        )
        assert rule["dimension"] == "freshness"

    def test_no_columns_uses_star(self):
        """P03-08: columns=[] → entity ends with '.*'"""
        h = _handler()
        rule = h._build_canonical_rule(
            "completeness",
            {"columns": []},
            "public",
            "t",
        )
        assert rule["entity"].endswith(".*")


# ===================================================================
# validate_config
# ===================================================================
class TestCheckValidateConfig:
    def test_missing_checktype_fails(self):
        """P03-09: No checkType → False"""
        h = _handler()
        assert h.validate_config({}) is False

    def test_rule_id_always_valid(self):
        """P03-10: rule_id present → True regardless of other fields"""
        h = _handler()
        assert h.validate_config({"checkType": "completeness", "rule_id": "r1"}) is True

    def test_completeness_needs_columns(self):
        """P03-11: completeness without columns → False"""
        h = _handler()
        assert h.validate_config({"checkType": "completeness"}) is False


# ===================================================================
# execute – error paths
# ===================================================================
class TestCheckExecute:
    @pytest.mark.asyncio
    async def test_no_checktype_returns_failed(self):
        """P03-12: No checkType in config or context → FAILED"""
        h = _handler()
        ctx = _make_context(node_config={}, check_type=None)
        result = await h.execute(ctx)
        assert result.status == NodeStatus.FAILED
        assert "checkType" in result.error_message

    @pytest.mark.asyncio
    async def test_missing_data_source_returns_failed(self):
        """P03-13: No data_source in input_data → FAILED"""
        h = _handler()
        ctx = _make_context(
            node_config={"checkType": "completeness", "columns": ["a"]},
            check_type="completeness",
            input_data={},  # no data_source
        )
        result = await h.execute(ctx)
        assert result.status == NodeStatus.FAILED
        assert "source" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_column_mismatch_all_invalid(self):
        """P03-14: All configured cols missing from source → FAILED with dataset change msg"""
        h = _handler()
        ctx = _make_context(
            node_config={"columns": ["col_x", "col_y"]},
            check_type="completeness",
            input_data={
                "data_source": {"id": "ds1", "type": "postgres"},
                "columns": ["real_a", "real_b"],
                "schema_name": "public",
                "table_name": "t",
            },
        )
        result = await h.execute(ctx)
        assert result.status == NodeStatus.FAILED
        assert "DATASET CHANGE" in result.error_message

    @pytest.mark.asyncio
    async def test_column_mismatch_partial(self):
        """P03-15: Some cols missing → FAILED with config error msg"""
        h = _handler()
        ctx = _make_context(
            node_config={"columns": ["real_a", "bad_col"]},
            check_type="completeness",
            input_data={
                "data_source": {"id": "ds1", "type": "postgres"},
                "columns": ["real_a", "real_b"],
                "schema_name": "public",
                "table_name": "t",
            },
        )
        result = await h.execute(ctx)
        assert result.status == NodeStatus.FAILED
        assert "COLUMN CONFIGURATION ERROR" in result.error_message
