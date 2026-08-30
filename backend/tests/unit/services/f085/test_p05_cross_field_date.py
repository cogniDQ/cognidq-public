"""P05 — Cross-Field & Date Logic Modes tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


TABLE = '"s"."t"'


# ===================================================================
# Cross-field validation
# ===================================================================
class TestCrossFieldBasic:
    def test_equality_comparison(self, compiler):
        result = compiler._validity_cross_field(
            TABLE,
            "col_a",
            "",
            "",
            {
                "comparison_column": "col_b",
                "comparison_operator": "=",
            },
        )
        sql = result["compiled_sql"]
        assert '"col_a" = "col_b"' in sql

    def test_less_than(self, compiler):
        result = compiler._validity_cross_field(
            TABLE,
            "start_date",
            "",
            "",
            {
                "comparison_column": "end_date",
                "comparison_operator": "<",
            },
        )
        sql = result["compiled_sql"]
        assert '"start_date" < "end_date"' in sql

    def test_missing_comparison_column_error(self, compiler):
        result = compiler._validity_cross_field(
            TABLE,
            "a",
            "",
            "",
            {
                "comparison_operator": "=",
            },
        )
        assert result["error"] is True
        assert "comparison_column" in result["error_message"]

    def test_invalid_operator_error(self, compiler):
        result = compiler._validity_cross_field(
            TABLE,
            "a",
            "",
            "",
            {
                "comparison_column": "b",
                "comparison_operator": "LIKE",
            },
        )
        assert result["error"] is True
        assert "LIKE" in result["error_message"]

    @pytest.mark.parametrize("op", ["=", "!=", "<", ">", "<=", ">="])
    def test_all_operators_accepted(self, compiler, op):
        result = compiler._validity_cross_field(
            TABLE,
            "a",
            "",
            "",
            {
                "comparison_column": "b",
                "comparison_operator": op,
            },
        )
        assert "error" not in result
        assert op in result["compiled_sql"]


class TestCrossFieldNullHandling:
    @pytest.mark.parametrize("mode", ["fail", "skip", "pass"])
    def test_all_modes(self, compiler, mode):
        result = compiler._validity_cross_field(
            TABLE,
            "a",
            "",
            "",
            {
                "comparison_column": "b",
                "comparison_operator": "=",
                "null_handling": mode,
            },
        )
        assert "error" not in result
        sql = result["compiled_sql"]
        if mode == "skip":
            assert "skipped_rows" in sql


# ===================================================================
# Date logic validation
# ===================================================================
class TestDateLogicBasic:
    def test_date_cast_in_sql(self, compiler):
        result = compiler._validity_date_logic(
            TABLE,
            "start_date",
            "",
            "",
            {
                "comparison_column": "end_date",
                "comparison_operator": "<=",
            },
        )
        sql = result["compiled_sql"]
        assert "CAST" in sql
        assert "DATE" in sql
        assert '"start_date"' in sql
        assert '"end_date"' in sql

    def test_missing_comparison_column_error(self, compiler):
        result = compiler._validity_date_logic(
            TABLE,
            "start_date",
            "",
            "",
            {
                "comparison_operator": "<=",
            },
        )
        assert result["error"] is True

    def test_invalid_operator_error(self, compiler):
        result = compiler._validity_date_logic(
            TABLE,
            "start_date",
            "",
            "",
            {
                "comparison_column": "end_date",
                "comparison_operator": "BETWEEN",
            },
        )
        assert result["error"] is True


class TestDateLogicNullHandling:
    @pytest.mark.parametrize("mode", ["fail", "skip", "pass"])
    def test_all_modes(self, compiler, mode):
        result = compiler._validity_date_logic(
            TABLE,
            "start",
            "",
            "",
            {
                "comparison_column": "end",
                "comparison_operator": "<=",
                "null_handling": mode,
            },
        )
        assert "error" not in result
        sql = result["compiled_sql"]
        if mode == "skip":
            assert "skipped_rows" in sql


class TestCrossFieldViaDispatcher:
    def test_cross_field_dispatch(self, compiler):
        result = compiler._compile_validity_rule(
            TABLE,
            "a",
            "",
            "",
            {
                "validation_type": "cross_field",
                "comparison_column": "b",
                "comparison_operator": "=",
            },
        )
        assert "error" not in result
        assert '"a" = "b"' in result["compiled_sql"]

    def test_date_logic_dispatch(self, compiler):
        result = compiler._compile_validity_rule(
            TABLE,
            "start",
            "",
            "",
            {
                "validation_type": "date_logic",
                "comparison_column": "end",
                "comparison_operator": "<=",
            },
        )
        assert "error" not in result
        assert "CAST" in result["compiled_sql"]
