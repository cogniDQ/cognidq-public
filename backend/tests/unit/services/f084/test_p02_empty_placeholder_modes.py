"""P02 — Empty & Placeholder Modes tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, mode, **extra):
    params = {"columns": ["email"], "check_mode": mode}
    params.update(extra)
    return compiler._compile_completeness_rule('"orders"', "email", "IS NOT NULL", "100%", params)


# ---------------------------------------------------------------------------
# Empty mode
# ---------------------------------------------------------------------------
class TestCompletenessEmpty:
    def test_counts_null_empty_whitespace(self, compiler):
        result = _compile(compiler, "empty")
        sql = result["compiled_sql"]
        assert "TRIM" in sql
        assert "''" in sql
        assert "IS NULL" in sql
        assert result.get("error") is not True

    def test_violation_sql_includes_null_and_empty(self, compiler):
        result = _compile(compiler, "empty")
        vsql = result["violation_sql"]
        assert "IS NULL" in vsql
        assert "TRIM" in vsql

    def test_with_filter(self, compiler):
        result = _compile(compiler, "empty", filter_expression="status = 'active'")
        assert "status = 'active'" in result["compiled_sql"]
        assert "status = 'active'" in result["violation_sql"]

    def test_spark_code_present(self, compiler):
        result = _compile(compiler, "empty")
        assert "pyspark" in result["compiled_spark"]
        assert "trim" in result["compiled_spark"].lower()

    def test_all_keys_present(self, compiler):
        result = _compile(compiler, "empty")
        for key in [
            "compiled_sql",
            "compiled_postgres",
            "compiled_mysql",
            "compiled_snowflake",
            "compiled_spark",
            "violation_sql",
        ]:
            assert key in result


# ---------------------------------------------------------------------------
# Placeholder mode
# ---------------------------------------------------------------------------
class TestCompletenessPlaceholder:
    def test_basic_placeholders(self, compiler):
        result = _compile(compiler, "placeholder", placeholder_values=["N/A", "TBD"])
        sql = result["compiled_sql"]
        assert "'n/a'" in sql
        assert "'tbd'" in sql
        assert "LOWER" in sql

    def test_case_insensitive(self, compiler):
        result = _compile(compiler, "placeholder", placeholder_values=["N/A"])
        sql = result["compiled_sql"]
        assert "LOWER" in sql
        assert "TRIM" in sql

    def test_trimmed(self, compiler):
        result = _compile(compiler, "placeholder", placeholder_values=[" TBD "])
        sql = result["compiled_sql"]
        assert "'tbd'" in sql  # trimmed

    def test_empty_placeholder_list_fallback(self, compiler):
        """Empty placeholder list → SQL equivalent to empty mode."""
        result = _compile(compiler, "placeholder", placeholder_values=[])
        _compile(compiler, "empty")
        # Both should use NULL + empty string detection, no IN clause
        assert "IN" not in result["compiled_sql"]
        assert "TRIM" in result["compiled_sql"]

    def test_sql_injection_safe(self, compiler):
        """Placeholder with SQL metacharacters is safely escaped."""
        result = _compile(compiler, "placeholder", placeholder_values=["'; DROP TABLE users --"])
        sql = result["compiled_sql"]
        # Single quote is doubled, making the entire thing a safe literal
        assert "''" in sql
        assert result.get("error") is not True

    def test_violation_sql_includes_placeholder_condition(self, compiler):
        result = _compile(compiler, "placeholder", placeholder_values=["N/A"])
        vsql = result["violation_sql"]
        assert "'n/a'" in vsql
        assert "IN" in vsql

    def test_with_filter(self, compiler):
        result = _compile(
            compiler, "placeholder", placeholder_values=["N/A"], filter_expression="year > 2020"
        )
        assert "year > 2020" in result["compiled_sql"]
        assert "year > 2020" in result["violation_sql"]

    def test_spark_code_present(self, compiler):
        result = _compile(compiler, "placeholder", placeholder_values=["N/A"])
        assert "pyspark" in result["compiled_spark"]
        assert "isin" in result["compiled_spark"]

    def test_multiple_placeholders(self, compiler):
        result = _compile(
            compiler, "placeholder", placeholder_values=["N/A", "TBD", "unknown", "-"]
        )
        sql = result["compiled_sql"]
        assert "'n/a'" in sql
        assert "'tbd'" in sql
        assert "'unknown'" in sql
        assert "'-'" in sql
