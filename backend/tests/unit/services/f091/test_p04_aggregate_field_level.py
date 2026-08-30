"""P04 — Aggregate + Field-Level Tests."""

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


BASE = {"source_dataset": "gl_source", "target_dataset": "gl_target", "threshold_pass": 100}


# ── Aggregate ────────────────────────────────────────────────


class TestAggregateBasic:
    def test_requires_aggregate_column(self, compiler):
        params = {**BASE, "reconciliation_type": "aggregate"}
        result = _compile(compiler, params)
        assert "error" in result
        assert "aggregate_column" in result["error"]

    def test_default_function_is_sum(self, compiler):
        params = {**BASE, "reconciliation_type": "aggregate", "aggregate_column": "amount"}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "SUM" in sql

    def test_source_agg_in_sql(self, compiler):
        params = {**BASE, "reconciliation_type": "aggregate", "aggregate_column": "amount"}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "source_agg" in sql

    def test_target_agg_in_sql(self, compiler):
        params = {**BASE, "reconciliation_type": "aggregate", "aggregate_column": "amount"}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "target_agg" in sql

    def test_references_both_datasets(self, compiler):
        params = {**BASE, "reconciliation_type": "aggregate", "aggregate_column": "amount"}
        sql = _compile(compiler, params)["compiled_sql"]
        assert "gl_source" in sql
        assert "gl_target" in sql


class TestAggregateFunction:
    @pytest.mark.parametrize("fn", ["SUM", "COUNT", "AVG", "MIN", "MAX"])
    def test_valid_function(self, compiler, fn):
        params = {
            **BASE,
            "reconciliation_type": "aggregate",
            "aggregate_column": "amount",
            "aggregate_function": fn,
        }
        result = _compile(compiler, params)
        assert "error" not in result
        assert fn in result["compiled_sql"]

    def test_invalid_function_errors(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "aggregate",
            "aggregate_column": "amount",
            "aggregate_function": "MEDIAN",
        }
        result = _compile(compiler, params)
        assert "error" in result

    def test_case_insensitive_function(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "aggregate",
            "aggregate_column": "amount",
            "aggregate_function": "sum",
        }
        result = _compile(compiler, params)
        assert "error" not in result


class TestAggregateFilters:
    def test_source_filter(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "aggregate",
            "aggregate_column": "amount",
            "source_filter": "year = 2024",
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "year = 2024" in sql

    def test_target_filter(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "aggregate",
            "aggregate_column": "amount",
            "target_filter": "posted = true",
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "posted = true" in sql


class TestAggregateGroupBy:
    def test_group_by_in_sql(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "aggregate",
            "aggregate_column": "amount",
            "group_by_columns": ["region"],
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "GROUP BY" in sql
        assert '"region"' in sql

    def test_group_by_full_outer_join(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "aggregate",
            "aggregate_column": "amount",
            "group_by_columns": ["region"],
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "FULL OUTER JOIN" in sql

    def test_multiple_group_columns(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "aggregate",
            "aggregate_column": "amount",
            "group_by_columns": ["region", "month"],
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert '"region"' in sql
        assert '"month"' in sql


class TestAggregateSpark:
    def test_spark_has_agg(self, compiler):
        params = {**BASE, "reconciliation_type": "aggregate", "aggregate_column": "amount"}
        spark = _compile(compiler, params)["compiled_spark"]
        assert "source_agg" in spark
        assert "target_agg" in spark


# ── Field Level ──────────────────────────────────────────────


class TestFieldLevelBasic:
    def test_requires_join_keys(self, compiler):
        params = {**BASE, "reconciliation_type": "field_level", "compare_columns": ["name"]}
        result = _compile(compiler, params)
        assert "error" in result
        assert "join_keys" in result["error"]

    def test_requires_compare_columns(self, compiler):
        params = {**BASE, "reconciliation_type": "field_level", "join_keys": ["id"]}
        result = _compile(compiler, params)
        assert "error" in result
        assert "compare_columns" in result["error"]

    def test_inner_join(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "field_level",
            "join_keys": ["id"],
            "compare_columns": ["name"],
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "INNER JOIN" in sql

    def test_field_match_count(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "field_level",
            "join_keys": ["id"],
            "compare_columns": ["name"],
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "field_match_count" in sql

    def test_field_mismatch_count(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "field_level",
            "join_keys": ["id"],
            "compare_columns": ["name"],
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "field_mismatch_count" in sql

    def test_matched_count(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "field_level",
            "join_keys": ["id"],
            "compare_columns": ["name"],
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "matched_count" in sql


class TestFieldLevelColumns:
    def test_single_compare_column(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "field_level",
            "join_keys": ["id"],
            "compare_columns": ["email"],
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert '"email"' in sql

    def test_multiple_compare_columns(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "field_level",
            "join_keys": ["id"],
            "compare_columns": ["name", "email", "phone"],
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert '"name"' in sql
        assert '"email"' in sql
        assert '"phone"' in sql
        assert "AND" in sql


class TestFieldLevelFilters:
    def test_source_filter(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "field_level",
            "join_keys": ["id"],
            "compare_columns": ["name"],
            "source_filter": "active = true",
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "active = true" in sql

    def test_target_filter(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "field_level",
            "join_keys": ["id"],
            "compare_columns": ["name"],
            "target_filter": "verified = true",
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "verified = true" in sql


class TestFieldLevelViolation:
    def test_violation_sql_shows_mismatches(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "field_level",
            "join_keys": ["id"],
            "compare_columns": ["name"],
        }
        vsql = _compile(compiler, params)["violation_sql"]
        assert "NOT" in vsql

    def test_violation_has_both_sides(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "field_level",
            "join_keys": ["id"],
            "compare_columns": ["name"],
        }
        vsql = _compile(compiler, params)["violation_sql"]
        assert "a.*" in vsql
        assert "b.*" in vsql


class TestFieldLevelSpark:
    def test_spark_inner_join(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "field_level",
            "join_keys": ["id"],
            "compare_columns": ["name"],
        }
        spark = _compile(compiler, params)["compiled_spark"]
        assert '"inner"' in spark

    def test_spark_field_match(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "field_level",
            "join_keys": ["id"],
            "compare_columns": ["name"],
        }
        spark = _compile(compiler, params)["compiled_spark"]
        assert "field_match_count" in spark
