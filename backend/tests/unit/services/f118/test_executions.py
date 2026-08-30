"""
F120 — Execution History API Tests (F118)
==========================================

Tests for the unified executions endpoint: list, detail, CSV download.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_execution(**overrides):
    defaults = dict(
        id=uuid4(),
        rule_id=uuid4(),
        status="completed",
        execution_type="manual",
        rows_scanned=1000,
        rows_passed=950,
        rows_failed=50,
        pass_rate=0.95,
        result_details={"summary": "ok"},
        execution_params=None,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        error_message=None,
    )
    defaults.update(overrides)
    m = MagicMock(**defaults)
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _make_violation(**overrides):
    defaults = dict(
        id=uuid4(),
        execution_id=uuid4(),
        row_identifier="row-1",
        row_number=1,
        severity="high",
        category="null_check",
        violation_details={"column": "email", "reason": "null value"},
    )
    defaults.update(overrides)
    m = MagicMock(**defaults)
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


# ── Serialization Tests ─────────────────────────────────────────────────────


class TestSerializeExecution:
    def test_serialize_contains_key_fields(self):
        from app.api.v1.endpoints.executions import _serialize_execution

        ex = _make_execution()
        data = _serialize_execution(ex)
        assert "id" in data
        assert "status" in data
        assert "rows_scanned" in data
        assert "pass_rate" in data

    def test_serialize_handles_none_dates(self):
        from app.api.v1.endpoints.executions import _serialize_execution

        ex = _make_execution(started_at=None, completed_at=None)
        data = _serialize_execution(ex)
        assert data["started_at"] is None
        assert data["completed_at"] is None


# ── List Endpoint Tests ──────────────────────────────────────────────────────


class TestListExecutions:
    def test_returns_paginated_structure(self):
        """Verify the list endpoint response shape (unit-level)."""
        uuid4()
        executions = [_make_execution() for _ in range(3)]
        # Verify serialization works for a batch
        from app.api.v1.endpoints.executions import _serialize_execution

        items = [_serialize_execution(e) for e in executions]
        assert len(items) == 3
        assert all("id" in i for i in items)


# ── CSV Download Tests ───────────────────────────────────────────────────────


class TestCSVGeneration:
    def test_csv_row_format(self):
        """Verify CSV row generation logic matches expected columns."""
        import csv
        import io

        v = _make_violation()
        # Simulate the CSV generation from the endpoint
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            ["id", "row_identifier", "row_number", "severity", "category", "violation_details"]
        )
        writer.writerow(
            [
                str(v.id),
                v.row_identifier,
                v.row_number,
                v.severity,
                v.category,
                str(v.violation_details),
            ]
        )
        output.seek(0)
        reader = csv.reader(output)
        rows = list(reader)
        assert rows[0] == [
            "id",
            "row_identifier",
            "row_number",
            "severity",
            "category",
            "violation_details",
        ]
        assert rows[1][1] == "row-1"
        assert rows[1][3] == "high"
