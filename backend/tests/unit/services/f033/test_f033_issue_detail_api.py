"""
F033 P02 — Unit tests for the enriched issue detail API endpoint.

Tests the GET /workspaces/{workspace_id}/issues/{issue_id} endpoint
serialisation logic. Because the endpoint module imports auth dependencies
that require extra packages (jose), we test the serialisation functions
by importing them lazily with mocked dependencies.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timezone
from decimal import Decimal
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from app.services.issues.issue_models import (
    AssigneeSummary,
    DatasetSummary,
    EnrichedIssueDetail,
    FlowExecutionSummary,
    NodeResultSummary,
    RuleSummary,
)

# ---------------------------------------------------------------------------
# Lazy import of serialisation helpers — mock out auth dependencies
# ---------------------------------------------------------------------------


def _import_serialisers():
    """Import the serialisation helpers without triggering the jose dep chain."""
    # Provide stubs for auth modules that would fail to import
    for mod_name in (
        "jose",
        "jose.jwt",
        "app.api.v1.dependencies.workspace_auth",
    ):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = MagicMock()

    import importlib

    mod = importlib.import_module("app.api.v1.endpoints.issues")
    return mod._serialize_enriched_detail, mod._serialize_detail


_serialize_enriched_detail, _serialize_detail = _import_serialisers()

_TENANT = uuid.uuid4()
_WORKSPACE = uuid.uuid4()
_ISSUE_ID = uuid.uuid4()
_RULE_ID = uuid.uuid4()
_DATASET_ID = uuid.uuid4()
_ASSIGNEE_ID = uuid.uuid4()
_EXECUTION_ID = uuid.uuid4()
_NODE_RESULT_ID = uuid.uuid4()
_NOW = datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC)


def _make_enriched(**overrides) -> EnrichedIssueDetail:
    defaults = dict(
        id=_ISSUE_ID,
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        flow_execution_id=_EXECUTION_ID,
        flow_node_result_id=_NODE_RESULT_ID,
        rule_id=_RULE_ID,
        dataset_id=_DATASET_ID,
        assignee_id=_ASSIGNEE_ID,
        issue_type="dq_check_failure",
        severity="major",
        status="open",
        title="Test issue",
        impact_summary="50 rows failed",
        failure_count=50,
        rows_scanned=100,
        pass_rate=Decimal("50.00"),
        due_at=_NOW,
        opened_at=_NOW,
        resolved_at=None,
        closed_at=None,
        updated_at=_NOW,
        created_at=_NOW,
        rule=RuleSummary(
            id=_RULE_ID,
            name="Completeness",
            category="completeness",
            severity="major",
            status="active",
            target_table="orders",
            target_columns=["email"],
        ),
        dataset=DatasetSummary(
            dataset_id=_DATASET_ID,
            dataset_name="orders_dataset",
            business_domain="finance",
            criticality="high",
            status="active",
        ),
        assignee=AssigneeSummary(
            id=_ASSIGNEE_ID,
            display_name="Jane Doe",
            email="jane@example.com",
        ),
        flow_execution=FlowExecutionSummary(
            id=_EXECUTION_ID,
            flow_name="Daily DQ Flow",
            status="completed",
            started_at=_NOW,
            completed_at=_NOW,
            nodes_total=5,
            nodes_passed=4,
            nodes_failed=1,
        ),
        node_result=NodeResultSummary(
            id=_NODE_RESULT_ID,
            node_id="check_email",
            node_type="check",
            status="failed",
            rows_scanned=100,
            rows_passed=50,
            rows_failed=50,
            pass_rate=50.0,
        ),
    )
    defaults.update(overrides)
    return EnrichedIssueDetail(**defaults)


class TestSerializeEnrichedDetail200:
    """Verify the enriched serialiser produces the expected JSON shape."""

    def test_get_enriched_detail_200(self):
        enriched = _make_enriched()
        result = _serialize_enriched_detail(enriched)

        # Flat fields
        assert result["id"] == str(_ISSUE_ID)
        assert result["title"] == "Test issue"
        assert result["severity"] == "major"

        # Nested context objects
        assert result["rule"]["name"] == "Completeness"
        assert result["dataset"]["dataset_name"] == "orders_dataset"
        assert result["assignee"]["display_name"] == "Jane Doe"
        assert result["flow_execution"]["flow_name"] == "Daily DQ Flow"
        assert result["node_result"]["node_id"] == "check_email"


class TestSerializeEnrichedDetail404:
    """When service returns None, handler raises 404 — test via serialiser for None contexts."""

    def test_get_enriched_detail_null_contexts(self):
        enriched = _make_enriched(
            rule=None,
            dataset=None,
            assignee=None,
            flow_execution=None,
            node_result=None,
        )
        result = _serialize_enriched_detail(enriched)

        assert result["rule"] is None
        assert result["dataset"] is None
        assert result["assignee"] is None
        assert result["flow_execution"] is None
        assert result["node_result"] is None


class TestSerializeEnrichedDetailBackwardCompat:
    """All flat FK fields must remain in the response for backward compatibility."""

    def test_get_enriched_detail_backward_compat(self):
        enriched = _make_enriched()
        result = _serialize_enriched_detail(enriched)

        # All flat FK IDs preserved alongside context objects
        assert result["flow_execution_id"] == str(_EXECUTION_ID)
        assert result["flow_node_result_id"] == str(_NODE_RESULT_ID)
        assert result["rule_id"] == str(_RULE_ID)
        assert result["dataset_id"] == str(_DATASET_ID)
        assert result["assignee_id"] == str(_ASSIGNEE_ID)

        # All scalar fields
        assert result["issue_type"] == "dq_check_failure"
        assert result["failure_count"] == 50
        assert result["pass_rate"] == 50.0


class TestSerializeEnrichedDetailNullContexts:
    """Null contexts are serialised as JSON null (not omitted from response)."""

    def test_null_contexts_present_as_none(self):
        enriched = _make_enriched(
            rule=None,
            dataset=None,
            assignee=None,
            assignee_id=None,
            flow_execution=None,
            node_result=None,
            flow_node_result_id=None,
        )
        result = _serialize_enriched_detail(enriched)

        # These keys MUST be present, set to None (not missing)
        assert "rule" in result
        assert "dataset" in result
        assert "assignee" in result
        assert "flow_execution" in result
        assert "node_result" in result
        assert result["rule"] is None
        assert result["assignee"] is None


class TestSerializeDetailUnchanged:
    """The original _serialize_detail still works for list/legacy paths."""

    def test_serialize_detail_basic(self):
        enriched = _make_enriched()
        result = _serialize_detail(enriched)

        assert result["id"] == str(_ISSUE_ID)
        assert result["title"] == "Test issue"
        # Original serialiser should NOT have context keys
        assert "rule" not in result
        assert "dataset" not in result
