"""P03 — One-to-One Matching Tests."""

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


BASE = {"source_dataset": "invoices", "target_dataset": "payments", "threshold_pass": 100}


class TestOneToOneBasic:
    def test_requires_join_keys(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one"}
        result = _compile(compiler, params)
        assert "error" in result
        assert "join_keys" in result["error"]

    def test_full_outer_join(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["invoice_id"]}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "FULL OUTER JOIN" in sql

    def test_matched_count(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["id"]}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "matched_count" in sql

    def test_missing_in_target(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["id"]}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "missing_in_target" in sql

    def test_extra_in_target(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["id"]}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "extra_in_target" in sql

    def test_source_count_subquery(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["id"]}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "source_count" in sql

    def test_target_count_subquery(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["id"]}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "target_count" in sql


class TestOneToOneFilters:
    def test_source_filter(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "one_to_one",
            "join_keys": ["id"],
            "source_filter": "status = 'paid'",
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "status = 'paid'" in sql

    def test_target_filter(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "one_to_one",
            "join_keys": ["id"],
            "target_filter": "type = 'credit'",
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "type = 'credit'" in sql


class TestOneToOneJoinKeys:
    def test_single_key(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["order_id"]}
        sql = _compile(compiler, params)["compiled_sql"]
        assert '"order_id"' in sql

    def test_multiple_keys(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["region", "date"]}
        sql = _compile(compiler, params)["compiled_sql"]
        assert '"region"' in sql
        assert '"date"' in sql
        assert "AND" in sql

    def test_join_condition_uses_both_aliases(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["id"]}
        sql = _compile(compiler, params)["compiled_sql"]
        assert 'a."id"' in sql
        assert 'b."id"' in sql


class TestOneToOneViolation:
    def test_violation_sql_has_union(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["id"]}
        vsql = _compile(compiler, params)["violation_sql"]
        assert "UNION ALL" in vsql

    def test_violation_shows_missing(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["id"]}
        vsql = _compile(compiler, params)["violation_sql"]
        assert "missing_in_target" in vsql

    def test_violation_shows_extra(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["id"]}
        vsql = _compile(compiler, params)["violation_sql"]
        assert "extra_in_target" in vsql


class TestOneToOneSpark:
    def test_spark_full_outer(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["id"]}
        spark = _compile(compiler, params)["compiled_spark"]
        assert "full_outer" in spark

    def test_spark_matched(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["id"]}
        spark = _compile(compiler, params)["compiled_spark"]
        assert "matched_count" in spark

    def test_spark_missing(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["id"]}
        spark = _compile(compiler, params)["compiled_spark"]
        assert "missing_in_target" in spark
