"""P01 — F087 Conformity compiler infrastructure tests."""

import re

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


# ===================================================================
# A) Named Standards Library
# ===================================================================
class TestConformityStandards:
    EXPECTED_STANDARDS = [
        "iso_8601",
        "e164",
        "iso_4217",
        "iso_3166",
        "email_rfc5322",
        "iban",
        "url",
        "uuid",
    ]

    def test_all_standards_present(self):
        for name in self.EXPECTED_STANDARDS:
            assert name in RuleCompiler.CONFORMITY_STANDARDS, f"Missing standard: {name}"

    def test_standards_count(self):
        assert len(RuleCompiler.CONFORMITY_STANDARDS) == 15

    @pytest.mark.parametrize("name", EXPECTED_STANDARDS)
    def test_each_standard_is_valid_regex(self, name):
        pattern = RuleCompiler.CONFORMITY_STANDARDS[name]
        re.compile(pattern)  # Should not raise

    def test_iso_8601_matches_date(self):
        assert re.match(RuleCompiler.CONFORMITY_STANDARDS["iso_8601"], "2026-04-02")

    def test_e164_matches_phone(self):
        assert re.match(RuleCompiler.CONFORMITY_STANDARDS["e164"], "+15551234567")

    def test_email_matches(self):
        assert re.match(RuleCompiler.CONFORMITY_STANDARDS["email_rfc5322"], "test@example.com")

    def test_uuid_matches(self):
        assert re.match(
            RuleCompiler.CONFORMITY_STANDARDS["uuid"], "550e8400-e29b-41d4-a716-446655440000"
        )


# ===================================================================
# B) Valid Conformity Types
# ===================================================================
class TestValidConformityTypes:
    def test_has_six_types(self):
        assert len(RuleCompiler.VALID_CONFORMITY_TYPES) == 6

    def test_expected_types(self):
        expected = {"regex", "standard", "length", "charset", "case", "structural"}
        assert RuleCompiler.VALID_CONFORMITY_TYPES == expected


# ===================================================================
# C) Dispatcher routing
# ===================================================================
class TestConformityDispatcher:
    def _compile(self, compiler, params):
        return compiler._compile_conformity_rule('"public"."customers"', "name", "", "100%", params)

    def test_routes_regex(self, compiler):
        result = self._compile(compiler, {"conformity_type": "regex", "regex_pattern": "^[A-Z]+$"})
        assert "error" not in result
        assert "~" in result["compiled_postgres"]

    def test_routes_standard(self, compiler):
        result = self._compile(
            compiler, {"conformity_type": "standard", "standard_name": "iso_8601"}
        )
        assert "error" not in result

    def test_routes_length(self, compiler):
        result = self._compile(
            compiler, {"conformity_type": "length", "min_length": 5, "max_length": 10}
        )
        assert "error" not in result
        assert "CHAR_LENGTH" in result["compiled_postgres"]

    def test_routes_charset(self, compiler):
        result = self._compile(
            compiler, {"conformity_type": "charset", "allowed_characters": "a-zA-Z0-9"}
        )
        assert "error" not in result

    def test_routes_case(self, compiler):
        result = self._compile(compiler, {"conformity_type": "case", "case_rule": "upper"})
        assert "error" not in result
        assert "UPPER" in result["compiled_postgres"]

    def test_routes_structural(self, compiler):
        result = self._compile(
            compiler, {"conformity_type": "structural", "structural_format": "json"}
        )
        assert "error" not in result
        assert "json" in result["compiled_postgres"].lower()

    def test_unknown_type_error(self, compiler):
        result = self._compile(compiler, {"conformity_type": "unknown_xyz"})
        assert "error" in result
        assert "unknown_xyz" in result["error"].lower() or "Unknown" in result["error"]


# ===================================================================
# D) Type inference
# ===================================================================
class TestConformityTypeInference:
    def test_infer_regex(self):
        assert RuleCompiler._infer_conformity_type({"regex_pattern": "^\\d+$"}) == "regex"

    def test_infer_standard(self):
        assert RuleCompiler._infer_conformity_type({"standard_name": "e164"}) == "standard"

    def test_infer_length_from_min(self):
        assert RuleCompiler._infer_conformity_type({"min_length": 5}) == "length"

    def test_infer_length_from_max(self):
        assert RuleCompiler._infer_conformity_type({"max_length": 10}) == "length"

    def test_infer_charset(self):
        assert RuleCompiler._infer_conformity_type({"allowed_characters": "a-z"}) == "charset"

    def test_infer_case(self):
        assert RuleCompiler._infer_conformity_type({"case_rule": "upper"}) == "case"

    def test_infer_structural(self):
        assert RuleCompiler._infer_conformity_type({"structural_format": "json"}) == "structural"

    def test_infer_default_regex(self):
        assert RuleCompiler._infer_conformity_type({}) == "regex"


# ===================================================================
# E) Null handling SQL helper
# ===================================================================
class TestConformityNullHandling:
    def test_skip_returns_where_clause(self):
        where, mode = RuleCompiler._conformity_null_handling_sql('"col"', "skip")
        assert "IS NOT NULL" in where
        assert mode == ""

    def test_fail_returns_no_where(self):
        where, mode = RuleCompiler._conformity_null_handling_sql('"col"', "fail")
        assert where == ""
        assert mode == ""

    def test_pass_returns_pass_mode(self):
        where, mode = RuleCompiler._conformity_null_handling_sql('"col"', "pass")
        assert where == ""
        assert mode == "pass"


# ===================================================================
# F) Trim SQL helper
# ===================================================================
class TestConformityTrimSql:
    def test_trim_enabled(self):
        result = RuleCompiler._conformity_trim_sql('"col"', True)
        assert "TRIM" in result
        assert '"col"' in result

    def test_trim_disabled(self):
        result = RuleCompiler._conformity_trim_sql('"col"', False)
        assert result == '"col"'
        assert "TRIM" not in result


# ===================================================================
# G) Error result helper
# ===================================================================
class TestConformityErrorResult:
    def test_error_structure(self):
        result = RuleCompiler._conformity_error_result("test error")
        assert result["error"] == "test error"
        assert "ERROR" in result["compiled_sql"]
        assert "ERROR" in result["compiled_postgres"]
        assert "ERROR" in result["compiled_spark"]


# ===================================================================
# H) Filter expression
# ===================================================================
class TestConformityFilterExpression:
    def _compile(self, compiler, params):
        return compiler._compile_conformity_rule('"public"."customers"', "name", "", "100%", params)

    def test_filter_expression_in_sql(self, compiler):
        result = self._compile(
            compiler,
            {
                "conformity_type": "regex",
                "regex_pattern": "^[A-Z]+$",
                "filter_expression": "status = 'active'",
            },
        )
        assert "status" in result["compiled_postgres"]

    def test_filter_injection_blocked(self, compiler):
        result = self._compile(
            compiler,
            {
                "conformity_type": "regex",
                "regex_pattern": "^[A-Z]+$",
                "filter_expression": "1=1; DROP TABLE users",
            },
        )
        assert "error" in result
