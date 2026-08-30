"""P04 — Business Rule Mode tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


TABLE = '"s"."t"'
COL = "amount"


class TestBusinessRuleBasic:
    def test_generates_case_when(self, compiler):
        result = compiler._validity_business_rule(
            TABLE,
            COL,
            "",
            "",
            {
                "business_rule_expression": "amount > 0 AND amount < 10000",
            },
        )
        sql = result["compiled_sql"]
        assert "amount > 0 AND amount < 10000" in sql
        assert "valid_rows" in sql

    def test_missing_expression_error(self, compiler):
        result = compiler._validity_business_rule(TABLE, COL, "", "", {})
        assert result["error"] is True
        assert "business_rule_expression" in result["error_message"]

    def test_sql_injection_rejected(self, compiler):
        result = compiler._validity_business_rule(
            TABLE,
            COL,
            "",
            "",
            {
                "business_rule_expression": "1=1; DROP TABLE users",
            },
        )
        assert result["error"] is True
        assert "forbidden" in result["error_message"].lower()

    def test_union_injection_rejected(self, compiler):
        result = compiler._validity_business_rule(
            TABLE,
            COL,
            "",
            "",
            {
                "business_rule_expression": "id IN (SELECT id FROM admin UNION SELECT id FROM secrets)",
            },
        )
        assert result["error"] is True


class TestBusinessRuleNullHandling:
    @pytest.mark.parametrize("mode", ["fail", "skip", "pass"])
    def test_all_modes(self, compiler, mode):
        result = compiler._validity_business_rule(
            TABLE,
            COL,
            "",
            "",
            {
                "business_rule_expression": "amount > 0",
                "null_handling": mode,
            },
        )
        assert "error" not in result
        sql = result["compiled_sql"]
        if mode == "skip":
            assert "skipped_rows" in sql


class TestBusinessRuleViaDispatcher:
    def test_dispatch(self, compiler):
        result = compiler._compile_validity_rule(
            TABLE,
            COL,
            "",
            "",
            {
                "validation_type": "business_rule",
                "business_rule_expression": "amount BETWEEN 0 AND 9999",
            },
        )
        assert "error" not in result
        assert "BETWEEN" in result["compiled_sql"]
