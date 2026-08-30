"""P06 — Negative Constraint Mode tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


TABLE = '"s"."t"'
COL = "status"


class TestNegativeBasic:
    def test_inverted_logic(self, compiler):
        """Matching rows should be counted as INVALID, not valid."""
        result = compiler._validity_negative(
            TABLE,
            COL,
            "",
            "",
            {
                "negative_expression": "status = 'DELETED'",
            },
        )
        sql = result["compiled_sql"]
        # valid = NOT matching, invalid = matching
        assert "NOT (status = 'DELETED')" in sql
        assert "valid_rows" in sql
        assert "invalid_rows" in sql

    def test_missing_expression_error(self, compiler):
        result = compiler._validity_negative(TABLE, COL, "", "", {})
        assert result["error"] is True
        assert "negative_expression" in result["error_message"]

    def test_sql_injection_rejected(self, compiler):
        result = compiler._validity_negative(
            TABLE,
            COL,
            "",
            "",
            {
                "negative_expression": "1=1; DROP TABLE users",
            },
        )
        assert result["error"] is True
        assert "forbidden" in result["error_message"].lower()


class TestNegativeNullHandling:
    @pytest.mark.parametrize("mode", ["fail", "skip", "pass"])
    def test_all_modes(self, compiler, mode):
        result = compiler._validity_negative(
            TABLE,
            COL,
            "",
            "",
            {
                "negative_expression": "status = 'DELETED'",
                "null_handling": mode,
            },
        )
        assert "error" not in result
        sql = result["compiled_sql"]
        if mode == "skip":
            assert "skipped_rows" in sql


class TestNegativeViaDispatcher:
    def test_dispatch(self, compiler):
        result = compiler._compile_validity_rule(
            TABLE,
            COL,
            "",
            "",
            {
                "validation_type": "negative",
                "negative_expression": "status = 'DELETED'",
            },
        )
        assert "error" not in result
        assert "NOT (status = 'DELETED')" in result["compiled_sql"]
