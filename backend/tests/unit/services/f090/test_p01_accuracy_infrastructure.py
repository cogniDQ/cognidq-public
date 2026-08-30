"""P01 — Accuracy Infrastructure Tests (constants, helpers, dispatcher, error paths)."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, column, params):
    return compiler.compile_rule(
        {
            "dimension": "accuracy",
            "entity": f"t.{column}",
            "condition": "",
            "expectation": "95%",
            "parameters": params,
        },
        target_table="t",
    )


# ── Constants ────────────────────────────────────────────────


class TestAccuracyConstants:
    def test_valid_accuracy_types_count(self):
        assert len(RuleCompiler.VALID_ACCURACY_TYPES) == 5

    def test_valid_accuracy_types_members(self):
        for t in (
            "reference_comparison",
            "trusted_source",
            "tolerated_deviation",
            "statistical",
            "derived_value",
        ):
            assert t in RuleCompiler.VALID_ACCURACY_TYPES

    def test_reference_based_types(self):
        assert RuleCompiler.REFERENCE_BASED_TYPES == {
            "reference_comparison",
            "trusted_source",
            "tolerated_deviation",
        }

    def test_self_referential_types(self):
        assert RuleCompiler.SELF_REFERENTIAL_TYPES == {"statistical", "derived_value"}

    def test_valid_tolerance_types(self):
        assert RuleCompiler.VALID_TOLERANCE_TYPES == {"none", "absolute", "percentage"}

    def test_valid_statistical_methods(self):
        assert RuleCompiler.VALID_STATISTICAL_METHODS == {"zscore", "iqr"}


# ── Error Result ─────────────────────────────────────────────


class TestAccuracyErrorResult:
    def test_error_result_structure(self):
        result = RuleCompiler._accuracy_error_result("test error")
        assert "-- ERROR: test error" in result["compiled_sql"]
        assert "# ERROR: test error" in result["compiled_spark"]
        assert result["error"] == "test error"
        assert "violation_sql" in result


# ── Type Inference ───────────────────────────────────────────


class TestInferAccuracyType:
    def test_statistical_method_infers_statistical(self):
        assert RuleCompiler._infer_accuracy_type({"statistical_method": "zscore"}) == "statistical"

    def test_formula_infers_derived_value(self):
        assert RuleCompiler._infer_accuracy_type({"formula": '"qty" * "price"'}) == "derived_value"

    def test_tolerance_with_ref_infers_tolerated_deviation(self):
        assert (
            RuleCompiler._infer_accuracy_type(
                {"tolerance_value": 5.0, "reference_dataset": "ref_table"}
            )
            == "tolerated_deviation"
        )

    def test_reference_dataset_infers_reference_comparison(self):
        assert (
            RuleCompiler._infer_accuracy_type({"reference_dataset": "ref"})
            == "reference_comparison"
        )

    def test_empty_params_infers_reference_comparison(self):
        assert RuleCompiler._infer_accuracy_type({}) == "reference_comparison"

    def test_statistical_takes_priority_over_formula(self):
        assert (
            RuleCompiler._infer_accuracy_type({"statistical_method": "iqr", "formula": "x+y"})
            == "statistical"
        )


# ── Tolerance SQL ────────────────────────────────────────────


class TestAccuracyToleranceSql:
    def test_none_exact_match(self):
        m, mm = RuleCompiler._accuracy_tolerance_sql("a", "b", "none", None)
        assert "(a) = (b)" in m
        assert "(a) != (b)" in mm

    def test_absolute(self):
        m, mm = RuleCompiler._accuracy_tolerance_sql("a", "b", "absolute", 0.5)
        assert "ABS" in m
        assert "<= 0.5" in m
        assert "> 0.5" in mm

    def test_absolute_default(self):
        m, _ = RuleCompiler._accuracy_tolerance_sql("a", "b", "absolute", None)
        assert "<= 0.01" in m

    def test_percentage(self):
        m, mm = RuleCompiler._accuracy_tolerance_sql("a", "b", "percentage", 5.0)
        assert "NULLIF" in m
        assert "<= 5.0" in m
        assert "> 5.0" in mm

    def test_percentage_default(self):
        m, _ = RuleCompiler._accuracy_tolerance_sql("a", "b", "percentage", None)
        assert "<= 1.0" in m


# ── Null Handling SQL ────────────────────────────────────────


class TestAccuracyNullHandling:
    def test_fail_default(self):
        clause, mode = RuleCompiler._accuracy_null_handling_sql(["col"], "fail")
        assert clause is None
        assert mode == "fail"

    def test_skip(self):
        clause, mode = RuleCompiler._accuracy_null_handling_sql(["col"], "skip")
        assert "IS NOT NULL" in clause
        assert mode == "skip"

    def test_pass(self):
        clause, mode = RuleCompiler._accuracy_null_handling_sql(["col"], "pass")
        assert clause is None
        assert mode == "pass"

    def test_skip_multi_column(self):
        clause, mode = RuleCompiler._accuracy_null_handling_sql(["a", "b"], "skip")
        assert '"a" IS NOT NULL' in clause
        assert '"b" IS NOT NULL' in clause


# ── Dispatcher Routing ───────────────────────────────────────


class TestDispatcherRouting:
    def _compile_type(self, compiler, accuracy_type, extra=None):
        params = {"accuracy_type": accuracy_type, "threshold_pass": 95}
        if extra:
            params.update(extra)
        return _compile(compiler, "c", params)

    def test_reference_comparison_routes(self, compiler):
        result = self._compile_type(
            compiler,
            "reference_comparison",
            {"reference_dataset": "ref", "reference_column": "rc", "join_keys": ["id"]},
        )
        assert "error" not in result

    def test_trusted_source_routes(self, compiler):
        result = self._compile_type(
            compiler,
            "trusted_source",
            {"reference_dataset": "ref", "reference_column": "rc", "join_keys": ["id"]},
        )
        assert "error" not in result

    def test_tolerated_deviation_routes(self, compiler):
        result = self._compile_type(
            compiler,
            "tolerated_deviation",
            {
                "reference_dataset": "ref",
                "reference_column": "rc",
                "join_keys": ["id"],
                "tolerance_type": "absolute",
                "tolerance_value": 1.0,
            },
        )
        assert "error" not in result

    def test_statistical_routes(self, compiler):
        result = self._compile_type(compiler, "statistical", {"statistical_method": "zscore"})
        assert "error" not in result

    def test_derived_value_routes(self, compiler):
        result = self._compile_type(compiler, "derived_value", {"formula": '"qty" * "price"'})
        assert "error" not in result

    def test_unknown_type_error(self, compiler):
        result = self._compile_type(compiler, "unknown_type")
        assert "error" in result
        assert "Unknown accuracy type" in result["error"]

    def test_dimension_dispatch(self, compiler):
        """Verify accuracy dimension hits _compile_accuracy_rule."""
        result = _compile(
            compiler,
            "c",
            {"accuracy_type": "statistical", "statistical_method": "zscore", "threshold_pass": 95},
        )
        assert "AVG" in result["compiled_sql"]


# ── Filter Expression ────────────────────────────────────────


class TestFilterExpression:
    def test_safe_filter_accepted(self, compiler):
        result = self._compile_with_filter(compiler, "status = 'active'")
        assert "error" not in result

    def test_dangerous_filter_rejected(self, compiler):
        result = self._compile_with_filter(compiler, "x; DROP TABLE users")
        assert "error" in result

    def _compile_with_filter(self, compiler, filter_expr):
        return _compile(
            compiler,
            "c",
            {
                "accuracy_type": "statistical",
                "statistical_method": "zscore",
                "threshold_pass": 95,
                "filter_expression": filter_expr,
            },
        )


# ── Quick SQL Smoke Per Type ─────────────────────────────────


class TestQuickSqlSmoke:
    def test_reference_comparison_sql(self, compiler):
        result = _compile(
            compiler,
            "price",
            {
                "accuracy_type": "reference_comparison",
                "reference_dataset": "master.prices",
                "reference_column": "ref_price",
                "join_keys": ["product_id"],
                "threshold_pass": 95,
            },
        )
        assert "LEFT JOIN" in result["compiled_sql"]
        assert "accurate_rows" in result["compiled_sql"]
        assert "verified_rows" in result["compiled_sql"]
        assert "unverifiable_rows" in result["compiled_sql"]

    def test_trusted_source_sql(self, compiler):
        result = _compile(
            compiler,
            "email",
            {
                "accuracy_type": "trusted_source",
                "reference_dataset": "verified_contacts",
                "reference_column": "verified_email",
                "join_keys": ["customer_id"],
                "threshold_pass": 95,
            },
        )
        assert "LEFT JOIN" in result["compiled_sql"]

    def test_tolerated_deviation_sql(self, compiler):
        result = _compile(
            compiler,
            "lat",
            {
                "accuracy_type": "tolerated_deviation",
                "reference_dataset": "ref_locations",
                "reference_column": "ref_lat",
                "join_keys": ["store_id"],
                "tolerance_type": "absolute",
                "tolerance_value": 0.001,
                "threshold_pass": 95,
            },
        )
        assert "ABS" in result["compiled_sql"]

    def test_statistical_zscore_sql(self, compiler):
        result = _compile(
            compiler,
            "salary",
            {
                "accuracy_type": "statistical",
                "statistical_method": "zscore",
                "threshold_pass": 95,
            },
        )
        assert "AVG" in result["compiled_sql"]
        assert "STDDEV" in result["compiled_sql"]
        assert "stats" in result["compiled_sql"].lower()

    def test_statistical_iqr_sql(self, compiler):
        result = _compile(
            compiler,
            "amount",
            {
                "accuracy_type": "statistical",
                "statistical_method": "iqr",
                "threshold_pass": 95,
            },
        )
        assert "percentile_cont" in result["compiled_sql"]

    def test_derived_value_sql(self, compiler):
        result = _compile(
            compiler,
            "total",
            {
                "accuracy_type": "derived_value",
                "formula": '"quantity" * "unit_price"',
                "threshold_pass": 95,
            },
        )
        assert "quantity" in result["compiled_sql"]
        assert "unit_price" in result["compiled_sql"]
        assert "accurate_rows" in result["compiled_sql"]
