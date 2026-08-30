"""P04 — Cross-table and aggregation consistency types."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


# ── Cross-Table ─────────────────────────────────────────────────


class TestCrossTableSQL:
    def test_basic_join(self, compiler):
        r = compiler._compile_consistency_rule(
            "crm.customers",
            "col",
            "",
            "",
            {
                "consistency_type": "cross_table",
                "comparison_dataset": "billing.customers",
                "join_keys": ["customer_id"],
                "comparison_columns": ["status"],
            },
        )
        assert "INNER JOIN" in r["compiled_sql"]
        assert "billing.customers" in r["compiled_sql"]
        assert "customer_id" in r["compiled_sql"]
        assert "status" in r["compiled_sql"]
        assert "total_rows" in r["compiled_sql"]

    def test_multiple_comparison_columns(self, compiler):
        r = compiler._compile_consistency_rule(
            "a_tbl",
            "col",
            "",
            "",
            {
                "consistency_type": "cross_table",
                "comparison_dataset": "b_tbl",
                "join_keys": ["id"],
                "comparison_columns": ["status", "email"],
            },
        )
        assert "status" in r["compiled_sql"]
        assert "email" in r["compiled_sql"]
        # Both should be in the match condition
        assert 'a."status" = b."status"' in r["compiled_sql"]
        assert 'a."email" = b."email"' in r["compiled_sql"]

    def test_multiple_join_keys(self, compiler):
        r = compiler._compile_consistency_rule(
            "a_tbl",
            "col",
            "",
            "",
            {
                "consistency_type": "cross_table",
                "comparison_dataset": "b_tbl",
                "join_keys": ["tenant_id", "customer_id"],
                "comparison_columns": ["status"],
            },
        )
        assert 'a."tenant_id" = b."tenant_id"' in r["compiled_sql"]
        assert 'a."customer_id" = b."customer_id"' in r["compiled_sql"]

    def test_filter_expression(self, compiler):
        r = compiler._compile_consistency_rule(
            "a_tbl",
            "col",
            "",
            "",
            {
                "consistency_type": "cross_table",
                "comparison_dataset": "b_tbl",
                "join_keys": ["id"],
                "comparison_columns": ["status"],
                "filter_expression": "a.active = true",
            },
        )
        assert "active" in r["compiled_sql"]

    def test_violation_sql(self, compiler):
        r = compiler._compile_consistency_rule(
            "a_tbl",
            "col",
            "",
            "",
            {
                "consistency_type": "cross_table",
                "comparison_dataset": "b_tbl",
                "join_keys": ["id"],
                "comparison_columns": ["status"],
            },
        )
        assert "NOT" in r["violation_sql"]
        assert "INNER JOIN" in r["violation_sql"]

    def test_spark_code(self, compiler):
        r = compiler._compile_consistency_rule(
            "a_tbl",
            "col",
            "",
            "",
            {
                "consistency_type": "cross_table",
                "comparison_dataset": "b_tbl",
                "join_keys": ["id"],
                "comparison_columns": ["status"],
            },
        )
        assert "pyspark" in r["compiled_spark"]
        assert "join" in r["compiled_spark"]

    def test_missing_comparison_dataset(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "cross_table",
                "join_keys": ["id"],
                "comparison_columns": ["status"],
            },
        )
        assert "error" in r
        assert "comparison_dataset" in r["error"]

    def test_missing_join_keys(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "cross_table",
                "comparison_dataset": "b",
                "comparison_columns": ["status"],
            },
        )
        assert "error" in r
        assert "join_keys" in r["error"]

    def test_missing_comparison_columns(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "cross_table",
                "comparison_dataset": "b",
                "join_keys": ["id"],
            },
        )
        assert "error" in r
        assert "comparison_columns" in r["error"]


# ── Aggregation ─────────────────────────────────────────────────


class TestAggregationSQL:
    def test_basic_sum(self, compiler):
        r = compiler._compile_consistency_rule(
            "line_items",
            "amount",
            "",
            "",
            {
                "consistency_type": "aggregation",
                "group_by_columns": ["order_id"],
                "aggregation_function": "SUM",
                "expected_column": "order_total",
            },
        )
        assert "SUM" in r["compiled_sql"]
        assert "order_id" in r["compiled_sql"]
        assert "order_total" in r["compiled_sql"]
        assert "agg" in r["compiled_sql"].lower()
        assert "header" in r["compiled_sql"].lower()

    @pytest.mark.parametrize("func", ["COUNT", "AVG", "MIN", "MAX"])
    def test_other_functions(self, compiler, func):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "aggregation",
                "group_by_columns": ["gid"],
                "aggregation_function": func,
                "expected_column": "expected",
            },
        )
        assert func in r["compiled_sql"]
        assert "error" not in r

    def test_tolerance_absolute(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "amount",
            "",
            "",
            {
                "consistency_type": "aggregation",
                "group_by_columns": ["oid"],
                "aggregation_function": "SUM",
                "expected_column": "total",
                "tolerance_type": "absolute",
                "tolerance_value": 0.5,
            },
        )
        assert "0.5" in r["compiled_sql"]
        assert "ABS" in r["compiled_sql"]

    def test_tolerance_percentage(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "amount",
            "",
            "",
            {
                "consistency_type": "aggregation",
                "group_by_columns": ["oid"],
                "aggregation_function": "SUM",
                "expected_column": "total",
                "tolerance_type": "percentage",
                "tolerance_value": 5.0,
            },
        )
        assert "NULLIF" in r["compiled_sql"]

    def test_tolerance_none(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "amount",
            "",
            "",
            {
                "consistency_type": "aggregation",
                "group_by_columns": ["oid"],
                "aggregation_function": "SUM",
                "expected_column": "total",
                "tolerance_type": "none",
            },
        )
        # exact match — no ABS
        assert "= (" in r["compiled_sql"] or ") = (" in r["compiled_sql"]

    def test_separate_header_table(self, compiler):
        r = compiler._compile_consistency_rule(
            "line_items",
            "amount",
            "",
            "",
            {
                "consistency_type": "aggregation",
                "group_by_columns": ["order_id"],
                "aggregation_function": "SUM",
                "expected_column": "order_total",
                "comparison_dataset": "orders",
            },
        )
        # header should come from orders, not line_items
        assert "FROM orders" in r["compiled_sql"]

    def test_filter_expression(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "amount",
            "",
            "",
            {
                "consistency_type": "aggregation",
                "group_by_columns": ["oid"],
                "aggregation_function": "SUM",
                "expected_column": "total",
                "filter_expression": "status = 'active'",
            },
        )
        assert "active" in r["compiled_sql"]

    def test_violation_sql(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "amount",
            "",
            "",
            {
                "consistency_type": "aggregation",
                "group_by_columns": ["oid"],
                "aggregation_function": "SUM",
                "expected_column": "total",
            },
        )
        assert "violation_sql" in r
        assert "expected_value" in r["violation_sql"]

    def test_spark_code(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "amount",
            "",
            "",
            {
                "consistency_type": "aggregation",
                "group_by_columns": ["oid"],
                "aggregation_function": "SUM",
                "expected_column": "total",
            },
        )
        assert "pyspark" in r["compiled_spark"]
        assert "computed_value" in r["compiled_spark"]

    def test_missing_group_by(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "aggregation",
                "aggregation_function": "SUM",
                "expected_column": "total",
            },
        )
        assert "error" in r
        assert "group_by_columns" in r["error"]

    def test_missing_aggregation_function(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "aggregation",
                "group_by_columns": ["gid"],
                "expected_column": "total",
            },
        )
        assert "error" in r
        assert "aggregation_function" in r["error"]

    def test_missing_expected_column(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "aggregation",
                "group_by_columns": ["gid"],
                "aggregation_function": "SUM",
            },
        )
        assert "error" in r
        assert "expected_column" in r["error"]

    def test_invalid_aggregation_function(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "aggregation",
                "group_by_columns": ["gid"],
                "aggregation_function": "MEDIAN",
                "expected_column": "total",
            },
        )
        assert "error" in r
        assert "Invalid" in r["error"]
