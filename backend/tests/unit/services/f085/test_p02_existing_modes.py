"""P02 — Existing Modes Normalisation (regex, range, allowed_values) tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


TABLE = '"s"."t"'
COL = "email"


# ===================================================================
# Regex mode
# ===================================================================
class TestRegexNullHandling:
    def test_null_handling_fail(self, compiler):
        result = compiler._validity_regex(
            TABLE,
            COL,
            "",
            "",
            {
                "regex_pattern": "^[A-Z]+$",
                "null_handling": "fail",
            },
        )
        sql = result["compiled_sql"]
        assert "IS NULL" in sql  # NULLs counted as invalid
        assert "skipped_rows" not in sql

    def test_null_handling_skip(self, compiler):
        result = compiler._validity_regex(
            TABLE,
            COL,
            "",
            "",
            {
                "regex_pattern": "^[A-Z]+$",
                "null_handling": "skip",
            },
        )
        sql = result["compiled_sql"]
        assert "skipped_rows" in sql
        assert "IS NOT NULL" in sql

    def test_null_handling_pass(self, compiler):
        result = compiler._validity_regex(
            TABLE,
            COL,
            "",
            "",
            {
                "regex_pattern": "^[A-Z]+$",
                "null_handling": "pass",
            },
        )
        sql = result["compiled_sql"]
        assert "IS NULL THEN 1" in sql  # NULLs valid
        assert "skipped_rows" not in sql


class TestRegexWithFilter:
    def test_filter_combined(self, compiler):
        result = compiler._validity_regex(
            TABLE,
            COL,
            "",
            "",
            {
                "regex_pattern": "^\\d+$",
                "filter_expression": "active = true",
            },
        )
        sql = result["compiled_sql"]
        assert "active = true" in sql

    def test_mysql_variant(self, compiler):
        result = compiler._validity_regex(
            TABLE,
            COL,
            "",
            "",
            {
                "regex_pattern": "^[A-Z]+$",
            },
        )
        mysql = result["compiled_mysql"]
        assert "REGEXP" in mysql
        assert "~" not in mysql.replace("REGEXP", "")


# ===================================================================
# Range mode
# ===================================================================
class TestRangeBounds:
    def test_both_bounds(self, compiler):
        result = compiler._validity_range(
            TABLE,
            "age",
            "",
            "",
            {
                "min_value": 0,
                "max_value": 120,
            },
        )
        sql = result["compiled_sql"]
        assert ">= 0" in sql
        assert "<= 120" in sql

    def test_min_only(self, compiler):
        result = compiler._validity_range(
            TABLE,
            "age",
            "",
            "",
            {
                "min_value": 0,
            },
        )
        sql = result["compiled_sql"]
        assert ">= 0" in sql
        assert "<=" not in sql

    def test_max_only(self, compiler):
        result = compiler._validity_range(
            TABLE,
            "age",
            "",
            "",
            {
                "max_value": 100,
            },
        )
        sql = result["compiled_sql"]
        assert "<= 100" in sql
        assert ">=" not in sql

    def test_no_bounds_error(self, compiler):
        result = compiler._validity_range(TABLE, "age", "", "", {})
        assert result["error"] is True
        assert "min_value" in result["error_message"]


class TestRangeNullHandling:
    @pytest.mark.parametrize("mode", ["fail", "skip", "pass"])
    def test_all_modes(self, compiler, mode):
        result = compiler._validity_range(
            TABLE,
            "age",
            "",
            "",
            {
                "min_value": 0,
                "max_value": 120,
                "null_handling": mode,
            },
        )
        assert "error" not in result
        sql = result["compiled_sql"]
        assert "total_rows" in sql
        if mode == "skip":
            assert "skipped_rows" in sql


class TestRangeWithFilter:
    def test_filter_combined(self, compiler):
        result = compiler._validity_range(
            TABLE,
            "age",
            "",
            "",
            {
                "min_value": 0,
                "max_value": 120,
                "filter_expression": "status = 'active'",
            },
        )
        sql = result["compiled_sql"]
        assert "status = 'active'" in sql


# ===================================================================
# Allowed values mode
# ===================================================================
class TestAllowedValuesCaseSensitivity:
    def test_case_sensitive(self, compiler):
        result = compiler._validity_allowed_values(
            TABLE,
            "status",
            "",
            "",
            {
                "allowed_values": ["Active", "Inactive"],
                "case_sensitive": True,
            },
        )
        sql = result["compiled_sql"]
        assert "LOWER" not in sql
        assert "'Active'" in sql

    def test_case_insensitive(self, compiler):
        result = compiler._validity_allowed_values(
            TABLE,
            "status",
            "",
            "",
            {
                "allowed_values": ["Active", "Inactive"],
                "case_sensitive": False,
            },
        )
        sql = result["compiled_sql"]
        assert "LOWER" in sql
        assert "'active'" in sql


class TestAllowedValuesEdgeCases:
    def test_empty_list_error(self, compiler):
        result = compiler._validity_allowed_values(
            TABLE,
            "status",
            "",
            "",
            {
                "allowed_values": [],
            },
        )
        assert result["error"] is True
        assert "non-empty" in result["error_message"]

    def test_no_list_error(self, compiler):
        result = compiler._validity_allowed_values(TABLE, "status", "", "", {})
        assert result["error"] is True

    def test_single_quote_escaping(self, compiler):
        result = compiler._validity_allowed_values(
            TABLE,
            "name",
            "",
            "",
            {
                "allowed_values": ["O'Brien"],
                "case_sensitive": True,
            },
        )
        sql = result["compiled_sql"]
        assert "O''Brien" in sql


class TestAllowedValuesNullHandling:
    @pytest.mark.parametrize("mode", ["fail", "skip", "pass"])
    def test_all_modes(self, compiler, mode):
        result = compiler._validity_allowed_values(
            TABLE,
            "status",
            "",
            "",
            {
                "allowed_values": ["A", "B"],
                "null_handling": mode,
            },
        )
        assert "error" not in result
        sql = result["compiled_sql"]
        if mode == "skip":
            assert "skipped_rows" in sql
        if mode == "pass":
            assert "IS NULL THEN 1" in sql


class TestAllowedValuesCte:
    def test_cte_for_large_lists(self, compiler):
        """Lists >1000 should use CTE/unnest pattern instead of IN clause."""
        big_list = [f"val_{i}" for i in range(1001)]
        result = compiler._validity_allowed_values(
            TABLE,
            "code",
            "",
            "",
            {
                "allowed_values": big_list,
                "case_sensitive": True,
            },
        )
        sql = result["compiled_sql"]
        assert "WITH ref_values" in sql
        assert "unnest" in sql
        assert "LEFT JOIN" in sql

    def test_small_list_uses_in_clause(self, compiler):
        small_list = ["a", "b", "c"]
        result = compiler._validity_allowed_values(
            TABLE,
            "code",
            "",
            "",
            {
                "allowed_values": small_list,
                "case_sensitive": True,
            },
        )
        sql = result["compiled_sql"]
        assert "IN (" in sql
        assert "WITH ref_values" not in sql


# ===================================================================
# Backward compatibility — old configs with no validation_type
# ===================================================================
class TestBackwardCompatibility:
    def test_old_regex_config(self, compiler):
        """Old config with regex_pattern and no validation_type should compile."""
        result = compiler._compile_validity_rule(
            TABLE,
            COL,
            "",
            "",
            {
                "regex_pattern": "^[A-Z]+$",
            },
        )
        assert "error" not in result
        assert "~" in result["compiled_postgres"]

    def test_old_range_config(self, compiler):
        result = compiler._compile_validity_rule(
            TABLE,
            "age",
            "",
            "",
            {
                "min_value": 0,
                "max_value": 100,
            },
        )
        assert "error" not in result
        assert ">= 0" in result["compiled_sql"]
        assert "<= 100" in result["compiled_sql"]

    def test_old_allowed_values_config(self, compiler):
        result = compiler._compile_validity_rule(
            TABLE,
            "status",
            "",
            "",
            {
                "allowed_values": ["A", "B"],
            },
        )
        assert "error" not in result
        assert "IN (" in result["compiled_sql"]
