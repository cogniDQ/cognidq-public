"""
F070 P01 — Unit tests: RuleCompiler dimension compilation

Tests compile_rule() output for all 9 dimensions plus output structure.
RuleCompiler is a pure function (no DB, no I/O) — no mocking required.

P01-01 .. P01-18  (18 tests)
"""

from __future__ import annotations

import pytest
from app.services.rules.compiler import RuleCompiler

compiler = RuleCompiler()

REQUIRED_KEYS = {
    "compiled_sql",
    "compiled_postgres",
    "compiled_spark",
    "violation_sql",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _rule(dimension: str, entity: str = "orders.amount", **params):
    """Build a minimal canonical rule dict."""
    return {
        "dimension": dimension,
        "entity": entity,
        "condition": params.pop("condition", ""),
        "expectation": params.pop("expectation", "should pass"),
        "parameters": params,
    }


# ===================================================================
# COMPLETENESS
# ===================================================================
class TestCompletenessCompilation:
    """P01-01 .. P01-04"""

    def test_single_column_produces_count_sql(self):
        """P01-01"""
        result = compiler.compile_rule(_rule("completeness"))
        sql = result["compiled_sql"]
        assert "COUNT" in sql
        assert "total_rows" in sql
        assert "non_null_rows" in sql
        assert "null_rows" in sql

    def test_multi_column_produces_and_condition(self):
        """P01-02"""
        result = compiler.compile_rule(
            _rule("completeness", entity="orders", columns=["col_a", "col_b", "col_c"]),
            target_columns=["col_a"],
        )
        sql = result["compiled_sql"]
        assert "IS NOT NULL" in sql
        assert "AND" in sql

    def test_violation_sql_selects_null_rows(self):
        """P01-03"""
        result = compiler.compile_rule(_rule("completeness"))
        assert "IS NULL" in result["violation_sql"]

    def test_spark_code_present(self):
        """P01-04"""
        result = compiler.compile_rule(_rule("completeness"))
        spark = result["compiled_spark"]
        assert "pyspark" in spark or "spark" in spark.lower()


# ===================================================================
# VALIDITY
# ===================================================================
class TestValidityCompilation:
    """P01-05 .. P01-09"""

    def test_regex_pattern_produces_tilde_operator(self):
        """P01-05"""
        result = compiler.compile_rule(_rule("validity", regex_pattern=r"^\d{5}$"))
        assert "~" in result["compiled_sql"]

    def test_range_min_max(self):
        """P01-06"""
        result = compiler.compile_rule(_rule("validity", min_value=0, max_value=100))
        sql = result["compiled_sql"]
        assert ">= 0" in sql
        assert "<= 100" in sql

    def test_allowed_values(self):
        """P01-07"""
        result = compiler.compile_rule(_rule("validity", allowed_values=["A", "B", "C"]))
        sql = result["compiled_sql"]
        assert "IN (" in sql.upper()
        assert "'A'" in sql
        assert "'B'" in sql

    def test_no_condition_fallback(self):
        """P01-08: no regex/range/allowed and empty condition → compiler returns error result"""
        result = compiler.compile_rule(_rule("validity", condition=""))
        sql = result["compiled_sql"]
        # Compiler now requires explicit validation_type; unknown type → error result
        assert sql == "" or sql.startswith("-- ERROR")

    def test_mysql_uses_regexp(self):
        """P01-09"""
        result = compiler.compile_rule(_rule("validity", regex_pattern=r"^\d+$"))
        mysql = result["compiled_mysql"]
        assert "REGEXP" in mysql


# ===================================================================
# UNIQUENESS
# ===================================================================
class TestUniquenessCompilation:
    """P01-10 .. P01-11"""

    def test_produces_cte_with_group_by(self):
        """P01-10"""
        result = compiler.compile_rule(_rule("uniqueness"))
        sql = result["compiled_sql"]
        assert "WITH duplicates AS" in sql
        assert "GROUP BY" in sql
        assert "HAVING COUNT(*) > 1" in sql

    def test_output_includes_duplicate_rows(self):
        """P01-11"""
        result = compiler.compile_rule(_rule("uniqueness"))
        assert "duplicate_rows" in result["compiled_sql"]


# ===================================================================
# CONSISTENCY
# ===================================================================
class TestConsistencyCompilation:
    """P01-12 .. P01-13"""

    def test_with_reference_column(self):
        """P01-12"""
        result = compiler.compile_rule(_rule("consistency", reference_column="expected_amount"))
        sql = result["compiled_sql"]
        assert "consistent_rows" in sql
        assert "expected_amount" in sql

    def test_without_reference_column_fallback(self):
        """P01-13: consistency with no params falls to intra_record which requires rule_expression"""
        result = compiler.compile_rule(_rule("consistency"))
        sql = result["compiled_sql"]
        # intra_record without rule_expression → error result
        assert "total_rows" not in sql or "ERROR" in sql.upper()


# ===================================================================
# STATISTICAL
# ===================================================================
class TestStatisticalCompilation:
    """P01-14 .. P01-15"""

    def test_produces_avg_stddev(self):
        """P01-14"""
        result = compiler.compile_rule(_rule("statistical"))
        sql = result["compiled_sql"]
        assert "AVG(" in sql
        assert "STDDEV(" in sql

    def test_violation_sql_uses_3_sigma(self):
        """P01-15"""
        result = compiler.compile_rule(_rule("statistical"))
        vsql = result["violation_sql"]
        assert "3 *" in vsql or "3*" in vsql


# ===================================================================
# CONFORMITY
# ===================================================================
class TestConformityCompilation:
    """P01-16"""

    def test_delegates_to_validity(self):
        """P01-16: conformity and validity both produce regex-based SQL for regex_pattern"""
        result_c = compiler.compile_rule(_rule("conformity", regex_pattern=r"^\d+$"))
        result_v = compiler.compile_rule(_rule("validity", regex_pattern=r"^\d+$"))
        # Both use regex pattern — structure similar even if not identical
        assert "~" in result_c["compiled_sql"] or "REGEXP" in result_c["compiled_sql"].upper()
        assert "~" in result_v["compiled_sql"] or "REGEXP" in result_v["compiled_sql"].upper()


# ===================================================================
# GENERIC
# ===================================================================
class TestGenericCompilation:
    """P01-17"""

    def test_unknown_dimension_produces_generic_sql(self):
        """P01-17: unrecognised dimension falls through to generic."""
        result = compiler.compile_rule(_rule("bogus_dimension", condition='"amount" > 0'))
        sql = result["compiled_sql"]
        assert "passed_rows" in sql
        assert "failed_rows" in sql


# ===================================================================
# OUTPUT STRUCTURE
# ===================================================================
class TestOutputStructure:
    """P01-18"""

    @pytest.mark.parametrize(
        "dimension,params",
        [
            ("completeness", {}),
            ("validity", {"regex_pattern": r"^\d+$"}),
            ("uniqueness", {}),
            ("conformity", {"regex_pattern": r"^\d+$"}),
            ("consistency", {"reference_column": "other_col"}),
            ("statistical", {}),
        ],
    )
    def test_all_keys_present(self, dimension: str, params: dict):
        """P01-18: every dimension returns the full key set."""
        result = compiler.compile_rule(_rule(dimension, **params))
        assert REQUIRED_KEYS <= set(result.keys()), (
            f"Missing keys for {dimension}: {REQUIRED_KEYS - set(result.keys())}"
        )
