"""P03 — Temporal and inter-record consistency types."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


# ── Temporal ────────────────────────────────────────────────────


class TestTemporalSQL:
    def test_default_gte_operator(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "end_date",
            "",
            "",
            {
                "consistency_type": "temporal",
                "comparison_column": "start_date",
            },
        )
        assert ">=" in r["compiled_sql"]
        assert "end_date" in r["compiled_sql"]
        assert "start_date" in r["compiled_sql"]
        assert "total_rows" in r["compiled_sql"]

    @pytest.mark.parametrize("op", [">", "<", "<=", "="])
    def test_custom_operator(self, compiler, op):
        r = compiler._compile_consistency_rule(
            "t",
            "a",
            "",
            "",
            {
                "consistency_type": "temporal",
                "comparison_column": "b",
                "operator": op,
            },
        )
        assert op in r["compiled_sql"]

    def test_null_skip(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "a",
            "",
            "",
            {
                "consistency_type": "temporal",
                "comparison_column": "b",
                "null_handling": "skip",
            },
        )
        assert "IS NOT NULL" in r["compiled_sql"]

    def test_null_pass(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "a",
            "",
            "",
            {
                "consistency_type": "temporal",
                "comparison_column": "b",
                "null_handling": "pass",
            },
        )
        assert "COALESCE" in r["compiled_sql"]

    def test_null_fail_no_coalesce(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "a",
            "",
            "",
            {
                "consistency_type": "temporal",
                "comparison_column": "b",
                "null_handling": "fail",
            },
        )
        assert "COALESCE" not in r["compiled_sql"]
        assert "IS NOT NULL" not in r["compiled_sql"]

    def test_filter_expression(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "a",
            "",
            "",
            {
                "consistency_type": "temporal",
                "comparison_column": "b",
                "filter_expression": "active = true",
            },
        )
        assert "active" in r["compiled_sql"]

    def test_violation_sql(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "end_date",
            "",
            "",
            {
                "consistency_type": "temporal",
                "comparison_column": "start_date",
            },
        )
        assert "<" in r["violation_sql"]  # inverse of >=
        assert "FROM t" in r["violation_sql"]

    def test_spark_code(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "a",
            "",
            "",
            {
                "consistency_type": "temporal",
                "comparison_column": "b",
            },
        )
        assert "pyspark" in r["compiled_spark"]
        assert "col" in r["compiled_spark"]

    def test_missing_comparison_column(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "a",
            "",
            "",
            {
                "consistency_type": "temporal",
            },
        )
        assert "error" in r
        assert "comparison_column" in r["error"]

    def test_invalid_operator_defaults_gte(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "a",
            "",
            "",
            {
                "consistency_type": "temporal",
                "comparison_column": "b",
                "operator": "LIKE",
            },
        )
        # Invalid op should default to >=
        assert ">=" in r["compiled_sql"]


# ── Inter-Record ────────────────────────────────────────────────


class TestInterRecordSQL:
    def test_basic_group_consistency(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "inter_record",
                "group_by_columns": ["customer_id"],
                "comparison_columns": ["email"],
            },
        )
        assert "group_stats" in r["compiled_sql"]
        assert "customer_id" in r["compiled_sql"]
        assert "DISTINCT" in r["compiled_sql"]
        assert "email" in r["compiled_sql"]
        assert "total_rows" in r["compiled_sql"]

    def test_multiple_group_columns(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "inter_record",
                "group_by_columns": ["tenant_id", "customer_id"],
                "comparison_columns": ["email"],
            },
        )
        assert "tenant_id" in r["compiled_sql"]
        assert "customer_id" in r["compiled_sql"]

    def test_null_skip(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "inter_record",
                "group_by_columns": ["cid"],
                "comparison_columns": ["email"],
                "null_handling": "skip",
            },
        )
        assert "IS NOT NULL" in r["compiled_sql"]

    def test_filter_expression(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "inter_record",
                "group_by_columns": ["cid"],
                "comparison_columns": ["email"],
                "filter_expression": "status = 'active'",
            },
        )
        assert "active" in r["compiled_sql"]

    def test_violation_sql(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "inter_record",
                "group_by_columns": ["cid"],
                "comparison_columns": ["email"],
            },
        )
        assert "distinct_vals > 1" in r["violation_sql"]

    def test_spark_code(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "inter_record",
                "group_by_columns": ["cid"],
                "comparison_columns": ["email"],
            },
        )
        assert "pyspark" in r["compiled_spark"]
        assert "countDistinct" in r["compiled_spark"]

    def test_missing_group_by_columns(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "inter_record",
                "comparison_columns": ["email"],
            },
        )
        assert "error" in r
        assert "group_by_columns" in r["error"]

    def test_missing_comparison_columns(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "inter_record",
                "group_by_columns": ["cid"],
            },
        )
        assert "error" in r
        assert "comparison_columns" in r["error"]
