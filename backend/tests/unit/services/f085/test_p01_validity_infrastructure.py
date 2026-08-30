"""P01 — Validity Dispatcher Infrastructure tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _make_rule(dimension="validity", column="col", **params):
    """Helper to build a canonical rule dict."""
    return {
        "dimension": dimension,
        "entity": f"table.{column}",
        "condition": "",
        "expectation": "",
        "parameters": params,
    }


# ---------------------------------------------------------------------------
# Dispatcher routing
# ---------------------------------------------------------------------------
class TestDispatcherRoutesAllTypes:
    """Each known validation_type should dispatch without raising."""

    @pytest.mark.parametrize("vtype", sorted(RuleCompiler.VALID_VALIDATION_TYPES))
    def test_dispatcher_routes_all_types(self, compiler, vtype):
        # Build minimal params that won't error for implemented types
        params: dict = {"validation_type": vtype}
        if vtype == "regex":
            params["regex_pattern"] = "^[A-Z]$"
        elif vtype == "range":
            params["min_value"] = 0
        elif vtype == "allowed_values":
            params["allowed_values"] = ["a"]
        # P03-P06 stubs will return error results but should not raise
        result = compiler._compile_validity_rule('"schema"."table"', "col", "", "", params)
        assert isinstance(result, dict)
        # Must have at least compiled_sql or error key
        assert "compiled_sql" in result or "error" in result

    def test_unknown_type_returns_error(self, compiler):
        result = compiler._compile_validity_rule(
            '"schema"."table"',
            "col",
            "",
            "",
            {"validation_type": "bogus_type"},
        )
        assert result["error"] is True
        assert "bogus_type" in result["error_message"]


# ---------------------------------------------------------------------------
# Type inference (_infer_validation_type)
# ---------------------------------------------------------------------------
class TestInferValidationType:
    def test_infer_regex(self, compiler):
        assert compiler._infer_validation_type({"regex_pattern": "^\\d+$"}) == "regex"

    def test_infer_range_from_min(self, compiler):
        assert compiler._infer_validation_type({"min_value": 0}) == "range"

    def test_infer_range_from_max(self, compiler):
        assert compiler._infer_validation_type({"max_value": 100}) == "range"

    def test_infer_range_from_both(self, compiler):
        assert compiler._infer_validation_type({"min_value": 0, "max_value": 100}) == "range"

    def test_infer_allowed_values(self, compiler):
        assert compiler._infer_validation_type({"allowed_values": ["a", "b"]}) == "allowed_values"

    def test_infer_fallback(self, compiler):
        """No recognised params → fallback to unknown."""
        assert compiler._infer_validation_type({}) == "unknown"

    def test_regex_takes_priority_over_range(self, compiler):
        """When both regex_pattern and min_value are present, regex wins."""
        assert (
            compiler._infer_validation_type({"regex_pattern": "^\\d+$", "min_value": 0}) == "regex"
        )


# ---------------------------------------------------------------------------
# Null handling SQL (_validity_null_handling_sql)
# ---------------------------------------------------------------------------
class TestNullHandlingSql:
    def test_fail_mode(self, compiler):
        total, mode, extra = compiler._validity_null_handling_sql("age", "fail")
        assert total == "COUNT(*)"
        assert mode == "null_invalid"
        assert extra == ""

    def test_skip_mode(self, compiler):
        total, mode, extra = compiler._validity_null_handling_sql("age", "skip")
        assert "IS NOT NULL" in total
        assert mode == "skipped_null"
        assert "skipped_rows" in extra
        assert '"age" IS NULL' in extra

    def test_pass_mode(self, compiler):
        total, mode, extra = compiler._validity_null_handling_sql("age", "pass")
        assert total == "COUNT(*)"
        assert mode == "null_valid"
        assert extra == ""

    def test_default_is_fail(self, compiler):
        """Unrecognised value falls through to fail."""
        total, mode, extra = compiler._validity_null_handling_sql("x", "unknown")
        assert mode == "null_invalid"


# ---------------------------------------------------------------------------
# Error result structure (_validity_error_result)
# ---------------------------------------------------------------------------
class TestValidityErrorResult:
    def test_error_result_structure(self, compiler):
        result = compiler._validity_error_result("something broke")
        assert result["error"] is True
        assert result["error_message"] == "something broke"
        assert result["compiled_sql"] == ""
        assert result["compiled_postgres"] == ""
        assert result["compiled_mysql"] == ""
        assert result["compiled_snowflake"] == ""
        assert result["compiled_spark"] == ""
        assert result["violation_sql"] == ""


# ---------------------------------------------------------------------------
# Filter expression integration in validity dispatch
# ---------------------------------------------------------------------------
class TestFilterExpressionValidity:
    def test_filter_expression_in_validity(self, compiler):
        """Valid filter should appear in compiled SQL."""
        result = compiler._compile_validity_rule(
            '"s"."t"',
            "col",
            "",
            "",
            {
                "validation_type": "regex",
                "regex_pattern": "^[A-Z]+$",
                "filter_expression": "status = 'active'",
            },
        )
        assert "error" not in result
        assert "status = 'active'" in result["compiled_sql"]

    def test_filter_injection_rejected(self, compiler):
        """DDL in filter_expression → error result, no SQL executed."""
        result = compiler._compile_validity_rule(
            '"s"."t"',
            "col",
            "",
            "",
            {
                "validation_type": "regex",
                "regex_pattern": "^[A-Z]+$",
                "filter_expression": "1=1; DROP TABLE users",
            },
        )
        assert result["error"] is True
        assert "forbidden" in result["error_message"].lower()
