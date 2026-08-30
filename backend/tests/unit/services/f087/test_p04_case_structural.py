"""P04 — F087 Case & Structural conformity type tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, params):
    return compiler._compile_conformity_rule('"public"."customers"', "name", "", "100%", params)


# ===================================================================
# A) Case type
# ===================================================================
class TestCaseConformity:
    def test_upper(self, compiler):
        result = _compile(compiler, {"conformity_type": "case", "case_rule": "upper"})
        sql = result["compiled_postgres"]
        assert "UPPER" in sql
        assert "error" not in result

    def test_lower(self, compiler):
        result = _compile(compiler, {"conformity_type": "case", "case_rule": "lower"})
        assert "LOWER" in result["compiled_postgres"]

    def test_title(self, compiler):
        result = _compile(compiler, {"conformity_type": "case", "case_rule": "title"})
        assert "INITCAP" in result["compiled_postgres"]

    def test_missing_case_rule_error(self, compiler):
        result = _compile(compiler, {"conformity_type": "case"})
        assert "error" in result

    def test_unknown_case_rule_error(self, compiler):
        result = _compile(compiler, {"conformity_type": "case", "case_rule": "camel"})
        assert "error" in result

    def test_null_skip(self, compiler):
        result = _compile(
            compiler, {"conformity_type": "case", "case_rule": "upper", "null_handling": "skip"}
        )
        assert "IS NOT NULL" in result["compiled_postgres"]

    def test_null_pass(self, compiler):
        result = _compile(
            compiler, {"conformity_type": "case", "case_rule": "upper", "null_handling": "pass"}
        )
        assert "IS NULL OR" in result["compiled_postgres"]

    def test_trim_applied(self, compiler):
        result = _compile(compiler, {"conformity_type": "case", "case_rule": "lower"})
        assert "TRIM" in result["compiled_postgres"]

    def test_filter_expression(self, compiler):
        result = _compile(
            compiler,
            {"conformity_type": "case", "case_rule": "upper", "filter_expression": "dept = 'IT'"},
        )
        assert "dept" in result["compiled_postgres"]

    def test_violation_sql(self, compiler):
        result = _compile(compiler, {"conformity_type": "case", "case_rule": "upper"})
        assert "violation_sql" in result
        assert "UPPER" in result["violation_sql"]

    def test_spark_code(self, compiler):
        result = _compile(compiler, {"conformity_type": "case", "case_rule": "upper"})
        assert "compiled_spark" in result
        assert "upper" in result["compiled_spark"].lower()

    def test_spark_lower(self, compiler):
        result = _compile(compiler, {"conformity_type": "case", "case_rule": "lower"})
        assert "F.lower" in result["compiled_spark"]

    def test_spark_title(self, compiler):
        result = _compile(compiler, {"conformity_type": "case", "case_rule": "title"})
        assert "initcap" in result["compiled_spark"].lower()


# ===================================================================
# B) Structural type
# ===================================================================
class TestStructuralConformity:
    def test_json_uses_cast(self, compiler):
        result = _compile(compiler, {"conformity_type": "structural", "structural_format": "json"})
        sql = result["compiled_postgres"]
        assert "json" in sql.lower()
        assert "error" not in result

    def test_xml_uses_xmlparse(self, compiler):
        result = _compile(compiler, {"conformity_type": "structural", "structural_format": "xml"})
        sql = result["compiled_postgres"]
        assert "XMLPARSE" in sql

    def test_missing_format_error(self, compiler):
        result = _compile(compiler, {"conformity_type": "structural"})
        assert "error" in result

    def test_unknown_format_error(self, compiler):
        result = _compile(compiler, {"conformity_type": "structural", "structural_format": "csv"})
        assert "error" in result
        assert "csv" in result["error"]

    def test_json_null_skip(self, compiler):
        result = _compile(
            compiler,
            {"conformity_type": "structural", "structural_format": "json", "null_handling": "skip"},
        )
        assert "IS NOT NULL" in result["compiled_postgres"]

    def test_json_null_pass(self, compiler):
        result = _compile(
            compiler,
            {"conformity_type": "structural", "structural_format": "json", "null_handling": "pass"},
        )
        assert "IS NULL OR" in result["compiled_postgres"]

    def test_json_filter(self, compiler):
        result = _compile(
            compiler,
            {
                "conformity_type": "structural",
                "structural_format": "json",
                "filter_expression": "active = true",
            },
        )
        assert "active" in result["compiled_postgres"]

    def test_json_violation_sql(self, compiler):
        result = _compile(compiler, {"conformity_type": "structural", "structural_format": "json"})
        assert "violation_sql" in result

    def test_json_spark(self, compiler):
        result = _compile(compiler, {"conformity_type": "structural", "structural_format": "json"})
        assert "compiled_spark" in result
        assert "from_json" in result["compiled_spark"]

    def test_xml_spark(self, compiler):
        result = _compile(compiler, {"conformity_type": "structural", "structural_format": "xml"})
        assert "compiled_spark" in result
