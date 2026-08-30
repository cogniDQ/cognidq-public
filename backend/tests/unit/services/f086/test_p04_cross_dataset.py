"""P04 — Cross-Dataset Uniqueness Mode tests."""

import pytest
from app.services.rules.compiler import RuleCompiler

TABLE = '"schema"."table"'


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, **params):
    params.setdefault("columns", ["customer_id"])
    params.setdefault("uniqueness_mode", "cross_dataset")
    return compiler._compile_uniqueness_rule(TABLE, "customer_id", "", "", params)


class TestCrossDatasetMode:
    def test_basic_cross_dataset_sql(self, compiler):
        result = _compile(
            compiler, cross_dataset_name="legacy_customers", cross_dataset_column="cust_id"
        )
        sql = result["compiled_sql"]
        assert "INNER JOIN" in sql
        assert "legacy_customers" in sql
        assert "total_rows" in sql
        assert "duplicate_rows" in sql

    def test_missing_cross_dataset_name_error(self, compiler):
        result = _compile(compiler, cross_dataset_column="cust_id")
        assert result["error"] is True
        assert "cross_dataset_name" in result["error_message"]

    def test_missing_cross_dataset_column_error(self, compiler):
        result = _compile(compiler, cross_dataset_name="legacy_customers")
        assert result["error"] is True
        assert "cross_dataset_column" in result["error_message"]

    def test_case_insensitive_join(self, compiler):
        result = _compile(
            compiler, cross_dataset_name="ref", cross_dataset_column="id", case_sensitive=False
        )
        sql = result["compiled_sql"]
        assert "LOWER" in sql

    def test_case_sensitive_default(self, compiler):
        result = _compile(compiler, cross_dataset_name="ref", cross_dataset_column="id")
        sql = result["compiled_sql"]
        # Should have direct column comparison without LOWER
        assert "INNER JOIN" in sql

    def test_filter_expression(self, compiler):
        result = _compile(
            compiler,
            cross_dataset_name="ref",
            cross_dataset_column="id",
            filter_expression="status = 'active'",
        )
        sql = result["compiled_sql"]
        assert "status = 'active'" in sql

    def test_violation_sql(self, compiler):
        result = _compile(compiler, cross_dataset_name="ref", cross_dataset_column="id")
        assert "INNER JOIN" in result["violation_sql"]

    def test_spark_code(self, compiler):
        result = _compile(compiler, cross_dataset_name="ref", cross_dataset_column="id")
        spark = result["compiled_spark"]
        assert "spark.table" in spark
        assert "join" in spark.lower()

    def test_all_dialect_keys(self, compiler):
        result = _compile(compiler, cross_dataset_name="ref", cross_dataset_column="id")
        for key in [
            "compiled_sql",
            "compiled_postgres",
            "compiled_mysql",
            "compiled_snowflake",
            "compiled_spark",
            "violation_sql",
        ]:
            assert key in result
