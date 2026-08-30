"""
F120 — Dataset Profiling Tests (F121)
======================================

Tests for the DataProfiler service used by the dataset profiling endpoint.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pandas as pd
import pytest
from app.services.ingestion.profiler import DataProfiler


class TestDataProfiler:
    def setup_method(self):
        self.profiler = DataProfiler()

    def test_profile_empty_dataframe(self):
        df = pd.DataFrame()
        result = self.profiler.profile_dataframe(df)
        assert result["total_rows"] == 0
        assert result["total_columns"] == 0
        assert result["columns"] == []

    def test_profile_numeric_column(self):
        df = pd.DataFrame({"amount": [10, 20, 30, None, 50]})
        result = self.profiler.profile_dataframe(df)
        assert result["total_columns"] == 1
        col = result["columns"][0]
        assert col["name"] == "amount"
        assert col["null_count"] == 1
        assert col["null_percentage"] == pytest.approx(20.0)
        assert col["unique_count"] == 4
        assert col["min_value"] is not None
        assert col["max_value"] is not None

    def test_profile_string_column(self):
        df = pd.DataFrame({"city": ["NYC", "LA", "NYC", "Chicago", None]})
        result = self.profiler.profile_dataframe(df)
        col = result["columns"][0]
        assert col["name"] == "city"
        assert col["null_count"] == 1
        assert col["unique_count"] == 3

    def test_profile_with_actual_row_count(self):
        df = pd.DataFrame({"x": [1, 2, 3]})
        result = self.profiler.profile_dataframe(df, actual_row_count=1000000)
        assert result["total_rows"] == 1000000

    def test_profile_multiple_columns(self):
        df = pd.DataFrame(
            {
                "id": range(100),
                "name": [f"user_{i}" for i in range(100)],
                "score": [i * 1.5 for i in range(100)],
            }
        )
        result = self.profiler.profile_dataframe(df)
        assert result["total_columns"] == 3
        assert len(result["columns"]) == 3
        names = {c["name"] for c in result["columns"]}
        assert names == {"id", "name", "score"}

    def test_profile_all_nulls_column(self):
        df = pd.DataFrame({"empty": [None, None, None]})
        result = self.profiler.profile_dataframe(df)
        col = result["columns"][0]
        assert col["null_percentage"] == pytest.approx(100.0)
        assert col["unique_count"] == 0

    def test_profiled_at_present(self):
        df = pd.DataFrame({"x": [1]})
        result = self.profiler.profile_dataframe(df)
        assert "profiled_at" in result
        assert result["profiled_at"] is not None

    def test_suggested_checks_generated(self):
        df = pd.DataFrame({"email": ["a@b.com", None, "c@d.com", None, None]})
        result = self.profiler.profile_dataframe(df)
        col = result["columns"][0]
        # High null rate should trigger a null check suggestion
        assert isinstance(col["suggested_checks"], list)
