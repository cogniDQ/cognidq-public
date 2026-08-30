"""P02 — Intra-record and formula consistency types."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


# ── Intra-Record ────────────────────────────────────────────────


class TestIntraRecordSQL:
    def test_basic_sql_structure(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "intra_record",
                "rule_expression": "\"country\" = 'US' AND \"currency\" = 'USD'",
            },
        )
        assert "total_rows" in r["compiled_sql"]
        assert "consistent_rows" in r["compiled_sql"]
        assert "inconsistent_rows" in r["compiled_sql"]
        assert "country" in r["compiled_sql"]
        assert "FROM t" in r["compiled_sql"]

    def test_null_skip(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "intra_record",
                "rule_expression": '"a" = "b"',
                "null_handling": "skip",
                "columns": ["a", "b"],
            },
        )
        assert "IS NOT NULL" in r["compiled_sql"]

    def test_null_fail_default(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "intra_record",
                "rule_expression": '"a" = "b"',
            },
        )
        assert "IS NOT NULL" not in r["compiled_sql"]

    def test_null_pass(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "intra_record",
                "rule_expression": '"a" = "b"',
                "null_handling": "pass",
            },
        )
        assert "COALESCE" in r["compiled_sql"]

    def test_filter_expression(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "intra_record",
                "rule_expression": '"a" = "b"',
                "filter_expression": "status = 'active'",
            },
        )
        assert "status" in r["compiled_sql"]
        assert "active" in r["compiled_sql"]

    def test_violation_sql(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "intra_record",
                "rule_expression": '"a" = "b"',
            },
        )
        assert "NOT" in r["violation_sql"]
        assert "FROM t" in r["violation_sql"]

    def test_spark_code(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "intra_record",
                "rule_expression": '"a" = "b"',
            },
        )
        assert "pyspark" in r["compiled_spark"]
        assert "expr" in r["compiled_spark"]

    def test_missing_rule_expression_error(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "intra_record",
            },
        )
        assert "error" in r
        assert "rule_expression" in r["error"]


class TestIntraRecordBackwardCompat:
    def test_reference_column_operator(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "price",
            "",
            "",
            {
                "consistency_type": "intra_record",
                "reference_column": "expected_price",
                "operator": "=",
            },
        )
        assert "error" not in r
        assert "price" in r["compiled_sql"]
        assert "expected_price" in r["compiled_sql"]

    def test_reference_column_default_operator(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "a",
            "",
            "",
            {
                "consistency_type": "intra_record",
                "reference_column": "b",
            },
        )
        assert "error" not in r
        assert '= "b"' in r["compiled_sql"] or '"b"' in r["compiled_sql"]


# ── Formula ─────────────────────────────────────────────────────


class TestFormulaSQL:
    def test_basic_sql_structure(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "formula",
                "rule_expression": '"subtotal" + "tax"',
                "expected_column": "total",
            },
        )
        assert "total_rows" in r["compiled_sql"]
        assert "consistent_rows" in r["compiled_sql"]
        assert "total" in r["compiled_sql"]
        assert "subtotal" in r["compiled_sql"]

    def test_absolute_tolerance(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "formula",
                "rule_expression": '"a" + "b"',
                "expected_column": "c",
                "tolerance_type": "absolute",
                "tolerance_value": 0.5,
            },
        )
        assert "0.5" in r["compiled_sql"]
        assert "ABS" in r["compiled_sql"]

    def test_percentage_tolerance(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "formula",
                "rule_expression": '"a" + "b"',
                "expected_column": "c",
                "tolerance_type": "percentage",
                "tolerance_value": 2.0,
            },
        )
        assert "NULLIF" in r["compiled_sql"]
        assert "2.0" in r["compiled_sql"]

    def test_no_tolerance_exact(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "formula",
                "rule_expression": '"a" + "b"',
                "expected_column": "c",
                "tolerance_type": "none",
            },
        )
        assert "ABS" not in r["compiled_sql"]

    def test_null_skip(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "formula",
                "rule_expression": '"a" + "b"',
                "expected_column": "c",
                "null_handling": "skip",
            },
        )
        assert "IS NOT NULL" in r["compiled_sql"]

    def test_null_pass(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "formula",
                "rule_expression": '"a" + "b"',
                "expected_column": "c",
                "null_handling": "pass",
            },
        )
        assert "COALESCE" in r["compiled_sql"]

    def test_filter_expression(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "formula",
                "rule_expression": '"a" + "b"',
                "expected_column": "c",
                "filter_expression": "active = true",
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
                "consistency_type": "formula",
                "rule_expression": '"a" + "b"',
                "expected_column": "c",
            },
        )
        assert "FROM t" in r["violation_sql"]

    def test_spark_code(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "formula",
                "rule_expression": '"a" + "b"',
                "expected_column": "c",
            },
        )
        assert "pyspark" in r["compiled_spark"]
        assert "_expected" in r["compiled_spark"]

    def test_missing_rule_expression_error(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "formula",
                "expected_column": "c",
            },
        )
        assert "error" in r
        assert "rule_expression" in r["error"]

    def test_missing_expected_column_error(self, compiler):
        r = compiler._compile_consistency_rule(
            "t",
            "col",
            "",
            "",
            {
                "consistency_type": "formula",
                "rule_expression": '"a" + "b"',
            },
        )
        assert "error" in r
        assert "expected_column" in r["error"]
