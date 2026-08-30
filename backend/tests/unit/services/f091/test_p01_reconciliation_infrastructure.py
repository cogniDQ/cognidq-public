"""P01 — Reconciliation Infrastructure Tests (constants, error, dispatcher, filter, smoke)."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, params):
    """Compile a reconciliation rule using canonical dict pattern."""
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


BASE = {
    "source_dataset": "src_table",
    "target_dataset": "tgt_table",
    "threshold_pass": 100,
}


# ── Constants ────────────────────────────────────────────────


class TestConstants:
    def test_valid_reconciliation_types(self):
        expected = {
            "record_count",
            "one_to_one",
            "aggregate",
            "field_level",
            "tolerance",
            "missing_extra",
        }
        assert RuleCompiler.VALID_RECONCILIATION_TYPES == expected

    def test_valid_aggregate_functions(self):
        expected = {"SUM", "COUNT", "AVG", "MIN", "MAX"}
        assert RuleCompiler.VALID_AGGREGATE_FUNCTIONS == expected


# ── Error Result ─────────────────────────────────────────────


class TestErrorResult:
    def test_error_result_has_error_key(self):
        result = RuleCompiler._reconciliation_error_result("boom")
        assert "error" in result
        assert result["error"] == "boom"

    def test_error_result_has_five_keys(self):
        result = RuleCompiler._reconciliation_error_result("x")
        for k in ("compiled_sql", "compiled_postgres", "compiled_spark", "violation_sql", "error"):
            assert k in result

    def test_error_result_sql_has_error_prefix(self):
        result = RuleCompiler._reconciliation_error_result("test msg")
        assert result["compiled_sql"].startswith("-- ERROR:")

    def test_error_result_spark_has_hash_prefix(self):
        result = RuleCompiler._reconciliation_error_result("test msg")
        assert result["compiled_spark"].startswith("# ERROR:")


# ── Type Validation ──────────────────────────────────────────


class TestTypeValidation:
    @pytest.mark.parametrize(
        "rtype",
        ["record_count", "one_to_one", "aggregate", "field_level", "tolerance", "missing_extra"],
    )
    def test_valid_type_does_not_error(self, compiler, rtype):
        params = {
            **BASE,
            "reconciliation_type": rtype,
            "join_keys": ["id"],
            "compare_columns": ["name"],
            "aggregate_column": "amount",
            "tolerance_type": "absolute",
            "tolerance_value": 0.01,
        }
        result = _compile(compiler, params)
        assert "error" not in result

    def test_unknown_type_errors(self, compiler):
        params = {**BASE, "reconciliation_type": "temporal"}
        result = _compile(compiler, params)
        assert "error" in result
        assert "Unknown" in result["error"]

    def test_none_type_errors(self, compiler):
        params = {**BASE}
        result = _compile(compiler, params)
        assert "error" in result


# ── Required Fields ──────────────────────────────────────────


class TestRequiredFields:
    def test_missing_source_dataset(self, compiler):
        result = _compile(
            compiler,
            {"reconciliation_type": "record_count", "target_dataset": "t", "threshold_pass": 100},
        )
        assert "error" in result
        assert "source_dataset" in result["error"]

    def test_missing_target_dataset(self, compiler):
        result = _compile(
            compiler,
            {"reconciliation_type": "record_count", "source_dataset": "s", "threshold_pass": 100},
        )
        assert "error" in result
        assert "target_dataset" in result["error"]


# ── Filter Validation ────────────────────────────────────────


class TestFilterValidation:
    def test_dangerous_source_filter(self, compiler):
        params = {**BASE, "reconciliation_type": "record_count", "source_filter": "x; DROP TABLE y"}
        result = _compile(compiler, params)
        assert "error" in result
        assert "source_filter" in result["error"]

    def test_dangerous_target_filter(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "record_count",
            "target_filter": "1; DELETE FROM z",
        }
        result = _compile(compiler, params)
        assert "error" in result
        assert "target_filter" in result["error"]

    def test_safe_filter_allowed(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "record_count",
            "source_filter": "status = 'active'",
        }
        result = _compile(compiler, params)
        assert "error" not in result


# ── Dispatcher Routing ───────────────────────────────────────


class TestDispatcherRouting:
    def test_record_count_returns_sql(self, compiler):
        params = {**BASE, "reconciliation_type": "record_count"}
        result = _compile(compiler, params)
        assert "source_count" in result["compiled_sql"]

    def test_one_to_one_returns_full_outer(self, compiler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["id"]}
        result = _compile(compiler, params)
        assert "FULL OUTER JOIN" in result["compiled_sql"]

    def test_aggregate_returns_agg(self, compiler):
        params = {**BASE, "reconciliation_type": "aggregate", "aggregate_column": "amount"}
        result = _compile(compiler, params)
        assert "source_agg" in result["compiled_sql"]

    def test_field_level_returns_inner_join(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "field_level",
            "join_keys": ["id"],
            "compare_columns": ["name"],
        }
        result = _compile(compiler, params)
        assert "INNER JOIN" in result["compiled_sql"]

    def test_tolerance_returns_tolerance_sql(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "absolute",
            "tolerance_value": 0.5,
        }
        result = _compile(compiler, params)
        assert "within_tolerance" in result["compiled_sql"]

    def test_missing_extra_returns_anti_join(self, compiler):
        params = {**BASE, "reconciliation_type": "missing_extra", "join_keys": ["id"]}
        result = _compile(compiler, params)
        assert "missing_in_target" in result["compiled_sql"]


# ── Quick SQL Smoke ──────────────────────────────────────────


class TestQuickSmoke:
    @pytest.mark.parametrize(
        "rtype,extra",
        [
            ("record_count", {}),
            ("one_to_one", {"join_keys": ["id"]}),
            ("aggregate", {"aggregate_column": "amt"}),
            ("field_level", {"join_keys": ["id"], "compare_columns": ["val"]}),
            (
                "tolerance",
                {"join_keys": ["id"], "tolerance_type": "absolute", "tolerance_value": 1},
            ),
            ("missing_extra", {"join_keys": ["id"]}),
        ],
    )
    def test_compiled_sql_not_empty(self, compiler, rtype, extra):
        params = {**BASE, "reconciliation_type": rtype, **extra}
        result = _compile(compiler, params)
        assert result["compiled_sql"]
        assert "error" not in result

    @pytest.mark.parametrize(
        "rtype,extra",
        [
            ("record_count", {}),
            ("one_to_one", {"join_keys": ["id"]}),
            ("aggregate", {"aggregate_column": "amt"}),
            ("field_level", {"join_keys": ["id"], "compare_columns": ["val"]}),
            (
                "tolerance",
                {"join_keys": ["id"], "tolerance_type": "absolute", "tolerance_value": 1},
            ),
            ("missing_extra", {"join_keys": ["id"]}),
        ],
    )
    def test_spark_not_empty(self, compiler, rtype, extra):
        params = {**BASE, "reconciliation_type": rtype, **extra}
        result = _compile(compiler, params)
        assert result["compiled_spark"]

    @pytest.mark.parametrize(
        "rtype,extra",
        [
            ("record_count", {}),
            ("one_to_one", {"join_keys": ["id"]}),
            ("aggregate", {"aggregate_column": "amt"}),
            ("field_level", {"join_keys": ["id"], "compare_columns": ["val"]}),
            (
                "tolerance",
                {"join_keys": ["id"], "tolerance_type": "absolute", "tolerance_value": 1},
            ),
            ("missing_extra", {"join_keys": ["id"]}),
        ],
    )
    def test_violation_sql_present(self, compiler, rtype, extra):
        params = {**BASE, "reconciliation_type": rtype, **extra}
        result = _compile(compiler, params)
        assert "violation_sql" in result
