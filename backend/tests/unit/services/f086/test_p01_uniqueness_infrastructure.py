"""P01 — Uniqueness Dispatcher Infrastructure tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _make_params(**kwargs):
    """Helper to build a parameters dict."""
    return kwargs


# ---------------------------------------------------------------------------
# Dispatcher routing
# ---------------------------------------------------------------------------
class TestDispatcherRoutesAllModes:
    """Each known uniqueness_mode should dispatch without raising."""

    @pytest.mark.parametrize("mode", sorted(RuleCompiler.VALID_UNIQUENESS_MODES))
    def test_dispatcher_routes_all_modes(self, compiler, mode):
        params = {"uniqueness_mode": mode, "columns": ["col1", "col2"]}
        if mode == "scoped":
            params["scope_columns"] = ["dept"]
        elif mode == "cross_dataset":
            params["cross_dataset_name"] = "other_table"
            params["cross_dataset_column"] = "other_col"
        elif mode == "temporal":
            params["temporal_column"] = "created_at"
            params["temporal_window"] = "1d"
        result = compiler._compile_uniqueness_rule('"schema"."table"', "col1", "", "", params)
        assert isinstance(result, dict)
        assert "compiled_sql" in result or "error" in result

    def test_unknown_mode_returns_error(self, compiler):
        result = compiler._compile_uniqueness_rule(
            '"schema"."table"',
            "col",
            "",
            "",
            {"uniqueness_mode": "bogus_mode"},
        )
        assert result["error"] is True
        assert "bogus_mode" in result["error_message"]

    def test_error_result_lists_allowed_modes(self, compiler):
        result = compiler._compile_uniqueness_rule(
            '"schema"."table"',
            "col",
            "",
            "",
            {"uniqueness_mode": "invalid"},
        )
        for mode in ["exact", "composite", "scoped"]:
            assert mode in result["error_message"]


# ---------------------------------------------------------------------------
# Mode inference (_infer_uniqueness_mode)
# ---------------------------------------------------------------------------
class TestInferUniquenessMode:
    def test_infer_scoped(self, compiler):
        assert compiler._infer_uniqueness_mode({"scope_columns": ["dept"]}) == "scoped"

    def test_infer_cross_dataset(self, compiler):
        assert compiler._infer_uniqueness_mode({"cross_dataset_name": "t2"}) == "cross_dataset"

    def test_infer_fuzzy(self, compiler):
        assert compiler._infer_uniqueness_mode({"fuzzy_algorithm": "levenshtein"}) == "fuzzy"

    def test_infer_temporal(self, compiler):
        assert compiler._infer_uniqueness_mode({"temporal_window": "1d"}) == "temporal"

    def test_infer_composite(self, compiler):
        assert compiler._infer_uniqueness_mode({"columns": ["a", "b"]}) == "composite"

    def test_infer_exact_default(self, compiler):
        assert compiler._infer_uniqueness_mode({}) == "exact"

    def test_infer_exact_single_column(self, compiler):
        assert compiler._infer_uniqueness_mode({"columns": ["email"]}) == "exact"

    def test_scope_takes_priority_over_composite(self, compiler):
        """When both scope_columns and multiple columns, scoped wins."""
        assert (
            compiler._infer_uniqueness_mode({"scope_columns": ["dept"], "columns": ["a", "b"]})
            == "scoped"
        )


# ---------------------------------------------------------------------------
# Null handling SQL (_uniqueness_null_handling_sql)
# ---------------------------------------------------------------------------
class TestNullHandlingSql:
    def test_exclude_mode_single_column(self, compiler):
        key_exprs, null_where = compiler._uniqueness_null_handling_sql(["email"], "exclude")
        assert key_exprs == ['"email"']
        assert '"email" IS NOT NULL' in null_where

    def test_exclude_mode_multi_column(self, compiler):
        key_exprs, null_where = compiler._uniqueness_null_handling_sql(
            ["order_id", "line_item"], "exclude"
        )
        assert len(key_exprs) == 2
        assert '"order_id" IS NOT NULL' in null_where
        assert '"line_item" IS NOT NULL' in null_where

    def test_include_mode_single_column(self, compiler):
        key_exprs, null_where = compiler._uniqueness_null_handling_sql(["email"], "include")
        assert "__NULL__" in key_exprs[0]
        assert null_where == ""

    def test_include_mode_multi_column(self, compiler):
        key_exprs, null_where = compiler._uniqueness_null_handling_sql(["a", "b"], "include")
        assert len(key_exprs) == 2
        for expr in key_exprs:
            assert "COALESCE" in expr
        assert null_where == ""

    def test_case_insensitive(self, compiler):
        key_exprs, _ = compiler._uniqueness_null_handling_sql(
            ["Name"], "exclude", case_sensitive=False
        )
        assert "LOWER" in key_exprs[0]

    def test_case_sensitive_default(self, compiler):
        key_exprs, _ = compiler._uniqueness_null_handling_sql(
            ["Name"], "exclude", case_sensitive=True
        )
        assert key_exprs == ['"Name"']


# ---------------------------------------------------------------------------
# Error result structure (_uniqueness_error_result)
# ---------------------------------------------------------------------------
class TestUniquenessErrorResult:
    def test_error_result_structure(self, compiler):
        result = compiler._uniqueness_error_result("something broke")
        assert result["error"] is True
        assert result["error_message"] == "something broke"
        assert result["compiled_sql"] == ""
        assert result["compiled_postgres"] == ""
        assert result["compiled_mysql"] == ""
        assert result["compiled_snowflake"] == ""
        assert result["compiled_spark"] == ""
        assert result["violation_sql"] == ""


# ---------------------------------------------------------------------------
# Temporal window parsing (_parse_temporal_window)
# ---------------------------------------------------------------------------
class TestParseTemporalWindow:
    def test_days(self, compiler):
        assert compiler._parse_temporal_window("1d") == 86400

    def test_hours(self, compiler):
        assert compiler._parse_temporal_window("2h") == 7200

    def test_minutes(self, compiler):
        assert compiler._parse_temporal_window("30m") == 1800

    def test_seconds(self, compiler):
        assert compiler._parse_temporal_window("60s") == 60

    def test_multi_digit(self, compiler):
        assert compiler._parse_temporal_window("14d") == 14 * 86400

    def test_invalid_format_returns_neg(self, compiler):
        assert compiler._parse_temporal_window("abc") == -1

    def test_empty_string_returns_neg(self, compiler):
        assert compiler._parse_temporal_window("") == -1

    def test_no_unit_returns_neg(self, compiler):
        assert compiler._parse_temporal_window("100") == -1

    def test_float_returns_neg(self, compiler):
        assert compiler._parse_temporal_window("1.5d") == -1


# ---------------------------------------------------------------------------
# Filter expression integration in uniqueness dispatch
# ---------------------------------------------------------------------------
class TestFilterExpressionUniqueness:
    def test_filter_expression_in_uniqueness(self, compiler):
        result = compiler._compile_uniqueness_rule(
            '"s"."t"',
            "col",
            "",
            "",
            {
                "uniqueness_mode": "exact",
                "columns": ["col"],
                "filter_expression": "status = 'active'",
            },
        )
        assert "error" not in result
        assert "status = 'active'" in result["compiled_sql"]

    def test_filter_injection_rejected(self, compiler):
        result = compiler._compile_uniqueness_rule(
            '"s"."t"',
            "col",
            "",
            "",
            {
                "uniqueness_mode": "exact",
                "columns": ["col"],
                "filter_expression": "1=1; DROP TABLE users",
            },
        )
        assert result["error"] is True
        assert "forbidden" in result["error_message"].lower()
