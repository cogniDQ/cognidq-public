"""P03 — Reference Lookup Mode tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


TABLE = '"s"."t"'
COL = "country_code"


class TestReferenceLookupBasic:
    def test_generates_left_join(self, compiler):
        result = compiler._validity_reference_lookup(
            TABLE,
            COL,
            "",
            "",
            {
                "reference_dataset": "ref_schema.countries",
                "reference_column": "code",
            },
        )
        sql = result["compiled_sql"]
        assert "LEFT JOIN" in sql
        assert 'ref."code"' in sql
        assert "total_rows" in sql
        assert "valid_rows" in sql

    def test_missing_ref_dataset_error(self, compiler):
        result = compiler._validity_reference_lookup(
            TABLE,
            COL,
            "",
            "",
            {
                "reference_column": "code",
            },
        )
        assert result["error"] is True
        assert "reference_dataset" in result["error_message"]

    def test_missing_ref_column_error(self, compiler):
        result = compiler._validity_reference_lookup(
            TABLE,
            COL,
            "",
            "",
            {
                "reference_dataset": "countries",
            },
        )
        assert result["error"] is True
        assert "reference_column" in result["error_message"]

    def test_invalid_identifier_rejected(self, compiler):
        result = compiler._validity_reference_lookup(
            TABLE,
            COL,
            "",
            "",
            {
                "reference_dataset": "countries; DROP TABLE",
                "reference_column": "code",
            },
        )
        assert result["error"] is True
        assert "identifier" in result["error_message"].lower()


class TestReferenceLookupNullHandling:
    def test_fail_mode(self, compiler):
        result = compiler._validity_reference_lookup(
            TABLE,
            COL,
            "",
            "",
            {
                "reference_dataset": "countries",
                "reference_column": "code",
                "null_handling": "fail",
            },
        )
        sql = result["compiled_sql"]
        # In fail mode NULLs counted as invalid
        assert "IS NULL" in sql
        assert "skipped_rows" not in sql

    def test_skip_mode(self, compiler):
        result = compiler._validity_reference_lookup(
            TABLE,
            COL,
            "",
            "",
            {
                "reference_dataset": "countries",
                "reference_column": "code",
                "null_handling": "skip",
            },
        )
        sql = result["compiled_sql"]
        assert "skipped_rows" in sql

    def test_pass_mode(self, compiler):
        result = compiler._validity_reference_lookup(
            TABLE,
            COL,
            "",
            "",
            {
                "reference_dataset": "countries",
                "reference_column": "code",
                "null_handling": "pass",
            },
        )
        sql = result["compiled_sql"]
        assert "IS NULL THEN 1" in sql  # NULLs counted as valid
        assert "skipped_rows" not in sql


class TestReferenceLookupViaDispatcher:
    def test_dispatch_to_reference_lookup(self, compiler):
        result = compiler._compile_validity_rule(
            TABLE,
            COL,
            "",
            "",
            {
                "validation_type": "reference_lookup",
                "reference_dataset": "ref.countries",
                "reference_column": "code",
            },
        )
        assert "error" not in result
        assert "LEFT JOIN" in result["compiled_sql"]

    def test_with_filter_expression(self, compiler):
        result = compiler._compile_validity_rule(
            TABLE,
            COL,
            "",
            "",
            {
                "validation_type": "reference_lookup",
                "reference_dataset": "countries",
                "reference_column": "code",
                "filter_expression": "active = true",
            },
        )
        assert "error" not in result
        assert "active = true" in result["compiled_sql"]
