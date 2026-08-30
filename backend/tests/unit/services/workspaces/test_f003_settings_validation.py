"""
Unit tests — F003 Packet 3: Settings Validation Layer

Verifies all validation functions in settings_validation.py.
No database or I/O dependencies.

Run:
    docker exec dq-backend-1 python -m pytest tests/unit/services/workspaces/test_f003_settings_validation.py -v
"""

import pytest
from app.services.workspaces.settings_validation import (
    ALLOWED_GROUPING_MODES,
    FieldError,
    ValidationResult,
    detect_unknown_fields,
    is_empty_request,
    validate_issue_grouping_policy,
    validate_naming_standards,
    validate_settings_update_payload,
    validate_severity_policy,
    validate_sla_policy,
    validate_timezone_policy,
)

# ─────────────────────────────────────────────────────────────────────────────
# detect_unknown_fields
# ─────────────────────────────────────────────────────────────────────────────


class TestDetectUnknownFields:
    def test_unknown_key_detected(self):
        result = detect_unknown_fields({"unknown_key": 1})
        assert "unknown_key" in result

    def test_recognised_keys_not_flagged(self):
        body = {"timezone_policy": {}, "severity_policy": {}, "sla_policy": {}}
        assert detect_unknown_fields(body) == []

    def test_empty_body_returns_empty_list(self):
        assert detect_unknown_fields({}) == []

    def test_mixed_known_unknown(self):
        result = detect_unknown_fields({"issue_grouping_policy": "x", "bad_key": 1})
        assert result == ["bad_key"]

    def test_all_recognised_fields_accepted(self):
        body = {
            "timezone_policy": {},
            "severity_policy": {},
            "sla_policy": {},
            "issue_grouping_policy": "x",
            "naming_standards": {},
        }
        assert detect_unknown_fields(body) == []


# ─────────────────────────────────────────────────────────────────────────────
# is_empty_request
# ─────────────────────────────────────────────────────────────────────────────


class TestIsEmptyRequest:
    def test_empty_dict_is_empty(self):
        assert is_empty_request({}) is True

    def test_recognised_key_is_not_empty(self):
        assert is_empty_request({"issue_grouping_policy": "one_per_rule"}) is False

    def test_only_unknown_key_counts_as_empty(self):
        # Body has only unrecognised key — treated as empty (unknown keys checked separately)
        assert is_empty_request({"bad_key": 1}) is True

    def test_all_recognised_policies_not_empty(self):
        assert is_empty_request({"severity_policy": {}}) is False


# ─────────────────────────────────────────────────────────────────────────────
# validate_timezone_policy  (AC-P03-03 ~ AC-P03-05)
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateTimezonePolicy:
    def test_valid_utc_returns_no_errors(self):
        errors = validate_timezone_policy({"default_timezone": "UTC"})
        assert errors == []

    def test_valid_named_zone_returns_no_errors(self):
        errors = validate_timezone_policy({"default_timezone": "America/New_York"})
        assert errors == []

    def test_empty_string_returns_required_field_error(self):
        errors = validate_timezone_policy({"default_timezone": ""})
        assert len(errors) == 1
        assert errors[0].error_code == "required_field"
        assert errors[0].field == "timezone_policy.default_timezone"

    def test_whitespace_only_returns_required_field_error(self):
        errors = validate_timezone_policy({"default_timezone": "   "})
        assert len(errors) == 1
        assert errors[0].error_code == "required_field"

    def test_none_value_returns_required_field_error(self):
        errors = validate_timezone_policy({"default_timezone": None})
        assert len(errors) == 1
        assert errors[0].error_code == "required_field"

    def test_invalid_timezone_returns_invalid_timezone_error(self):
        errors = validate_timezone_policy({"default_timezone": "Not/Valid/Zone"})
        assert len(errors) == 1
        assert errors[0].error_code == "invalid_timezone"

    def test_bogus_string_returns_invalid_timezone_error(self):
        errors = validate_timezone_policy({"default_timezone": "Atlantis"})
        assert len(errors) == 1
        assert errors[0].error_code == "invalid_timezone"

    def test_non_string_returns_invalid_field_type(self):
        errors = validate_timezone_policy({"default_timezone": 42})
        assert len(errors) == 1
        assert errors[0].error_code == "invalid_field_type"

    def test_missing_key_returns_required_field_error(self):
        errors = validate_timezone_policy({})
        assert len(errors) == 1
        assert errors[0].error_code == "required_field"


# ─────────────────────────────────────────────────────────────────────────────
# validate_severity_policy  (AC-P03-06, AC-P03-07)
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateSeverityPolicy:
    def _valid_severity(self):
        return {
            "critical_label": "Critical",
            "major_label": "Major",
            "minor_label": "Minor",
            "informational_label": "Informational",
        }

    def test_valid_policy_returns_no_errors(self):
        assert validate_severity_policy(self._valid_severity()) == []

    def test_missing_three_labels_returns_incomplete_error(self):
        errors = validate_severity_policy({"critical_label": "Crit"})
        assert any(e.error_code == "incomplete_severity_policy" for e in errors)

    def test_missing_all_labels_returns_incomplete_error(self):
        errors = validate_severity_policy({})
        assert any(e.error_code == "incomplete_severity_policy" for e in errors)

    def test_label_51_chars_returns_invalid_label(self):
        body = self._valid_severity()
        body["critical_label"] = "X" * 51
        errors = validate_severity_policy(body)
        assert any(e.error_code == "invalid_label" and "critical_label" in e.field for e in errors)

    def test_label_50_chars_is_valid(self):
        body = self._valid_severity()
        body["critical_label"] = "X" * 50
        assert validate_severity_policy(body) == []

    def test_empty_label_returns_invalid_label(self):
        body = self._valid_severity()
        body["critical_label"] = ""
        errors = validate_severity_policy(body)
        assert any(e.error_code == "invalid_label" for e in errors)

    def test_whitespace_only_label_returns_invalid_label(self):
        body = self._valid_severity()
        body["major_label"] = "   "
        errors = validate_severity_policy(body)
        assert any(e.error_code == "invalid_label" for e in errors)

    def test_label_with_newline_returns_invalid_label(self):
        body = self._valid_severity()
        body["minor_label"] = "Minor\nIssue"
        errors = validate_severity_policy(body)
        assert any(e.error_code == "invalid_label" for e in errors)

    def test_non_string_label_returns_invalid_field_type(self):
        body = self._valid_severity()
        body["critical_label"] = 123
        errors = validate_severity_policy(body)
        assert any(e.error_code == "invalid_field_type" for e in errors)

    def test_non_dict_returns_invalid_field_type(self):
        errors = validate_severity_policy("not a dict")
        assert any(e.error_code == "invalid_field_type" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# validate_sla_policy  (AC-P03-08 ~ AC-P03-10)
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateSlaPolicy:
    def _valid_sla(self, informational_hours=None):
        return {
            "critical_hours": 4,
            "major_hours": 24,
            "minor_hours": 72,
            "informational_hours": informational_hours,
        }

    def test_valid_policy_no_informational_returns_no_errors(self):
        assert validate_sla_policy(self._valid_sla()) == []

    def test_valid_policy_with_informational_returns_no_errors(self):
        body = self._valid_sla()
        body["informational_hours"] = 168
        assert validate_sla_policy(body) == []

    def test_informational_hours_none_is_valid(self):
        """AC-P03-10: informational_hours=None is explicitly allowed."""
        errors = validate_sla_policy(
            {"critical_hours": 4, "major_hours": 24, "minor_hours": 72, "informational_hours": None}
        )
        assert errors == []

    def test_critical_greater_than_major_is_ordering_violation(self):
        """AC-P03-08."""
        body = {"critical_hours": 8, "major_hours": 4, "minor_hours": 72}
        errors = validate_sla_policy(body)
        assert any(e.error_code == "sla_ordering_violation" for e in errors)

    def test_major_greater_than_minor_is_ordering_violation(self):
        body = {"critical_hours": 4, "major_hours": 72, "minor_hours": 24}
        errors = validate_sla_policy(body)
        assert any(e.error_code == "sla_ordering_violation" for e in errors)

    def test_equal_values_are_valid(self):
        # critical == major == minor is allowed (tight SLA)
        body = {"critical_hours": 4, "major_hours": 4, "minor_hours": 4}
        assert validate_sla_policy(body) == []

    def test_zero_hours_returns_invalid_sla_hours(self):
        """AC-P03-09."""
        body = {"critical_hours": 0, "major_hours": 24, "minor_hours": 72}
        errors = validate_sla_policy(body)
        assert any(e.error_code == "invalid_sla_hours" for e in errors)

    def test_hours_above_max_returns_invalid_sla_hours(self):
        body = {"critical_hours": 4, "major_hours": 24, "minor_hours": 8761}
        errors = validate_sla_policy(body)
        assert any(e.error_code == "invalid_sla_hours" for e in errors)

    def test_hours_at_max_boundary_valid(self):
        body = {"critical_hours": 4, "major_hours": 24, "minor_hours": 8760}
        assert validate_sla_policy(body) == []

    def test_non_integer_hours_returns_invalid_sla_hours(self):
        body = {"critical_hours": "four", "major_hours": 24, "minor_hours": 72}
        errors = validate_sla_policy(body)
        assert any(e.error_code == "invalid_sla_hours" for e in errors)

    def test_boolean_hours_rejected_as_not_integer(self):
        # bool is a subclass of int in Python; must explicitly reject
        body = {"critical_hours": True, "major_hours": 24, "minor_hours": 72}
        errors = validate_sla_policy(body)
        assert any(e.error_code == "invalid_sla_hours" for e in errors)

    def test_missing_required_key_returns_incomplete_error(self):
        body = {"critical_hours": 4, "major_hours": 24}  # missing minor_hours
        errors = validate_sla_policy(body)
        assert any(e.error_code == "incomplete_sla_policy" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# validate_issue_grouping_policy  (AC-P03-11)
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateIssueGroupingPolicy:
    def test_valid_modes_return_no_errors(self):
        for mode in ALLOWED_GROUPING_MODES:
            assert validate_issue_grouping_policy(mode) == []

    def test_invalid_mode_returns_invalid_grouping_mode(self):
        """AC-P03-11."""
        errors = validate_issue_grouping_policy("one_per_quarter")
        assert len(errors) == 1
        assert errors[0].error_code == "invalid_grouping_mode"

    def test_empty_string_returns_invalid_grouping_mode(self):
        errors = validate_issue_grouping_policy("")
        assert any(e.error_code == "invalid_grouping_mode" for e in errors)

    def test_non_string_returns_invalid_field_type(self):
        errors = validate_issue_grouping_policy(42)
        assert any(e.error_code == "invalid_field_type" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# validate_naming_standards  (AC-P03-12 ~ AC-P03-14)
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateNamingStandards:
    def test_empty_dict_is_valid(self):
        assert validate_naming_standards({}) == []

    def test_empty_datasets_is_valid(self):
        assert validate_naming_standards({"datasets": {}}) == []

    def test_valid_full_constraint_returns_no_errors(self):
        ns = {
            "datasets": {
                "required_prefix": "raw_",
                "required_suffix": "_v1",
                "pattern": r"^[a-z_]+$",
                "max_length": 200,
                "allow_special_characters": False,
            },
            "rules": {},
        }
        assert validate_naming_standards(ns) == []

    def test_invalid_regex_returns_invalid_pattern(self):
        """AC-P03-12."""
        errors = validate_naming_standards({"datasets": {"pattern": "[invalid"}})
        assert any(e.error_code == "invalid_pattern" for e in errors)

    def test_valid_regex_returns_no_errors(self):
        errors = validate_naming_standards({"datasets": {"pattern": r"^[a-z]+$"}})
        assert errors == []

    def test_empty_prefix_returns_invalid_prefix(self):
        """AC-P03-13."""
        errors = validate_naming_standards({"datasets": {"required_prefix": ""}})
        assert any(e.error_code == "invalid_prefix" for e in errors)

    def test_whitespace_only_prefix_returns_invalid_prefix(self):
        errors = validate_naming_standards({"datasets": {"required_prefix": "   "}})
        assert any(e.error_code == "invalid_prefix" for e in errors)

    def test_prefix_over_50_chars_returns_invalid_prefix(self):
        errors = validate_naming_standards({"datasets": {"required_prefix": "p" * 51}})
        assert any(e.error_code == "invalid_prefix" for e in errors)

    def test_empty_suffix_returns_invalid_suffix(self):
        errors = validate_naming_standards({"datasets": {"required_suffix": ""}})
        assert any(e.error_code == "invalid_suffix" for e in errors)

    def test_max_length_zero_returns_invalid_max_length(self):
        """AC-P03-14."""
        errors = validate_naming_standards({"datasets": {"max_length": 0}})
        assert any(e.error_code == "invalid_max_length" for e in errors)

    def test_max_length_501_returns_invalid_max_length(self):
        errors = validate_naming_standards({"datasets": {"max_length": 501}})
        assert any(e.error_code == "invalid_max_length" for e in errors)

    def test_max_length_500_is_valid(self):
        assert validate_naming_standards({"datasets": {"max_length": 500}}) == []

    def test_max_length_1_is_valid(self):
        assert validate_naming_standards({"datasets": {"max_length": 1}}) == []

    def test_non_boolean_allow_special_characters_returns_invalid_field_type(self):
        errors = validate_naming_standards({"datasets": {"allow_special_characters": "yes"}})
        assert any(e.error_code == "invalid_field_type" for e in errors)

    def test_boolean_allow_special_characters_is_valid(self):
        assert validate_naming_standards({"datasets": {"allow_special_characters": True}}) == []

    def test_max_length_boolean_rejected(self):
        errors = validate_naming_standards({"datasets": {"max_length": True}})
        assert any(e.error_code == "invalid_field_type" for e in errors)

    def test_errors_in_rules_domain_reported(self):
        errors = validate_naming_standards({"rules": {"pattern": "[bad"}})
        assert any("rules" in e.field for e in errors)

    def test_non_dict_returns_invalid_field_type(self):
        errors = validate_naming_standards("not a dict")
        assert any(e.error_code == "invalid_field_type" for e in errors)

    def test_prefix_at_max_50_chars_is_valid(self):
        errors = validate_naming_standards({"datasets": {"required_prefix": "p" * 50}})
        assert errors == []


# ─────────────────────────────────────────────────────────────────────────────
# validate_settings_update_payload  (AC-P03-15)
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateSettingsUpdatePayload:
    def test_empty_body_returns_valid(self):
        result = validate_settings_update_payload({})
        assert result.is_valid is True
        assert result.errors == []

    def test_valid_full_body_returns_valid(self):
        body = {
            "timezone_policy": {"default_timezone": "UTC"},
            "severity_policy": {
                "critical_label": "P1",
                "major_label": "P2",
                "minor_label": "P3",
                "informational_label": "P4",
            },
            "sla_policy": {"critical_hours": 4, "major_hours": 24, "minor_hours": 72},
            "issue_grouping_policy": "one_per_execution",
            "naming_standards": {"datasets": {}},
        }
        result = validate_settings_update_payload(body)
        assert result.is_valid is True

    def test_collects_all_errors_not_fail_fast(self):
        """AC-P03-15: ALL errors from multiple domains returned in one result."""
        body = {
            "severity_policy": {"critical_label": "X"},  # missing 3 labels
            "sla_policy": {"critical_hours": 4, "major_hours": 24},  # missing minor
        }
        result = validate_settings_update_payload(body)
        assert result.is_valid is False
        assert len(result.errors) >= 2

    def test_returns_validation_result_instance(self):
        result = validate_settings_update_payload({})
        assert isinstance(result, ValidationResult)

    def test_one_invalid_domain_makes_result_invalid(self):
        body = {"issue_grouping_policy": "bad_mode"}
        result = validate_settings_update_payload(body)
        assert result.is_valid is False
        assert any(e.error_code == "invalid_grouping_mode" for e in result.errors)

    def test_errors_have_field_and_error_code(self):
        body = {"issue_grouping_policy": "bad_mode"}
        result = validate_settings_update_payload(body)
        error = result.errors[0]
        assert isinstance(error, FieldError)
        assert error.field
        assert error.error_code
        assert error.message

    def test_only_present_fields_are_validated(self):
        # Only timezone_policy present; other domains not validated
        body = {"timezone_policy": {"default_timezone": "UTC"}}
        result = validate_settings_update_payload(body)
        assert result.is_valid is True

    def test_all_four_invalid_domains_all_reported(self):
        body = {
            "timezone_policy": {"default_timezone": ""},
            "severity_policy": {},
            "sla_policy": {},
            "issue_grouping_policy": "bad",
        }
        result = validate_settings_update_payload(body)
        assert result.is_valid is False
        # At minimum one error per domain
        codes = {e.error_code for e in result.errors}
        assert "required_field" in codes
        assert "incomplete_severity_policy" in codes
        assert "incomplete_sla_policy" in codes
        assert "invalid_grouping_mode" in codes
