"""P02 — Reference Comparison & Trusted Source Tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _ref_params(**overrides):
    base = {
        "accuracy_type": "reference_comparison",
        "reference_dataset": "master.products",
        "reference_column": "ref_price",
        "join_keys": ["product_id"],
        "threshold_pass": 95,
    }
    base.update(overrides)
    return base


def _compile(compiler, column="price", **overrides):
    params = _ref_params(**overrides)
    return compiler.compile_rule(
        {
            "dimension": "accuracy",
            "entity": f"orders.{column}",
            "condition": "",
            "expectation": "95%",
            "parameters": params,
        },
        target_table="orders",
    )


class TestReferenceComparison:
    def test_basic_sql_has_left_join(self, compiler):
        result = _compile(compiler)
        sql = result["compiled_sql"]
        assert "LEFT JOIN master.products" in sql
        assert 'a."product_id" = b."product_id"' in sql

    def test_verified_and_unverifiable_counting(self, compiler):
        result = _compile(compiler)
        sql = result["compiled_sql"]
        assert "verified_rows" in sql
        assert "unverifiable_rows" in sql
        assert "accurate_rows" in sql
        assert "inaccurate_rows" in sql

    def test_exact_match_default(self, compiler):
        result = _compile(compiler)
        sql = result["compiled_sql"]
        # Default tolerance_type is "none" → exact match
        assert '(a."price") = (b."ref_price")' in sql

    def test_filter_expression(self, compiler):
        result = _compile(compiler, filter_expression="status = 'active'")
        assert "status = 'active'" in result["compiled_sql"]

    def test_spark_code(self, compiler):
        result = _compile(compiler)
        spark = result["compiled_spark"]
        assert "join" in spark
        assert "left" in spark
        assert "accurate_rows" in spark

    def test_violation_sql(self, compiler):
        result = _compile(compiler)
        assert "SELECT a.*" in result["violation_sql"]
        assert "IS NOT NULL" in result["violation_sql"]

    def test_missing_reference_dataset_error(self, compiler):
        result = _compile(compiler, reference_dataset=None)
        assert "error" in result
        assert "reference_dataset" in result["error"]

    def test_missing_join_keys_error(self, compiler):
        result = _compile(compiler, join_keys=None)
        assert "error" in result
        assert "join_keys" in result["error"]

    def test_null_handling_skip(self, compiler):
        result = _compile(compiler, null_handling="skip")
        assert 'a."price" IS NOT NULL' in result["compiled_sql"]

    def test_null_handling_pass(self, compiler):
        result = _compile(compiler, null_handling="pass")
        sql = result["compiled_sql"]
        assert 'a."price" IS NULL OR' in sql

    def test_null_handling_fail_default(self, compiler):
        result = _compile(compiler)
        sql = result["compiled_sql"]
        # No IS NULL OR handling
        assert "IS NULL OR" not in sql or 'b."ref_price" IS NOT NULL' in sql

    def test_multiple_join_keys(self, compiler):
        result = _compile(compiler, join_keys=["product_id", "region"])
        sql = result["compiled_sql"]
        assert 'a."product_id" = b."product_id"' in sql
        assert 'a."region" = b."region"' in sql

    def test_reference_column_defaults_to_column(self, compiler):
        """When reference_column is not specified, defaults to the target column name."""
        params = {
            "accuracy_type": "reference_comparison",
            "reference_dataset": "ref_table",
            "join_keys": ["id"],
            "threshold_pass": 95,
        }
        result = compiler.compile_rule(
            {
                "dimension": "accuracy",
                "entity": "t.price",
                "condition": "",
                "expectation": "95%",
                "parameters": params,
            },
            target_table="t",
        )
        sql = result["compiled_sql"]
        assert 'b."price"' in sql


class TestTrustedSource:
    def test_trusted_source_basic_sql(self, compiler):
        result = _compile(compiler, accuracy_type="trusted_source")
        sql = result["compiled_sql"]
        assert "LEFT JOIN" in sql
        assert "accurate_rows" in sql

    def test_trusted_source_same_handler_as_reference(self, compiler):
        ref_result = _compile(compiler, accuracy_type="reference_comparison")
        ts_result = _compile(compiler, accuracy_type="trusted_source")
        # Same SQL structure (may differ in accuracy_type param routing but same SQL output)
        assert ref_result["compiled_sql"] == ts_result["compiled_sql"]

    def test_trusted_source_with_tolerance(self, compiler):
        result = _compile(
            compiler, accuracy_type="trusted_source", tolerance_type="absolute", tolerance_value=0.5
        )
        assert "ABS" in result["compiled_sql"]

    def test_trusted_source_with_filter(self, compiler):
        result = _compile(
            compiler, accuracy_type="trusted_source", filter_expression="active = true"
        )
        assert "active = true" in result["compiled_sql"]

    def test_trusted_source_violation_sql(self, compiler):
        result = _compile(compiler, accuracy_type="trusted_source")
        assert result["violation_sql"]
        assert "SELECT a.*" in result["violation_sql"]

    def test_trusted_source_spark(self, compiler):
        result = _compile(compiler, accuracy_type="trusted_source")
        assert "pyspark" in result["compiled_spark"]
