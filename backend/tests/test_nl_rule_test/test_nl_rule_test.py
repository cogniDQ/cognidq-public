"""
F107 — NL Rule Test Preview Tests
35+ tests covering schemas, expression builder, condition builder,
warning detection, and endpoint registration.
"""

from uuid import uuid4

import pytest
from app.schemas.nl_compiler import CompiledCheckConfig
from app.schemas.nl_rule_test import (
    TestPreviewRequest,
    TestPreviewResponse,
    TestStatistics,
)
from app.services.nl_rule_test.preview import NLRuleTestPreview

# ── helpers ──

svc = NLRuleTestPreview()


def cfg(**kwargs) -> CompiledCheckConfig:
    defaults = {
        "check_type": "completeness",
        "subtype": "null",
        "dataset_id": str(uuid4()),
        "rule_name": "test_rule",
        "severity": "medium",
        "config": {"columns": ["email"]},
    }
    defaults.update(kwargs)
    return CompiledCheckConfig(**defaults)


# ══════════════════════════════════════
# 1. Schema Tests
# ══════════════════════════════════════


class TestSchemas:
    def test_request_defaults(self):
        req = TestPreviewRequest(compiled_config=cfg())
        assert req.sample_size == 50
        assert req.violation_limit == 10

    def test_request_custom_sizes(self):
        req = TestPreviewRequest(compiled_config=cfg(), sample_size=100, violation_limit=25)
        assert req.sample_size == 100
        assert req.violation_limit == 25

    def test_request_sample_size_min(self):
        with pytest.raises(Exception):
            TestPreviewRequest(compiled_config=cfg(), sample_size=0)

    def test_request_sample_size_max(self):
        with pytest.raises(Exception):
            TestPreviewRequest(compiled_config=cfg(), sample_size=1001)

    def test_request_violation_limit_min(self):
        with pytest.raises(Exception):
            TestPreviewRequest(compiled_config=cfg(), violation_limit=0)

    def test_response_success(self):
        resp = TestPreviewResponse(status="success")
        assert resp.status == "success"
        assert resp.sample_data == []
        assert resp.violations == []
        assert resp.warnings == []

    def test_response_error(self):
        resp = TestPreviewResponse(status="error", error_message="oops")
        assert resp.error_message == "oops"

    def test_statistics_defaults(self):
        st = TestStatistics()
        assert st.total_rows == 0
        assert st.pass_rate == 0.0

    def test_statistics_values(self):
        st = TestStatistics(total_rows=100, rows_passed=95, rows_failed=5, pass_rate=95.0)
        assert st.pass_rate == 95.0


# ══════════════════════════════════════
# 2. Expression Builder
# ══════════════════════════════════════


class TestExpression:
    def test_null_check_with_canonical(self):
        c = cfg(
            canonical_rule={"condition": "email IS NULL", "expectation": "100%"},
        )
        expr = svc._build_expression(c)
        assert "completeness.null" in expr
        assert "email IS NULL" in expr
        assert "100%" in expr

    def test_no_canonical_uses_columns(self):
        c = cfg(config={"columns": ["age", "name"]})
        expr = svc._build_expression(c)
        assert "age" in expr
        assert "name" in expr
        assert "CHECK" in expr

    def test_no_canonical_no_columns(self):
        c = cfg(config={})
        expr = svc._build_expression(c)
        assert "CHECK(*)" in expr

    def test_expression_includes_dimension(self):
        c = cfg(check_type="validity", subtype="regex")
        expr = svc._build_expression(c)
        assert "validity.regex" in expr


# ══════════════════════════════════════
# 3. Condition Builder
# ══════════════════════════════════════


class TestCondition:
    def test_null_condition(self):
        c = cfg(subtype="null", config={"columns": ["email"]})
        cond = svc._build_condition(c)
        assert cond == '"email" IS NULL'

    def test_not_null_condition(self):
        c = cfg(subtype="not_null", config={"columns": ["email"]})
        cond = svc._build_condition(c)
        assert cond == '"email" IS NOT NULL'

    def test_range_condition(self):
        c = cfg(subtype="range", config={"columns": ["age"], "operator": ">", "value": 18})
        cond = svc._build_condition(c)
        # Violations = rows NOT satisfying age > 18 → age <= 18
        assert cond == '"age" <= 18'

    def test_range_gte(self):
        c = cfg(subtype="range", config={"columns": ["score"], "operator": ">=", "value": 0})
        cond = svc._build_condition(c)
        assert cond == '"score" < 0'

    def test_allowed_values(self):
        c = cfg(
            subtype="allowed_values",
            config={"columns": ["status"], "value_list": ["active", "inactive"]},
        )
        cond = svc._build_condition(c)
        assert '"status" NOT IN' in cond
        assert "'active'" in cond
        assert "'inactive'" in cond

    def test_regex_condition(self):
        c = cfg(subtype="regex", config={"columns": ["email"], "regex_pattern": "^[a-z]+@"})
        cond = svc._build_condition(c)
        assert "!~" in cond
        assert "^[a-z]+@" in cond

    def test_length_condition(self):
        c = cfg(subtype="length", config={"columns": ["name"], "operator": "<=", "value": 100})
        cond = svc._build_condition(c)
        assert 'LENGTH("name")' in cond
        assert "> 100" in cond

    def test_date_comparison_with_column(self):
        c = cfg(
            subtype="date_comparison",
            config={"columns": ["ship_date"], "operator": ">", "compare_column": "order_date"},
        )
        cond = svc._build_condition(c)
        assert '"ship_date" <=' in cond
        assert '"order_date"' in cond

    def test_date_comparison_with_value(self):
        c = cfg(
            subtype="date_comparison",
            config={"columns": ["created_at"], "operator": ">", "value": "2024-01-01"},
        )
        cond = svc._build_condition(c)
        assert '"created_at" <=' in cond
        assert "'2024-01-01'" in cond

    def test_column_comparison(self):
        c = cfg(
            subtype="column_comparison",
            config={"columns": ["col_a"], "compare_column": "col_b", "operator": "="},
        )
        cond = svc._build_condition(c)
        assert '"col_a" !=' in cond
        assert '"col_b"' in cond

    def test_unknown_subtype_returns_none(self):
        c = cfg(subtype="exotic_check", config={"columns": ["x"]})
        cond = svc._build_condition(c)
        assert cond is None

    def test_no_columns_returns_none(self):
        c = cfg(subtype="null", config={})
        cond = svc._build_condition(c)
        assert cond is None


# ══════════════════════════════════════
# 4. Warning Detection
# ══════════════════════════════════════


class TestWarnings:
    def _fields(self, *specs):
        return [{"field_name": s[0], "data_type": s[1], "nullable": s[2]} for s in specs]

    def test_null_on_not_null_column(self):
        c = cfg(subtype="null", config={"columns": ["email"]})
        fields = self._fields(("email", "varchar", False))
        warns = svc._detect_warnings(c, fields)
        assert any("NOT NULL" in w for w in warns)

    def test_null_on_nullable_column_no_warning(self):
        c = cfg(subtype="null", config={"columns": ["email"]})
        fields = self._fields(("email", "varchar", True))
        warns = svc._detect_warnings(c, fields)
        assert len(warns) == 0

    def test_range_on_non_numeric(self):
        c = cfg(subtype="range", config={"columns": ["name"]})
        fields = self._fields(("name", "varchar", True))
        warns = svc._detect_warnings(c, fields)
        assert any("non-numeric" in w for w in warns)

    def test_range_on_numeric_no_warning(self):
        c = cfg(subtype="range", config={"columns": ["age"]})
        fields = self._fields(("age", "integer", True))
        warns = svc._detect_warnings(c, fields)
        assert len(warns) == 0

    def test_date_on_non_date(self):
        c = cfg(subtype="date_comparison", config={"columns": ["name"]})
        fields = self._fields(("name", "varchar", True))
        warns = svc._detect_warnings(c, fields)
        assert any("non-date" in w.lower() for w in warns)

    def test_date_on_date_no_warning(self):
        c = cfg(subtype="date_comparison", config={"columns": ["created_at"]})
        fields = self._fields(("created_at", "timestamp", True))
        warns = svc._detect_warnings(c, fields)
        assert len(warns) == 0

    def test_length_on_numeric(self):
        c = cfg(subtype="length", config={"columns": ["age"]})
        fields = self._fields(("age", "integer", True))
        warns = svc._detect_warnings(c, fields)
        assert any("numeric" in w.lower() for w in warns)

    def test_column_not_found(self):
        c = cfg(subtype="null", config={"columns": ["nonexistent"]})
        fields = self._fields(("email", "varchar", True))
        warns = svc._detect_warnings(c, fields)
        assert any("not found" in w for w in warns)

    def test_empty_fields_no_crash(self):
        c = cfg(subtype="null", config={"columns": ["email"]})
        warns = svc._detect_warnings(c, [])
        assert any("not found" in w for w in warns)


# ══════════════════════════════════════
# 5. Invert Operator
# ══════════════════════════════════════


class TestInvertOp:
    def test_gt(self):
        assert svc._invert_op(">") == "<="

    def test_gte(self):
        assert svc._invert_op(">=") == "<"

    def test_lt(self):
        assert svc._invert_op("<") == ">="

    def test_lte(self):
        assert svc._invert_op("<=") == ">"

    def test_eq(self):
        assert svc._invert_op("=") == "!="

    def test_neq(self):
        assert svc._invert_op("!=") == "="

    def test_unknown_passthrough(self):
        assert svc._invert_op("LIKE") == "LIKE"


# ══════════════════════════════════════
# 6. FQN Helper
# ══════════════════════════════════════


class TestFQN:
    def test_with_schema(self):
        assert svc._fqn("public", "users") == '"public"."users"'

    def test_without_schema(self):
        assert svc._fqn(None, "users") == '"users"'


# ══════════════════════════════════════
# 7. Preview — Missing Dataset ID
# ══════════════════════════════════════


class TestPreviewErrors:
    def test_missing_dataset_id(self):
        req = TestPreviewRequest(compiled_config=cfg(dataset_id=None))
        resp = svc.preview(None, uuid4(), req)
        assert resp.status == "error"
        assert "dataset_id" in resp.error_message


# ══════════════════════════════════════
# 8. Endpoint Tests
# ══════════════════════════════════════


class TestEndpoints:
    def test_test_preview_endpoint_import(self):
        from app.api.v1.endpoints.rule_builder import test_preview

        assert callable(test_preview)

    def test_test_preview_service_instance(self):
        from app.api.v1.endpoints.rule_builder import _test_preview

        assert isinstance(_test_preview, NLRuleTestPreview)
