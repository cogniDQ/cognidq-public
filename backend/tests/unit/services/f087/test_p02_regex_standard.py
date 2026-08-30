"""P02 — F087 Regex & Standard conformity type tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, params):
    return compiler._compile_conformity_rule('"public"."customers"', "email", "", "100%", params)


# ===================================================================
# A) Regex type
# ===================================================================
class TestRegexConformity:
    def test_sql_contains_regex_operator(self, compiler):
        result = _compile(compiler, {"conformity_type": "regex", "regex_pattern": "^[A-Z]+$"})
        assert "~" in result["compiled_postgres"]
        assert "^[A-Z]+$" in result["compiled_postgres"]

    def test_null_skip_excludes_nulls(self, compiler):
        result = _compile(
            compiler,
            {"conformity_type": "regex", "regex_pattern": "^\\d+$", "null_handling": "skip"},
        )
        assert "IS NOT NULL" in result["compiled_postgres"]

    def test_null_fail_no_filter(self, compiler):
        result = _compile(
            compiler,
            {"conformity_type": "regex", "regex_pattern": "^\\d+$", "null_handling": "fail"},
        )
        assert "IS NOT NULL" not in result["compiled_postgres"]

    def test_null_pass_coalesce(self, compiler):
        result = _compile(
            compiler,
            {"conformity_type": "regex", "regex_pattern": "^\\d+$", "null_handling": "pass"},
        )
        sql = result["compiled_postgres"]
        assert "IS NULL OR" in sql

    def test_trim_enabled_by_default(self, compiler):
        result = _compile(compiler, {"conformity_type": "regex", "regex_pattern": "^[A-Z]+$"})
        assert "TRIM" in result["compiled_postgres"]

    def test_trim_disabled(self, compiler):
        result = _compile(
            compiler,
            {"conformity_type": "regex", "regex_pattern": "^[A-Z]+$", "trim_whitespace": False},
        )
        sql = result["compiled_postgres"]
        # Should not have TRIM wrapping the column
        assert 'TRIM("email")' not in sql

    def test_filter_expression(self, compiler):
        result = _compile(
            compiler,
            {
                "conformity_type": "regex",
                "regex_pattern": "^[A-Z]+$",
                "filter_expression": "status = 'active'",
            },
        )
        assert "status" in result["compiled_postgres"]

    def test_violation_sql_present(self, compiler):
        result = _compile(compiler, {"conformity_type": "regex", "regex_pattern": "^[A-Z]+$"})
        assert "violation_sql" in result
        assert "!~" in result["violation_sql"]

    def test_spark_uses_rlike(self, compiler):
        result = _compile(compiler, {"conformity_type": "regex", "regex_pattern": "^[A-Z]+$"})
        assert "rlike" in result["compiled_spark"]

    def test_missing_pattern_error(self, compiler):
        result = _compile(compiler, {"conformity_type": "regex"})
        assert "error" in result

    def test_sql_has_total_conforming_non_conforming(self, compiler):
        result = _compile(compiler, {"conformity_type": "regex", "regex_pattern": "^\\d+$"})
        sql = result["compiled_postgres"]
        assert "total_rows" in sql
        assert "conforming_rows" in sql
        assert "non_conforming_rows" in sql


# ===================================================================
# B) Standard type
# ===================================================================
class TestStandardConformity:
    def test_resolves_iso_8601(self, compiler):
        result = _compile(compiler, {"conformity_type": "standard", "standard_name": "iso_8601"})
        assert "error" not in result
        assert "~" in result["compiled_postgres"]

    def test_resolves_e164(self, compiler):
        result = _compile(compiler, {"conformity_type": "standard", "standard_name": "e164"})
        assert "error" not in result

    def test_resolves_email(self, compiler):
        result = _compile(
            compiler, {"conformity_type": "standard", "standard_name": "email_rfc5322"}
        )
        assert "error" not in result

    def test_unknown_standard_error(self, compiler):
        result = _compile(
            compiler, {"conformity_type": "standard", "standard_name": "fake_standard"}
        )
        assert "error" in result
        assert "fake_standard" in result["error"]

    def test_missing_standard_name_error(self, compiler):
        result = _compile(compiler, {"conformity_type": "standard"})
        assert "error" in result

    @pytest.mark.parametrize("standard", list(RuleCompiler.CONFORMITY_STANDARDS.keys()))
    def test_all_standards_produce_valid_sql(self, compiler, standard):
        result = _compile(compiler, {"conformity_type": "standard", "standard_name": standard})
        assert "error" not in result
        assert "compiled_postgres" in result

    def test_spark_code_present(self, compiler):
        result = _compile(compiler, {"conformity_type": "standard", "standard_name": "uuid"})
        assert "compiled_spark" in result

    def test_null_handling_works(self, compiler):
        result = _compile(
            compiler,
            {"conformity_type": "standard", "standard_name": "e164", "null_handling": "fail"},
        )
        assert "IS NOT NULL" not in result["compiled_postgres"]
