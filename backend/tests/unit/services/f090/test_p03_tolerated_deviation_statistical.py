"""P03 — Tolerated Deviation & Statistical Tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _tol_params(**overrides):
    base = {
        "accuracy_type": "tolerated_deviation",
        "reference_dataset": "ref.locations",
        "reference_column": "ref_lat",
        "join_keys": ["store_id"],
        "tolerance_type": "absolute",
        "tolerance_value": 0.001,
        "threshold_pass": 95,
    }
    base.update(overrides)
    return base


def _stat_params(method="zscore", **overrides):
    base = {
        "accuracy_type": "statistical",
        "statistical_method": method,
        "threshold_pass": 95,
    }
    base.update(overrides)
    return base


def _compile(compiler, column, params):
    return compiler.compile_rule(
        {
            "dimension": "accuracy",
            "entity": f"data.{column}",
            "condition": "",
            "expectation": "95%",
            "parameters": params,
        },
        target_table="data",
    )


class TestToleratedDeviation:
    def test_absolute_tolerance(self, compiler):
        result = _compile(compiler, "lat", _tol_params())
        sql = result["compiled_sql"]
        assert "ABS" in sql
        assert "<= 0.001" in sql

    def test_percentage_tolerance(self, compiler):
        result = _compile(
            compiler, "price", _tol_params(tolerance_type="percentage", tolerance_value=5.0)
        )
        sql = result["compiled_sql"]
        assert "NULLIF" in sql
        assert "<= 5.0" in sql

    def test_missing_tolerance_error(self, compiler):
        result = _compile(compiler, "lat", _tol_params(tolerance_type="none", tolerance_value=None))
        assert "error" in result
        assert "tolerated_deviation requires" in result["error"]

    def test_filter(self, compiler):
        result = _compile(compiler, "lat", _tol_params(filter_expression="active = true"))
        assert "active = true" in result["compiled_sql"]

    def test_spark(self, compiler):
        result = _compile(compiler, "lat", _tol_params())
        assert "pyspark" in result["compiled_spark"]

    def test_violation_sql(self, compiler):
        result = _compile(compiler, "lat", _tol_params())
        assert "SELECT a.*" in result["violation_sql"]

    def test_null_handling_skip(self, compiler):
        result = _compile(compiler, "lat", _tol_params(null_handling="skip"))
        assert 'a."lat" IS NOT NULL' in result["compiled_sql"]

    def test_invalid_tolerance_type_error(self, compiler):
        result = _compile(compiler, "lat", _tol_params(tolerance_type="distance"))
        assert "error" in result
        assert "Invalid tolerance_type" in result["error"]


class TestStatisticalZscore:
    def test_basic_zscore_sql(self, compiler):
        result = _compile(compiler, "salary", _stat_params())
        sql = result["compiled_sql"]
        assert "AVG" in sql
        assert "STDDEV" in sql
        assert "stats" in sql.lower()
        assert "CROSS JOIN" in sql

    def test_default_threshold_3(self, compiler):
        result = _compile(compiler, "salary", _stat_params())
        assert "<= 3.0" in result["compiled_sql"]

    def test_custom_threshold(self, compiler):
        result = _compile(compiler, "salary", _stat_params(statistical_threshold=2.0))
        assert "<= 2.0" in result["compiled_sql"]

    def test_filter(self, compiler):
        result = _compile(compiler, "salary", _stat_params(filter_expression="dept = 'eng'"))
        assert "dept = 'eng'" in result["compiled_sql"]

    def test_spark(self, compiler):
        result = _compile(compiler, "salary", _stat_params())
        spark = result["compiled_spark"]
        assert "avg" in spark
        assert "stddev" in spark

    def test_violation_sql(self, compiler):
        result = _compile(compiler, "salary", _stat_params())
        assert "SELECT t.*" in result["violation_sql"]
        assert "> 3.0" in result["violation_sql"]

    def test_null_handling_skip(self, compiler):
        result = _compile(compiler, "salary", _stat_params(null_handling="skip"))
        assert '"salary" IS NOT NULL' in result["compiled_sql"]

    def test_null_handling_pass(self, compiler):
        result = _compile(compiler, "salary", _stat_params(null_handling="pass"))
        sql = result["compiled_sql"]
        assert '"salary" IS NULL OR' in sql

    def test_verified_rows_equals_total(self, compiler):
        result = _compile(compiler, "salary", _stat_params())
        sql = result["compiled_sql"]
        assert "COUNT(*) AS verified_rows" in sql
        assert "0 AS unverifiable_rows" in sql


class TestStatisticalIqr:
    def test_basic_iqr_sql(self, compiler):
        result = _compile(compiler, "amount", _stat_params("iqr"))
        sql = result["compiled_sql"]
        assert "percentile_cont(0.25)" in sql
        assert "percentile_cont(0.75)" in sql

    def test_default_multiplier_1_5(self, compiler):
        result = _compile(compiler, "amount", _stat_params("iqr"))
        assert "1.5" in result["compiled_sql"]

    def test_custom_multiplier(self, compiler):
        result = _compile(compiler, "amount", _stat_params("iqr", statistical_threshold=2.0))
        assert "2.0" in result["compiled_sql"]

    def test_filter(self, compiler):
        result = _compile(compiler, "amount", _stat_params("iqr", filter_expression="year = 2025"))
        assert "year = 2025" in result["compiled_sql"]

    def test_spark(self, compiler):
        result = _compile(compiler, "amount", _stat_params("iqr"))
        assert "percentile_approx" in result["compiled_spark"]

    def test_violation_sql(self, compiler):
        result = _compile(compiler, "amount", _stat_params("iqr"))
        assert "SELECT t.*" in result["violation_sql"]

    def test_null_handling_pass(self, compiler):
        result = _compile(compiler, "amount", _stat_params("iqr", null_handling="pass"))
        sql = result["compiled_sql"]
        assert '"amount" IS NULL OR' in sql


class TestStatisticalErrors:
    def test_invalid_method_error(self, compiler):
        result = _compile(compiler, "x", _stat_params(statistical_method="invalid"))
        assert "error" in result
        assert "Invalid statistical_method" in result["error"]

    def test_missing_column_error(self, compiler):
        result = compiler.compile_rule(
            {
                "dimension": "accuracy",
                "entity": "t.",
                "condition": "",
                "expectation": "95%",
                "parameters": {
                    "accuracy_type": "statistical",
                    "statistical_method": "zscore",
                    "threshold_pass": 95,
                },
            },
            target_table="t",
        )
        assert "error" in result
        assert "target column" in result["error"]
