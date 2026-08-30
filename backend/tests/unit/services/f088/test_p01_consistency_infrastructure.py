"""P01 — Consistency infrastructure: constants, dispatcher, helpers, type inference."""

import re

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


# ── Constants ───────────────────────────────────────────────────


class TestValidConsistencyTypes:
    def test_has_six_types(self):
        assert len(RuleCompiler.VALID_CONSISTENCY_TYPES) == 6

    @pytest.mark.parametrize(
        "t", ["intra_record", "formula", "temporal", "inter_record", "cross_table", "aggregation"]
    )
    def test_type_present(self, t):
        assert t in RuleCompiler.VALID_CONSISTENCY_TYPES


class TestValidAggregationFunctions:
    def test_has_five(self):
        assert len(RuleCompiler.VALID_AGGREGATION_FUNCTIONS) == 5

    @pytest.mark.parametrize("f", ["SUM", "COUNT", "AVG", "MIN", "MAX"])
    def test_func_present(self, f):
        assert f in RuleCompiler.VALID_AGGREGATION_FUNCTIONS


class TestValidTemporalOperators:
    def test_has_five(self):
        assert len(RuleCompiler.VALID_TEMPORAL_OPERATORS) == 5

    @pytest.mark.parametrize("o", [">=", ">", "<=", "<", "="])
    def test_op_present(self, o):
        assert o in RuleCompiler.VALID_TEMPORAL_OPERATORS


# ── Dispatcher ──────────────────────────────────────────────────


class TestDispatcherRouting:
    @pytest.mark.parametrize(
        "ctype",
        ["intra_record", "formula", "temporal", "inter_record", "cross_table", "aggregation"],
    )
    def test_routes_valid_type(self, compiler, ctype):
        # Each type needs enough params to not error on missing-required
        param_sets = {
            "intra_record": {"consistency_type": ctype, "rule_expression": '"a" = "b"'},
            "formula": {
                "consistency_type": ctype,
                "rule_expression": '"a" + "b"',
                "expected_column": "total",
            },
            "temporal": {"consistency_type": ctype, "comparison_column": "end_date"},
            "inter_record": {
                "consistency_type": ctype,
                "group_by_columns": ["cust_id"],
                "comparison_columns": ["email"],
            },
            "cross_table": {
                "consistency_type": ctype,
                "comparison_dataset": "other.tbl",
                "join_keys": ["id"],
                "comparison_columns": ["status"],
            },
            "aggregation": {
                "consistency_type": ctype,
                "group_by_columns": ["order_id"],
                "aggregation_function": "SUM",
                "expected_column": "total",
            },
        }
        result = compiler._compile_consistency_rule("t", "col", "", "", param_sets[ctype])
        assert "error" not in result
        assert "compiled_sql" in result

    def test_unknown_type_returns_error(self, compiler):
        result = compiler._compile_consistency_rule("t", "c", "", "", {"consistency_type": "bogus"})
        assert "error" in result
        assert "Unknown" in result["error"]


# ── Type Inference ──────────────────────────────────────────────


class TestTypeInference:
    def test_aggregation_function_infers_aggregation(self):
        assert (
            RuleCompiler._infer_consistency_type({"aggregation_function": "SUM"}) == "aggregation"
        )

    def test_comparison_dataset_join_keys_infers_cross_table(self):
        assert (
            RuleCompiler._infer_consistency_type({"comparison_dataset": "x", "join_keys": ["id"]})
            == "cross_table"
        )

    def test_group_by_comparison_cols_infers_inter_record(self):
        assert (
            RuleCompiler._infer_consistency_type(
                {"group_by_columns": ["a"], "comparison_columns": ["b"]}
            )
            == "inter_record"
        )

    def test_comparison_column_infers_temporal(self):
        assert RuleCompiler._infer_consistency_type({"comparison_column": "end"}) == "temporal"

    def test_expected_column_infers_formula(self):
        assert RuleCompiler._infer_consistency_type({"expected_column": "total"}) == "formula"

    def test_reference_column_infers_intra_record(self):
        assert RuleCompiler._infer_consistency_type({"reference_column": "ref"}) == "intra_record"

    def test_empty_params_defaults_intra_record(self):
        assert RuleCompiler._infer_consistency_type({}) == "intra_record"

    def test_priority_aggregation_over_cross_table(self):
        # aggregation_function takes precedence
        assert (
            RuleCompiler._infer_consistency_type(
                {"aggregation_function": "SUM", "comparison_dataset": "x", "join_keys": ["id"]}
            )
            == "aggregation"
        )


# ── Null Handling ───────────────────────────────────────────────


class TestNullHandling:
    def test_skip_generates_not_null(self):
        cond, mode = RuleCompiler._consistency_null_handling_sql(["a", "b"], "skip")
        assert "IS NOT NULL" in cond
        assert mode == "skip"

    def test_pass_returns_empty(self):
        cond, mode = RuleCompiler._consistency_null_handling_sql(["a"], "pass")
        assert cond == ""
        assert mode == "pass"

    def test_fail_returns_empty(self):
        cond, mode = RuleCompiler._consistency_null_handling_sql(["a"], "fail")
        assert cond == ""
        assert mode == "fail"

    def test_skip_with_alias(self):
        cond, _ = RuleCompiler._consistency_null_handling_sql(["x"], "skip", "a")
        assert 'a."x"' in cond


# ── Tolerance ───────────────────────────────────────────────────


class TestTolerance:
    def test_absolute_default(self):
        m, mm = RuleCompiler._consistency_tolerance_sql("x", "y", "absolute", None)
        assert "0.01" in m
        assert "ABS" in m

    def test_absolute_custom(self):
        m, mm = RuleCompiler._consistency_tolerance_sql("x", "y", "absolute", 0.5)
        assert "0.5" in m

    def test_percentage(self):
        m, mm = RuleCompiler._consistency_tolerance_sql("x", "y", "percentage", 5)
        assert "NULLIF" in m
        assert "100" in m
        assert "5" in m

    def test_none(self):
        m, mm = RuleCompiler._consistency_tolerance_sql("x", "y", "none", None)
        assert "(x) = (y)" == m
        assert "(x) != (y)" == mm


# ── Error Result ────────────────────────────────────────────────


class TestErrorResult:
    def test_structure(self):
        r = RuleCompiler._consistency_error_result("bad thing")
        assert r["error"] == "bad thing"
        assert "ERROR" in r["compiled_sql"]
        assert "ERROR" in r["compiled_spark"]
        assert "violation_sql" in r


# ── Filter Expression Validation ────────────────────────────────


class TestFilterValidation:
    def test_clean_filter_accepted(self, compiler):
        result = compiler._compile_consistency_rule(
            "t",
            "c",
            "",
            "",
            {
                "consistency_type": "intra_record",
                "rule_expression": '"a" = 1',
                "filter_expression": "status = 'active'",
            },
        )
        assert "error" not in result

    def test_dangerous_filter_rejected(self, compiler):
        result = compiler._compile_consistency_rule(
            "t",
            "c",
            "",
            "",
            {
                "consistency_type": "intra_record",
                "rule_expression": '"a" = 1',
                "filter_expression": "1; DROP TABLE users",
            },
        )
        assert "error" in result
        assert "filter_expression" in result["error"]


# ── Rule Expression Validation ──────────────────────────────────


class TestRuleExpressionValidation:
    def test_clean_rule_accepted(self, compiler):
        result = compiler._compile_consistency_rule(
            "t",
            "c",
            "",
            "",
            {
                "consistency_type": "intra_record",
                "rule_expression": "\"country\" = 'US' AND \"currency\" = 'USD'",
            },
        )
        assert "error" not in result

    def test_dangerous_rule_rejected(self, compiler):
        result = compiler._compile_consistency_rule(
            "t",
            "c",
            "",
            "",
            {
                "consistency_type": "intra_record",
                "rule_expression": "1; DELETE FROM users",
            },
        )
        assert "error" in result
        assert "rule_expression" in result["error"]
