"""P01 — Compiler Infrastructure & Null Mode Refactor tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


# ---------------------------------------------------------------------------
# _validate_filter_expression
# ---------------------------------------------------------------------------
class TestValidateFilterExpression:
    def test_rejects_drop(self, compiler):
        assert compiler._validate_filter_expression("DROP TABLE users") is False

    def test_rejects_alter(self, compiler):
        assert compiler._validate_filter_expression("ALTER TABLE users ADD col INT") is False

    def test_rejects_delete(self, compiler):
        assert compiler._validate_filter_expression("DELETE FROM users") is False

    def test_rejects_insert(self, compiler):
        assert compiler._validate_filter_expression("INSERT INTO users VALUES(1)") is False

    def test_rejects_update(self, compiler):
        assert compiler._validate_filter_expression("UPDATE users SET x=1") is False

    def test_rejects_union(self, compiler):
        assert compiler._validate_filter_expression("1=1 UNION SELECT * FROM secrets") is False

    def test_rejects_semicolon(self, compiler):
        assert compiler._validate_filter_expression("status='active'; DROP TABLE") is False

    def test_rejects_subquery(self, compiler):
        assert compiler._validate_filter_expression("id IN (SELECT id FROM admin)") is False

    def test_accepts_basic_comparison(self, compiler):
        assert compiler._validate_filter_expression("status = 'active'") is True

    def test_accepts_and_or(self, compiler):
        assert (
            compiler._validate_filter_expression("status = 'active' AND created_at > '2024-01-01'")
            is True
        )

    def test_accepts_in_list(self, compiler):
        assert compiler._validate_filter_expression("country IN ('US', 'UK', 'DE')") is True

    def test_accepts_is_null(self, compiler):
        assert compiler._validate_filter_expression("deleted_at IS NULL") is True

    def test_accepts_between(self, compiler):
        assert compiler._validate_filter_expression("age BETWEEN 18 AND 65") is True


# ---------------------------------------------------------------------------
# _format_placeholder_list
# ---------------------------------------------------------------------------
class TestFormatPlaceholderList:
    def test_basic_list(self, compiler):
        result = compiler._format_placeholder_list(["N/A", "TBD"])
        assert result == "'n/a', 'tbd'"

    def test_trims_whitespace(self, compiler):
        result = compiler._format_placeholder_list(["  TBD  ", " N/A"])
        assert result == "'tbd', 'n/a'"

    def test_lowercases(self, compiler):
        result = compiler._format_placeholder_list(["UNKNOWN", "Pending"])
        assert result == "'unknown', 'pending'"

    def test_escapes_single_quotes(self, compiler):
        result = compiler._format_placeholder_list(["it's", "don't"])
        assert result == "'it''s', 'don''t'"

    def test_empty_list(self, compiler):
        result = compiler._format_placeholder_list([])
        assert result == ""

    def test_sql_injection_attempt(self, compiler):
        """Verify injection attempt is neutralized by quote escaping."""
        result = compiler._format_placeholder_list(["'; DROP TABLE users --"])
        # The single quote is doubled, making it a literal within the SQL string
        assert "''" in result


# ---------------------------------------------------------------------------
# _build_where_clause
# ---------------------------------------------------------------------------
class TestBuildWhereClause:
    def test_filter_only(self, compiler):
        result = compiler._build_where_clause("status = 'active'")
        assert result == "WHERE (status = 'active')"

    def test_existing_only(self, compiler):
        result = compiler._build_where_clause(None, '"col" IS NULL')
        assert result == 'WHERE ("col" IS NULL)'

    def test_both(self, compiler):
        result = compiler._build_where_clause("status = 'active'", '"col" IS NULL')
        assert result == "WHERE (status = 'active') AND (\"col\" IS NULL)"

    def test_neither(self, compiler):
        result = compiler._build_where_clause()
        assert result == ""

    def test_empty_strings(self, compiler):
        result = compiler._build_where_clause("", "")
        assert result == ""


# ---------------------------------------------------------------------------
# Null mode — single column (backward compatible default)
# ---------------------------------------------------------------------------
class TestCompletenessNull:
    def test_default_no_check_mode(self, compiler):
        """No check_mode in parameters → identical SQL to pre-F084."""
        result = compiler._compile_completeness_rule(
            '"public"."orders"', "email", "IS NOT NULL", "100%", {"columns": ["email"]}
        )
        assert "total_rows" in result["compiled_sql"]
        assert 'COUNT("email")' in result["compiled_sql"]
        assert '"email" IS NULL' in result["violation_sql"]
        assert result.get("error") is not True

    def test_explicit_null_mode(self, compiler):
        """check_mode=null produces same SQL as default."""
        default_result = compiler._compile_completeness_rule(
            '"orders"', "email", "IS NOT NULL", "100%", {"columns": ["email"]}
        )
        explicit_result = compiler._compile_completeness_rule(
            '"orders"', "email", "IS NOT NULL", "100%", {"columns": ["email"], "check_mode": "null"}
        )
        assert default_result["compiled_sql"] == explicit_result["compiled_sql"]
        assert default_result["violation_sql"] == explicit_result["violation_sql"]

    def test_multi_column(self, compiler):
        """Multiple columns → AND IS NOT NULL."""
        result = compiler._compile_completeness_rule(
            '"orders"',
            "email",
            "IS NOT NULL",
            "100%",
            {"columns": ["email", "phone"], "check_mode": "null"},
        )
        assert '"email" IS NOT NULL AND "phone" IS NOT NULL' in result["compiled_sql"]
        assert '"email" IS NULL OR "phone" IS NULL' in result["compiled_sql"]

    def test_with_filter_expression(self, compiler):
        """filter_expression applied as WHERE clause."""
        result = compiler._compile_completeness_rule(
            '"orders"',
            "email",
            "IS NOT NULL",
            "100%",
            {"columns": ["email"], "check_mode": "null", "filter_expression": "status = 'active'"},
        )
        assert "WHERE" in result["compiled_sql"]
        assert "status = 'active'" in result["compiled_sql"]
        assert "status = 'active'" in result["violation_sql"]

    def test_include_empty_strings_true(self, compiler):
        """include_empty_strings=True in null mode → TRIM + empty detection."""
        result = compiler._compile_completeness_rule(
            '"orders"',
            "email",
            "IS NOT NULL",
            "100%",
            {"columns": ["email"], "check_mode": "null", "include_empty_strings": True},
        )
        assert "TRIM" in result["compiled_sql"]
        assert "''" in result["compiled_sql"]

    def test_include_empty_strings_false(self, compiler):
        """include_empty_strings=False (default) → only NULL detected."""
        result = compiler._compile_completeness_rule(
            '"orders"',
            "email",
            "IS NOT NULL",
            "100%",
            {"columns": ["email"], "check_mode": "null", "include_empty_strings": False},
        )
        assert "TRIM" not in result["compiled_sql"]

    def test_spark_code_present(self, compiler):
        result = compiler._compile_completeness_rule(
            '"orders"', "email", "IS NOT NULL", "100%", {"columns": ["email"], "check_mode": "null"}
        )
        assert "pyspark" in result["compiled_spark"]
        assert "isNull" in result["compiled_spark"] or "isNotNull" in result["compiled_spark"]

    def test_all_output_keys_present(self, compiler):
        result = compiler._compile_completeness_rule(
            '"orders"', "email", "IS NOT NULL", "100%", {"columns": ["email"]}
        )
        for key in [
            "compiled_sql",
            "compiled_postgres",
            "compiled_mysql",
            "compiled_snowflake",
            "compiled_spark",
            "violation_sql",
        ]:
            assert key in result, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# Invalid check_mode
# ---------------------------------------------------------------------------
class TestInvalidCheckMode:
    def test_returns_error(self, compiler):
        result = compiler._compile_completeness_rule(
            '"orders"',
            "email",
            "IS NOT NULL",
            "100%",
            {"columns": ["email"], "check_mode": "invalid_mode"},
        )
        assert result["error"] is True
        assert "invalid_mode" in result["error_message"]
        assert result["compiled_sql"] == ""

    def test_invalid_filter_expression_returns_error(self, compiler):
        result = compiler._compile_completeness_rule(
            '"orders"',
            "email",
            "IS NOT NULL",
            "100%",
            {
                "columns": ["email"],
                "check_mode": "null",
                "filter_expression": "1=1; DROP TABLE users",
            },
        )
        assert result["error"] is True
        assert "forbidden" in result["error_message"].lower()
