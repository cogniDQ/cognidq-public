"""P03 — F087 Length & Charset conformity type tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, params):
    return compiler._compile_conformity_rule('"public"."customers"', "sku", "", "100%", params)


# ===================================================================
# A) Length type
# ===================================================================
class TestLengthConformity:
    def test_min_and_max(self, compiler):
        result = _compile(
            compiler, {"conformity_type": "length", "min_length": 8, "max_length": 12}
        )
        sql = result["compiled_postgres"]
        assert "CHAR_LENGTH" in sql
        assert ">= 8" in sql
        assert "<= 12" in sql

    def test_min_only(self, compiler):
        result = _compile(compiler, {"conformity_type": "length", "min_length": 5})
        sql = result["compiled_postgres"]
        assert ">= 5" in sql
        assert "<=" not in sql

    def test_max_only(self, compiler):
        result = _compile(compiler, {"conformity_type": "length", "max_length": 20})
        sql = result["compiled_postgres"]
        assert "<= 20" in sql
        # min should not be present
        assert ">=" not in sql

    def test_missing_both_error(self, compiler):
        result = _compile(compiler, {"conformity_type": "length"})
        assert "error" in result

    def test_null_skip(self, compiler):
        result = _compile(
            compiler, {"conformity_type": "length", "min_length": 3, "null_handling": "skip"}
        )
        assert "IS NOT NULL" in result["compiled_postgres"]

    def test_null_fail(self, compiler):
        result = _compile(
            compiler, {"conformity_type": "length", "min_length": 3, "null_handling": "fail"}
        )
        assert "IS NOT NULL" not in result["compiled_postgres"]

    def test_null_pass(self, compiler):
        result = _compile(
            compiler, {"conformity_type": "length", "min_length": 3, "null_handling": "pass"}
        )
        assert "IS NULL OR" in result["compiled_postgres"]

    def test_trim_applied(self, compiler):
        result = _compile(compiler, {"conformity_type": "length", "min_length": 5})
        assert "TRIM" in result["compiled_postgres"]

    def test_filter_expression(self, compiler):
        result = _compile(
            compiler,
            {"conformity_type": "length", "min_length": 5, "filter_expression": "active = true"},
        )
        assert "active" in result["compiled_postgres"]

    def test_violation_sql_present(self, compiler):
        result = _compile(
            compiler, {"conformity_type": "length", "min_length": 5, "max_length": 10}
        )
        assert "violation_sql" in result

    def test_spark_code_present(self, compiler):
        result = _compile(compiler, {"conformity_type": "length", "min_length": 5})
        assert "compiled_spark" in result
        assert "length" in result["compiled_spark"].lower()


# ===================================================================
# B) Charset type
# ===================================================================
class TestCharsetConformity:
    def test_sql_uses_character_class_regex(self, compiler):
        result = _compile(
            compiler, {"conformity_type": "charset", "allowed_characters": "a-zA-Z0-9"}
        )
        sql = result["compiled_postgres"]
        assert "^[a-zA-Z0-9]*$" in sql

    def test_missing_allowed_characters_error(self, compiler):
        result = _compile(compiler, {"conformity_type": "charset"})
        assert "error" in result

    def test_null_skip(self, compiler):
        result = _compile(
            compiler,
            {"conformity_type": "charset", "allowed_characters": "a-z", "null_handling": "skip"},
        )
        assert "IS NOT NULL" in result["compiled_postgres"]

    def test_null_fail(self, compiler):
        result = _compile(
            compiler,
            {"conformity_type": "charset", "allowed_characters": "a-z", "null_handling": "fail"},
        )
        assert "IS NOT NULL" not in result["compiled_postgres"]

    def test_trim_applied(self, compiler):
        result = _compile(compiler, {"conformity_type": "charset", "allowed_characters": "a-z"})
        assert "TRIM" in result["compiled_postgres"]

    def test_violation_sql_and_spark(self, compiler):
        result = _compile(compiler, {"conformity_type": "charset", "allowed_characters": "a-zA-Z"})
        assert "violation_sql" in result
        assert "compiled_spark" in result
