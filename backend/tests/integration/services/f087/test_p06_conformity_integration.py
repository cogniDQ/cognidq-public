"""P06 — F087 Conformity Integration Tests.

End-to-end pipeline: UI config → _build_canonical_rule → compile_rule → _parse_conformity_results.
Tests verify the full pipeline for all 6 conformity types, backward compatibility,
error paths, WARN threshold, null handling, trim, Spark output, and result structure.
"""

import sys
import types
from unittest.mock import MagicMock

# Stub pyspark
for mod_name in [
    "pyspark",
    "pyspark.sql",
    "pyspark.sql.functions",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

_ssm = types.ModuleType("app.services.execution.spark_session_manager")
_ssm.SparkSessionManager = MagicMock
sys.modules.setdefault("app.services.execution.spark_session_manager", _ssm)

_se = types.ModuleType("app.services.execution.spark_executor")
_se.SparkCheckExecutor = MagicMock
sys.modules.setdefault("app.services.execution.spark_executor", _se)

from decimal import Decimal

import pytest
from app.services.flows.node_handlers.check_node import CheckNodeHandler
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


@pytest.fixture
def handler():
    return CheckNodeHandler.__new__(CheckNodeHandler)


def pipeline(handler, compiler, ui_config, schema="public", table="customers"):
    canonical = handler._build_canonical_rule("conformity", ui_config, schema, table)
    compiled = compiler.compile_rule(canonical, target_schema=schema, target_table=table)
    return canonical, compiled


def full_pipeline(handler, compiler, ui_config, mock_row, schema="public", table="customers"):
    canonical, compiled = pipeline(handler, compiler, ui_config, schema, table)
    result = handler._parse_conformity_results([mock_row], canonical)
    return result


# ===================================================================
# 1. End-to-end per conformity type
# ===================================================================
class TestEndToEndRegex:
    def test_regex_pipeline(self, handler, compiler):
        config = {
            "columns": ["email"],
            "regexPattern": "^[a-z]+@[a-z]+\\.[a-z]+$",
            "pass_threshold": 95,
        }
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["conformity_type"] == "regex"
        assert "~" in compiled["compiled_postgres"]
        assert "error" not in compiled

    def test_regex_full_pipeline(self, handler, compiler):
        config = {"columns": ["email"], "regexPattern": "^[a-z]+$", "pass_threshold": 100}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "conforming_rows": 100, "non_conforming_rows": 0},
        )
        assert result["check_status"] == "PASS"
        assert result["conformity_type"] == "regex"


class TestEndToEndStandard:
    def test_standard_pipeline(self, handler, compiler):
        config = {"columns": ["date_col"], "standardName": "iso_8601", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["conformity_type"] == "standard"
        assert "~" in compiled["compiled_postgres"]

    def test_standard_full_pipeline(self, handler, compiler):
        config = {"columns": ["phone"], "standardName": "e164", "pass_threshold": 90}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "conforming_rows": 95, "non_conforming_rows": 5},
        )
        assert result["check_status"] == "PASS"
        assert result["conformity_type"] == "standard"


class TestEndToEndLength:
    def test_length_pipeline(self, handler, compiler):
        config = {"columns": ["sku"], "minLength": 8, "maxLength": 12, "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["conformity_type"] == "length"
        assert "CHAR_LENGTH" in compiled["compiled_postgres"]

    def test_length_full_pipeline(self, handler, compiler):
        config = {"columns": ["sku"], "minLength": 5, "pass_threshold": 95}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 50, "conforming_rows": 48, "non_conforming_rows": 2},
        )
        assert result["check_status"] == "PASS"


class TestEndToEndCharset:
    def test_charset_pipeline(self, handler, compiler):
        config = {"columns": ["code"], "allowedCharacters": "a-zA-Z0-9", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["conformity_type"] == "charset"
        assert "^[a-zA-Z0-9]*$" in compiled["compiled_postgres"]

    def test_charset_full_pipeline(self, handler, compiler):
        config = {"columns": ["code"], "allowedCharacters": "A-Z0-9", "pass_threshold": 90}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "conforming_rows": 92, "non_conforming_rows": 8},
        )
        assert result["check_status"] == "PASS"


class TestEndToEndCase:
    def test_case_pipeline(self, handler, compiler):
        config = {"columns": ["country_code"], "caseRule": "upper", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["conformity_type"] == "case"
        assert "UPPER" in compiled["compiled_postgres"]

    def test_case_full_pipeline(self, handler, compiler):
        config = {"columns": ["name"], "caseRule": "title", "pass_threshold": 90}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 50, "conforming_rows": 50, "non_conforming_rows": 0},
        )
        assert result["check_status"] == "PASS"


class TestEndToEndStructural:
    def test_structural_json_pipeline(self, handler, compiler):
        config = {"columns": ["metadata"], "structuralFormat": "json", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["conformity_type"] == "structural"
        assert "json" in compiled["compiled_postgres"].lower()

    def test_structural_full_pipeline(self, handler, compiler):
        config = {"columns": ["metadata"], "structuralFormat": "json", "pass_threshold": 95}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "conforming_rows": 98, "non_conforming_rows": 2},
        )
        assert result["check_status"] == "PASS"


# ===================================================================
# 2. Backward compatibility
# ===================================================================
class TestBackwardCompat:
    def test_old_pattern_key(self, handler, compiler):
        """Old config with 'pattern' key → infers regex."""
        config = {"columns": ["email"], "pattern": "^[a-z]+@", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["conformity_type"] == "regex"
        assert "error" not in compiled

    def test_old_config_no_type(self, handler, compiler):
        """Config with no type-specific keys → defaults to regex (may have no pattern → error)."""
        config = {"columns": ["email"], "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["conformity_type"] == "regex"


# ===================================================================
# 3. Error paths
# ===================================================================
class TestErrorPaths:
    def test_unknown_type(self, handler, compiler):
        config = {"columns": ["email"], "conformityType": "unknown_type", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert "error" in compiled

    def test_unknown_standard(self, handler, compiler):
        config = {"columns": ["email"], "standardName": "fake_std", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert "error" in compiled

    def test_missing_regex_pattern(self, handler, compiler):
        config = {"columns": ["email"], "conformityType": "regex", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert "error" in compiled

    def test_missing_length_bounds(self, handler, compiler):
        config = {"columns": ["sku"], "conformityType": "length", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert "error" in compiled

    def test_missing_charset(self, handler, compiler):
        config = {"columns": ["code"], "conformityType": "charset", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert "error" in compiled

    def test_missing_case_rule(self, handler, compiler):
        config = {"columns": ["name"], "conformityType": "case", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert "error" in compiled

    def test_missing_structural_format(self, handler, compiler):
        config = {"columns": ["data"], "conformityType": "structural", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert "error" in compiled


# ===================================================================
# 4. Spark output
# ===================================================================
class TestSparkOutput:
    @pytest.mark.parametrize(
        "config",
        [
            {"columns": ["email"], "regexPattern": "^\\d+$", "pass_threshold": 100},
            {"columns": ["date"], "standardName": "iso_8601", "pass_threshold": 100},
            {"columns": ["sku"], "minLength": 5, "pass_threshold": 100},
            {"columns": ["code"], "allowedCharacters": "a-z", "pass_threshold": 100},
            {"columns": ["name"], "caseRule": "upper", "pass_threshold": 100},
            {"columns": ["meta"], "structuralFormat": "json", "pass_threshold": 100},
        ],
    )
    def test_spark_present(self, handler, compiler, config):
        _, compiled = pipeline(handler, compiler, config)
        assert "compiled_spark" in compiled


# ===================================================================
# 5. WARN threshold
# ===================================================================
class TestWarnThreshold:
    def test_pass_above_threshold(self, handler, compiler):
        config = {
            "columns": ["email"],
            "regexPattern": "^\\d+$",
            "pass_threshold": 95,
            "thresholdWarn": 90,
        }
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "conforming_rows": 97, "non_conforming_rows": 3},
        )
        assert result["check_status"] == "PASS"

    def test_warn_between(self, handler, compiler):
        config = {
            "columns": ["email"],
            "regexPattern": "^\\d+$",
            "pass_threshold": 98,
            "thresholdWarn": 90,
        }
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "conforming_rows": 95, "non_conforming_rows": 5},
        )
        assert result["check_status"] == "WARN"

    def test_fail_below_warn(self, handler, compiler):
        config = {
            "columns": ["email"],
            "regexPattern": "^\\d+$",
            "pass_threshold": 98,
            "thresholdWarn": 90,
        }
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "conforming_rows": 85, "non_conforming_rows": 15},
        )
        assert result["check_status"] == "FAIL"


# ===================================================================
# 6. Filter expression
# ===================================================================
class TestFilterExpression:
    def test_filter_in_compiled_sql(self, handler, compiler):
        config = {
            "columns": ["email"],
            "regexPattern": "^\\d+$",
            "filterExpression": "status = 'active'",
            "pass_threshold": 100,
        }
        _, compiled = pipeline(handler, compiler, config)
        assert "status" in compiled["compiled_postgres"]


# ===================================================================
# 7. Null handling
# ===================================================================
class TestNullHandling:
    def test_skip_default(self, handler, compiler):
        config = {"columns": ["email"], "regexPattern": "^\\d+$", "pass_threshold": 100}
        _, compiled = pipeline(handler, compiler, config)
        assert "IS NOT NULL" in compiled["compiled_postgres"]

    def test_fail_mode(self, handler, compiler):
        config = {
            "columns": ["email"],
            "regexPattern": "^\\d+$",
            "nullHandling": "fail",
            "pass_threshold": 100,
        }
        _, compiled = pipeline(handler, compiler, config)
        assert "IS NOT NULL" not in compiled["compiled_postgres"]

    def test_pass_mode(self, handler, compiler):
        config = {
            "columns": ["email"],
            "regexPattern": "^\\d+$",
            "nullHandling": "pass",
            "pass_threshold": 100,
        }
        _, compiled = pipeline(handler, compiler, config)
        assert "IS NULL OR" in compiled["compiled_postgres"]


# ===================================================================
# 8. Trim whitespace
# ===================================================================
class TestTrimWhitespace:
    def test_trim_default_on(self, handler, compiler):
        config = {"columns": ["email"], "regexPattern": "^\\d+$", "pass_threshold": 100}
        _, compiled = pipeline(handler, compiler, config)
        assert "TRIM" in compiled["compiled_postgres"]

    def test_trim_disabled(self, handler, compiler):
        config = {
            "columns": ["email"],
            "regexPattern": "^\\d+$",
            "trimWhitespace": False,
            "pass_threshold": 100,
        }
        _, compiled = pipeline(handler, compiler, config)
        assert 'TRIM("email")' not in compiled["compiled_postgres"]


# ===================================================================
# 9. Result structure
# ===================================================================
class TestResultStructure:
    def test_all_required_fields(self, handler, compiler):
        config = {"columns": ["email"], "regexPattern": "^\\d+$", "pass_threshold": 100}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 50, "conforming_rows": 48, "non_conforming_rows": 2},
        )
        required = [
            "check_status",
            "pass_rate",
            "conformity_rate",
            "rows_scanned",
            "rows_passed",
            "rows_failed",
            "conformity_type",
            "zero_rows",
        ]
        for field in required:
            assert field in result, f"Missing field: {field}"

    def test_pass_rate_is_decimal(self, handler, compiler):
        config = {"columns": ["email"], "regexPattern": "^\\d+$", "pass_threshold": 100}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "conforming_rows": 100, "non_conforming_rows": 0},
        )
        assert isinstance(result["pass_rate"], Decimal)
