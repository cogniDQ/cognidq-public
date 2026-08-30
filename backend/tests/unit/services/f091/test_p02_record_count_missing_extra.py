"""P02 — Record Count + Missing/Extra Tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, params):
    return compiler.compile_rule(
        {
            "dimension": "reconciliation",
            "entity": "src",
            "condition": "",
            "expectation": "100%",
            "parameters": params,
        },
        target_table="src",
    )


BASE = {"source_dataset": "orders", "target_dataset": "orders_copy", "threshold_pass": 100}


# ── Record Count ─────────────────────────────────────────────


class TestRecordCountBasic:
    def test_sql_has_two_count_subqueries(self, compiler):
        params = {**BASE, "reconciliation_type": "record_count"}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "COUNT(*)" in sql
        assert "source_count" in sql
        assert "target_count" in sql

    def test_sql_references_both_datasets(self, compiler):
        params = {**BASE, "reconciliation_type": "record_count"}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "orders" in sql
        assert "orders_copy" in sql

    def test_source_filter_applied(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "record_count",
            "source_filter": "status = 'active'",
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "status = 'active'" in sql

    def test_target_filter_applied(self, compiler):
        params = {**BASE, "reconciliation_type": "record_count", "target_filter": "region = 'US'"}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "region = 'US'" in sql

    def test_both_filters(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "record_count",
            "source_filter": "a = 1",
            "target_filter": "b = 2",
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "a = 1" in sql
        assert "b = 2" in sql

    def test_spark_code(self, compiler):
        params = {**BASE, "reconciliation_type": "record_count"}
        spark = _compile(compiler, params)["compiled_spark"]
        assert "source_count" in spark
        assert "target_count" in spark

    def test_violation_sql(self, compiler):
        params = {**BASE, "reconciliation_type": "record_count"}
        vsql = _compile(compiler, params)["violation_sql"]
        assert "source" in vsql.lower()
        assert "target" in vsql.lower()


# ── Missing/Extra ────────────────────────────────────────────


class TestMissingExtraBasic:
    def test_requires_join_keys(self, compiler):
        params = {**BASE, "reconciliation_type": "missing_extra"}
        result = _compile(compiler, params)
        assert "error" in result
        assert "join_keys" in result["error"]

    def test_sql_has_left_join(self, compiler):
        params = {**BASE, "reconciliation_type": "missing_extra", "join_keys": ["order_id"]}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "LEFT JOIN" in sql

    def test_missing_in_target_count(self, compiler):
        params = {**BASE, "reconciliation_type": "missing_extra", "join_keys": ["id"]}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "missing_in_target" in sql

    def test_extra_in_target_count(self, compiler):
        params = {**BASE, "reconciliation_type": "missing_extra", "join_keys": ["id"]}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "extra_in_target" in sql

    def test_source_count_present(self, compiler):
        params = {**BASE, "reconciliation_type": "missing_extra", "join_keys": ["id"]}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "source_count" in sql

    def test_target_count_present(self, compiler):
        params = {**BASE, "reconciliation_type": "missing_extra", "join_keys": ["id"]}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "target_count" in sql

    def test_source_filter(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "missing_extra",
            "join_keys": ["id"],
            "source_filter": "active = true",
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "active = true" in sql

    def test_target_filter(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "missing_extra",
            "join_keys": ["id"],
            "target_filter": "deleted = false",
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "deleted = false" in sql

    def test_spark_has_anti_join(self, compiler):
        params = {**BASE, "reconciliation_type": "missing_extra", "join_keys": ["id"]}
        spark = _compile(compiler, params)["compiled_spark"]
        assert "left_anti" in spark

    def test_violation_sql_union(self, compiler):
        params = {**BASE, "reconciliation_type": "missing_extra", "join_keys": ["id"]}
        vsql = _compile(compiler, params)["violation_sql"]
        assert "UNION ALL" in vsql

    def test_multiple_join_keys(self, compiler):
        params = {**BASE, "reconciliation_type": "missing_extra", "join_keys": ["region", "date"]}
        sql = _compile(compiler, params)["compiled_sql"]
        assert '"region"' in sql
        assert '"date"' in sql
