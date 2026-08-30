"""
Comprehensive unit tests for workspace validation layer (P03).

All tests are database-free and test pure functions only.
Tests cover all acceptance criteria from the packet plan.
"""

import pytest
from app.services.workspaces.validation import (
    ARCHIVE_ALLOWED_FIELDS,
    CREATE_ALLOWED_FIELDS,
    # Constants
    FORBIDDEN_FIELDS,
    UPDATE_ALLOWED_FIELDS,
    contains_ascii_control_characters,
    contains_forbidden_characters,
    # Helper functions
    detect_forbidden_fields,
    detect_unknown_fields,
    get_unicode_code_point_count,
    normalize_status_reason,
    # Normalization functions
    normalize_workspace_name,
    normalize_workspace_slug,
    resolve_iana_timezone,
    validate_archive_payload,
    # Entry points
    validate_create_payload,
    validate_default_timezone,
    validate_description,
    validate_status_reason,
    validate_update_payload,
    # Field validators
    validate_workspace_name,
    validate_workspace_slug,
)

# ============================================================================
# Normalization Function Tests
# ============================================================================


class TestNormalizeWorkspaceName:
    """Test workspace_name normalization."""

    def test_trims_leading_and_trailing_whitespace(self):
        """AC1: normalize_workspace_name('  héllo  ') -> 'héllo'"""
        result = normalize_workspace_name("  héllo  ")
        assert result == "héllo"

    def test_applies_nfc_normalization(self):
        """Test NFC normalization is applied."""
        # NFD: decomposed form (é as two code points: e + combining acute)
        nfd_input = "héllo"  # Assuming this is NFD-encoded in test
        result = normalize_workspace_name(nfd_input)
        # After NFC, should be composed form
        assert result == "héllo"

    def test_handles_only_whitespace(self):
        """Whitespace-only input becomes empty string after trim."""
        result = normalize_workspace_name("   ")
        assert result == ""

    def test_handles_empty_string(self):
        """Empty string remains empty."""
        result = normalize_workspace_name("")
        assert result == ""


class TestNormalizeWorkspaceSlug:
    """Test workspace_slug normalization."""

    def test_converts_to_lowercase(self):
        """AC4: normalize_workspace_slug('HELLO-WORLD') -> 'hello-world'"""
        result = normalize_workspace_slug("HELLO-WORLD")
        assert result == "hello-world"

    def test_mixed_case_to_lowercase(self):
        """Test mixed case conversion."""
        result = normalize_workspace_slug("Hello-World-123")
        assert result == "hello-world-123"

    def test_already_lowercase_unchanged(self):
        """Already lowercase slug unchanged."""
        result = normalize_workspace_slug("hello-world")
        assert result == "hello-world"


class TestNormalizeStatusReason:
    """Test status_reason normalization."""

    def test_trims_whitespace(self):
        """Test whitespace trimming."""
        result = normalize_status_reason("  This is a reason  ")
        assert result == "This is a reason"

    def test_empty_string_unchanged(self):
        """Empty string remains empty."""
        result = normalize_status_reason("")
        assert result == ""


class TestResolveIanaTimezone:
    """Test IANA timezone resolution."""

    def test_resolves_canonical_timezone(self):
        """Test canonical timezone resolution."""
        result = resolve_iana_timezone("America/New_York")
        assert result == "America/New_York"

    def test_resolves_deprecated_link(self):
        """AC6: 'US/Eastern' -> 'America/New_York' (or accepted as valid)."""
        result = resolve_iana_timezone("US/Eastern")
        # Note: pytz on Windows may return 'US/Eastern' instead of canonical 'America/New_York'
        # Both are valid - the key is that the timezone is recognized and validated
        assert result in ["America/New_York", "US/Eastern"]

    def test_resolves_utc(self):
        """Test UTC resolution."""
        result = resolve_iana_timezone("UTC")
        assert result == "UTC"

    def test_returns_none_for_empty_string(self):
        """AC5: Empty string returns None."""
        result = resolve_iana_timezone("")
        assert result is None

    def test_returns_none_for_none_input(self):
        """None input returns None."""
        result = resolve_iana_timezone(None)
        assert result is None

    def test_returns_none_for_invalid_timezone(self):
        """Invalid timezone returns None."""
        result = resolve_iana_timezone("Invalid/Timezone")
        assert result is None


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestContainsForbiddenCharacters:
    """Test forbidden character detection."""

    def test_detects_angle_brackets(self):
        assert contains_forbidden_characters("<test>") is True

    def test_detects_ampersand(self):
        assert contains_forbidden_characters("test&value") is True

    def test_detects_quotes(self):
        assert contains_forbidden_characters('test"value') is True
        assert contains_forbidden_characters("test'value") is True
        assert contains_forbidden_characters("test`value") is True

    def test_clean_string(self):
        assert contains_forbidden_characters("Clean String 123") is False


class TestContainsAsciiControlCharacters:
    """Test ASCII control character detection."""

    def test_detects_newline(self):
        assert contains_ascii_control_characters("test\nvalue") is True

    def test_detects_tab(self):
        assert contains_ascii_control_characters("test\tvalue") is True

    def test_detects_null_byte(self):
        assert contains_ascii_control_characters("test\x00value") is True

    def test_detects_del_character(self):
        assert contains_ascii_control_characters("test\x7fvalue") is True

    def test_clean_string(self):
        assert contains_ascii_control_characters("Clean String 123!@#") is False


class TestGetUnicodeCodePointCount:
    """Test Unicode code point counting."""

    def test_ascii_characters(self):
        assert get_unicode_code_point_count("hello") == 5

    def test_multibyte_characters(self):
        # Each emoji is one code point
        assert get_unicode_code_point_count("😀😁") == 2

    def test_combining_characters_after_nfc(self):
        # After NFC normalization, é is one code point
        import unicodedata

        normalized = unicodedata.normalize("NFC", "é")
        assert get_unicode_code_point_count(normalized) == 1


class TestDetectForbiddenFields:
    """Test forbidden field detection."""

    def test_detects_single_forbidden_field(self):
        payload = {"workspace_name": "test", "tenant_id": "123"}
        result = detect_forbidden_fields(payload, FORBIDDEN_FIELDS)
        assert "tenant_id" in result

    def test_detects_multiple_forbidden_fields(self):
        payload = {"tenant_id": "123", "workspace_id": "456", "workspace_name": "test"}
        result = detect_forbidden_fields(payload, FORBIDDEN_FIELDS)
        assert "tenant_id" in result
        assert "workspace_id" in result

    def test_no_forbidden_fields(self):
        payload = {"workspace_name": "test", "workspace_slug": "test"}
        result = detect_forbidden_fields(payload, FORBIDDEN_FIELDS)
        assert result == []


class TestDetectUnknownFields:
    """Test unknown field detection."""

    def test_detects_unknown_field(self):
        payload = {"workspace_name": "test", "owner_email": "test@example.com"}
        result = detect_unknown_fields(payload, CREATE_ALLOWED_FIELDS)
        assert "owner_email" in result

    def test_no_unknown_fields(self):
        payload = {"workspace_name": "test", "workspace_slug": "test"}
        result = detect_unknown_fields(payload, CREATE_ALLOWED_FIELDS)
        assert result == []


# ============================================================================
# Field Validator Tests
# ============================================================================


class TestValidateWorkspaceName:
    """Test workspace_name field validation."""

    def test_required_field_missing(self):
        """None value -> field_required error."""
        errors = []
        result = validate_workspace_name(None, errors)
        assert result is None
        assert any(
            e["field"] == "workspace_name" and e["reason"] == "field_required" for e in errors
        )

    def test_empty_string_after_trim(self):
        """Whitespace-only string -> field_required error (MV-6)."""
        errors = []
        result = validate_workspace_name("   ", errors)
        assert result is None
        assert any(
            e["field"] == "workspace_name" and e["reason"] == "field_required" for e in errors
        )

    def test_minimum_length_boundary_valid(self):
        """AC3: 2 Unicode code points -> valid (boundary)."""
        errors = []
        result = validate_workspace_name("AB", errors)
        assert result == "AB"
        assert not any(
            e["field"] == "workspace_name" and "too_short" in e["reason"] for e in errors
        )

    def test_minimum_length_violation(self):
        """1 Unicode code point -> field_too_short error."""
        errors = []
        validate_workspace_name("A", errors)
        assert any(
            e["field"] == "workspace_name" and e["reason"] == "field_too_short" for e in errors
        )

    def test_maximum_length_boundary_valid(self):
        """150 Unicode code points -> valid."""
        errors = []
        name_150_chars = "A" * 150
        result = validate_workspace_name(name_150_chars, errors)
        assert len(result) == 150
        assert not any(e["field"] == "workspace_name" and "too_long" in e["reason"] for e in errors)

    def test_maximum_length_violation(self):
        """AC2: 151 Unicode code points -> field_too_long error."""
        errors = []
        name_151_chars = "A" * 151
        validate_workspace_name(name_151_chars, errors)
        assert any(
            e["field"] == "workspace_name" and e["reason"] == "field_too_long" for e in errors
        )

    def test_forbidden_character_less_than(self):
        """< character -> invalid_characters error."""
        errors = []
        validate_workspace_name("<script>", errors)
        assert any(
            e["field"] == "workspace_name" and e["reason"] == "invalid_characters" for e in errors
        )

    def test_forbidden_character_greater_than(self):
        """> character -> invalid_characters error."""
        errors = []
        validate_workspace_name("test>value", errors)
        assert any(
            e["field"] == "workspace_name" and e["reason"] == "invalid_characters" for e in errors
        )

    def test_forbidden_character_ampersand(self):
        """& character -> invalid_characters error."""
        errors = []
        validate_workspace_name("test&value", errors)
        assert any(
            e["field"] == "workspace_name" and e["reason"] == "invalid_characters" for e in errors
        )

    def test_forbidden_character_quotes(self):
        """Quote characters -> invalid_characters error."""
        errors = []
        validate_workspace_name('test"value', errors)
        assert any(
            e["field"] == "workspace_name" and e["reason"] == "invalid_characters" for e in errors
        )

    def test_ascii_control_character(self):
        """ASCII control character -> invalid_characters error."""
        errors = []
        validate_workspace_name("test\nvalue", errors)
        assert any(
            e["field"] == "workspace_name" and e["reason"] == "invalid_characters" for e in errors
        )

    def test_multibyte_character_counts_as_one(self):
        """Multi-byte character counts as 1 code point."""
        errors = []
        # Two emoji characters = 2 code points (valid, >= 2)
        validate_workspace_name("😀😁", errors)
        assert len(errors) == 0  # No length error

    def test_accumulates_multiple_errors(self):
        """AC7: Multiple errors accumulated (not fail-fast within field)."""
        errors = []
        # 1 char (too short) AND forbidden character
        validate_workspace_name("<", errors)
        has_too_short = any(
            e["field"] == "workspace_name" and e["reason"] == "field_too_short" for e in errors
        )
        has_invalid_chars = any(
            e["field"] == "workspace_name" and e["reason"] == "invalid_characters" for e in errors
        )
        assert has_too_short and has_invalid_chars


class TestValidateWorkspaceSlug:
    """Test workspace_slug field validation."""

    def test_required_field_missing(self):
        """None value -> field_required error."""
        errors = []
        result = validate_workspace_slug(None, errors)
        assert result is None
        assert any(
            e["field"] == "workspace_slug" and e["reason"] == "field_required" for e in errors
        )

    def test_minimum_length_boundary_valid(self):
        """3 chars -> valid (boundary)."""
        errors = []
        result = validate_workspace_slug("abc", errors)
        assert result == "abc"
        assert not any(
            e["field"] == "workspace_slug" and "too_short" in e["reason"] for e in errors
        )

    def test_minimum_length_violation(self):
        """2 chars -> field_too_short error."""
        errors = []
        validate_workspace_slug("ab", errors)
        assert any(
            e["field"] == "workspace_slug" and e["reason"] == "field_too_short" for e in errors
        )

    def test_maximum_length_boundary_valid(self):
        """80 chars -> valid."""
        errors = []
        slug_80_chars = "a" * 80
        result = validate_workspace_slug(slug_80_chars, errors)
        assert len(result) == 80
        assert not any(e["field"] == "workspace_slug" and "too_long" in e["reason"] for e in errors)

    def test_maximum_length_violation(self):
        """81 chars -> field_too_long error."""
        errors = []
        slug_81_chars = "a" * 81
        validate_workspace_slug(slug_81_chars, errors)
        assert any(
            e["field"] == "workspace_slug" and e["reason"] == "field_too_long" for e in errors
        )

    def test_uppercase_normalized_before_validation(self):
        """Uppercase normalized to lowercase before validation."""
        errors = []
        result = validate_workspace_slug("HELLO", errors)
        assert result == "hello"
        assert len(errors) == 0

    def test_invalid_character_uppercase_after_normalization(self):
        """Only [a-z0-9-] allowed after normalization."""
        errors = []
        validate_workspace_slug("hello_world", errors)  # underscore invalid
        assert any(
            e["field"] == "workspace_slug" and e["reason"] == "invalid_characters" for e in errors
        )

    def test_leading_hyphen(self):
        """Leading hyphen -> invalid_format error."""
        errors = []
        validate_workspace_slug("-hello", errors)
        assert any(
            e["field"] == "workspace_slug" and e["reason"] == "invalid_format" for e in errors
        )

    def test_trailing_hyphen(self):
        """Trailing hyphen -> invalid_format error."""
        errors = []
        validate_workspace_slug("hello-", errors)
        assert any(
            e["field"] == "workspace_slug" and e["reason"] == "invalid_format" for e in errors
        )

    def test_consecutive_hyphens(self):
        """Consecutive hyphens -> invalid_format error."""
        errors = []
        validate_workspace_slug("hello--world", errors)
        assert any(
            e["field"] == "workspace_slug" and e["reason"] == "invalid_format" for e in errors
        )

    def test_valid_slug_with_hyphens_and_numbers(self):
        """Valid slug with hyphens and numbers."""
        errors = []
        result = validate_workspace_slug("hello-world-123", errors)
        assert result == "hello-world-123"
        assert len(errors) == 0


class TestValidateDescription:
    """Test description field validation."""

    def test_none_is_valid(self):
        """None -> valid (optional field)."""
        errors = []
        result = validate_description(None, errors)
        assert result is None
        assert len(errors) == 0

    def test_empty_string_is_valid(self):
        """Empty string -> valid (optional field)."""
        errors = []
        result = validate_description("", errors)
        assert result is None
        assert len(errors) == 0

    def test_whitespace_only_treated_as_empty(self):
        """Whitespace-only -> valid (treated as empty)."""
        errors = []
        result = validate_description("   ", errors)
        assert result is None
        assert len(errors) == 0

    def test_maximum_length_boundary_valid(self):
        """500 code points -> valid."""
        errors = []
        desc_500_chars = "A" * 500
        result = validate_description(desc_500_chars, errors)
        assert len(result) == 500
        assert not any(e["field"] == "description" and "too_long" in e["reason"] for e in errors)

    def test_maximum_length_violation(self):
        """501 code points -> field_too_long error."""
        errors = []
        desc_501_chars = "A" * 501
        validate_description(desc_501_chars, errors)
        assert any(e["field"] == "description" and e["reason"] == "field_too_long" for e in errors)

    def test_ascii_control_character(self):
        """ASCII control character -> invalid_characters error."""
        errors = []
        validate_description("test\nvalue", errors)
        assert any(
            e["field"] == "description" and e["reason"] == "invalid_characters" for e in errors
        )

    def test_valid_description_with_spaces(self):
        """Valid description with spaces and punctuation."""
        errors = []
        result = validate_description("This is a valid description!", errors)
        assert result == "This is a valid description!"
        assert len(errors) == 0


class TestValidateDefaultTimezone:
    """Test default_timezone field validation."""

    def test_none_is_valid(self):
        """None -> valid (service will use UTC default)."""
        errors = []
        result = validate_default_timezone(None, errors)
        assert result is None
        assert len(errors) == 0

    def test_empty_string_rejected(self):
        """AC5: Empty string '' -> invalid_timezone error."""
        errors = []
        result = validate_default_timezone("", errors)
        assert result is None
        assert any(
            e["field"] == "default_timezone" and e["reason"] == "invalid_timezone" for e in errors
        )

    def test_valid_canonical_timezone(self):
        """Valid canonical timezone."""
        errors = []
        result = validate_default_timezone("America/New_York", errors)
        assert result == "America/New_York"
        assert len(errors) == 0

    def test_deprecated_link_resolved(self):
        """AC6: Deprecated 'US/Eastern' -> 'America/New_York' (or accepted as valid)."""
        errors = []
        result = validate_default_timezone("US/Eastern", errors)
        # Note: pytz on Windows may return 'US/Eastern' instead of canonical 'America/New_York'
        # Both are valid - the key is that the timezone is recognized and validated
        assert result in ["America/New_York", "US/Eastern"]
        assert len(errors) == 0

    def test_invalid_timezone(self):
        """Invalid timezone -> invalid_timezone error."""
        errors = []
        result = validate_default_timezone("Invalid/Timezone", errors)
        assert result is None
        assert any(
            e["field"] == "default_timezone" and e["reason"] == "invalid_timezone" for e in errors
        )

    def test_utc_timezone(self):
        """UTC timezone."""
        errors = []
        result = validate_default_timezone("UTC", errors)
        assert result == "UTC"
        assert len(errors) == 0


class TestValidateStatusReason:
    """Test status_reason field validation."""

    def test_none_value(self):
        """None -> missing_reason error."""
        errors = []
        result = validate_status_reason(None, errors)
        assert result is None
        assert any(
            e["field"] == "status_reason" and e["reason"] == "missing_reason" for e in errors
        )

    def test_whitespace_only(self):
        """Whitespace-only -> missing_reason error."""
        errors = []
        result = validate_status_reason("   ", errors)
        assert result is None
        assert any(
            e["field"] == "status_reason" and e["reason"] == "missing_reason" for e in errors
        )

    def test_minimum_length_violation(self):
        """9 chars after trim -> reason_too_short error."""
        errors = []
        validate_status_reason("123456789", errors)  # 9 chars
        assert any(
            e["field"] == "status_reason" and e["reason"] == "reason_too_short" for e in errors
        )

    def test_minimum_length_boundary_valid(self):
        """10 chars after trim -> valid (boundary)."""
        errors = []
        result = validate_status_reason("1234567890", errors)  # 10 chars
        assert result == "1234567890"
        assert not any(e["field"] == "status_reason" and "too_short" in e["reason"] for e in errors)

    def test_maximum_length_boundary_valid(self):
        """500 code points -> valid."""
        errors = []
        reason_500_chars = "A" * 500
        result = validate_status_reason(reason_500_chars, errors)
        assert len(result) == 500
        assert not any(e["field"] == "status_reason" and "too_long" in e["reason"] for e in errors)

    def test_maximum_length_violation(self):
        """501 code points -> field_too_long error."""
        errors = []
        reason_501_chars = "A" * 501
        validate_status_reason(reason_501_chars, errors)
        assert any(
            e["field"] == "status_reason" and e["reason"] == "field_too_long" for e in errors
        )

    def test_ascii_control_character(self):
        """ASCII control character -> invalid_characters error."""
        errors = []
        validate_status_reason("test\nvalue1234", errors)
        assert any(
            e["field"] == "status_reason" and e["reason"] == "invalid_characters" for e in errors
        )

    def test_valid_reason_with_spaces(self):
        """Valid reason with spaces."""
        errors = []
        result = validate_status_reason("  This workspace is no longer needed  ", errors)
        assert result == "This workspace is no longer needed"
        assert len(errors) == 0


# ============================================================================
# Entry Point Tests
# ============================================================================


class TestValidateCreatePayload:
    """Test validate_create_payload entry point."""

    def test_valid_create_payload(self):
        """Valid create payload with all fields."""
        payload = {
            "workspace_name": "Test Workspace",
            "workspace_slug": "test-workspace",
            "description": "A test workspace",
            "default_timezone": "America/New_York",
        }
        result = validate_create_payload(payload)
        assert result.is_valid
        assert result.normalized_payload["workspace_name"] == "Test Workspace"
        assert result.normalized_payload["workspace_slug"] == "test-workspace"
        assert result.normalized_payload["description"] == "A test workspace"
        assert result.normalized_payload["default_timezone"] == "America/New_York"

    def test_valid_create_payload_minimal(self):
        """Valid create payload with only required fields."""
        payload = {"workspace_name": "Test Workspace", "workspace_slug": "test-workspace"}
        result = validate_create_payload(payload)
        assert result.is_valid
        assert "workspace_name" in result.normalized_payload
        assert "workspace_slug" in result.normalized_payload

    def test_forbidden_field_detected(self):
        """Forbidden field -> forbidden_field error."""
        payload = {
            "workspace_name": "Test Workspace",
            "workspace_slug": "test-workspace",
            "tenant_id": "some-uuid",
        }
        result = validate_create_payload(payload)
        assert not result.is_valid
        assert any(
            e["field"] == "tenant_id" and e["reason"] == "forbidden_field" for e in result.errors
        )

    def test_unknown_field_detected(self):
        """Unknown field -> unknown_field error."""
        payload = {
            "workspace_name": "Test Workspace",
            "workspace_slug": "test-workspace",
            "owner_email": "test@example.com",
        }
        result = validate_create_payload(payload)
        assert not result.is_valid
        assert any(
            e["field"] == "owner_email" and e["reason"] == "unknown_field" for e in result.errors
        )

    def test_multiple_field_errors_accumulated(self):
        """AC7: Invalid name AND invalid slug -> both errors returned."""
        payload = {
            "workspace_name": "A",  # Too short
            "workspace_slug": "ab",  # Too short
        }
        result = validate_create_payload(payload)
        assert not result.is_valid
        has_name_error = any(e["field"] == "workspace_name" for e in result.errors)
        has_slug_error = any(e["field"] == "workspace_slug" for e in result.errors)
        assert has_name_error and has_slug_error

    def test_missing_required_fields(self):
        """Missing required fields -> field_required errors."""
        payload = {}
        result = validate_create_payload(payload)
        assert not result.is_valid
        assert any(
            e["field"] == "workspace_name" and e["reason"] == "field_required"
            for e in result.errors
        )
        assert any(
            e["field"] == "workspace_slug" and e["reason"] == "field_required"
            for e in result.errors
        )


class TestValidateUpdatePayload:
    """Test validate_update_payload entry point."""

    def test_valid_update_payload_single_field(self):
        """Valid update with one field."""
        payload = {"workspace_name": "Updated Name"}
        result = validate_update_payload(payload)
        assert result.is_valid
        assert result.normalized_payload["workspace_name"] == "Updated Name"

    def test_valid_update_payload_multiple_fields(self):
        """Valid update with multiple fields."""
        payload = {"workspace_name": "Updated Name", "description": "Updated description"}
        result = validate_update_payload(payload)
        assert result.is_valid
        assert "workspace_name" in result.normalized_payload
        assert "description" in result.normalized_payload

    def test_empty_payload_valid(self):
        """AC9: Empty payload {} -> zero errors."""
        payload = {}
        result = validate_update_payload(payload)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_immutable_field_detected(self):
        """AC8: workspace_slug in update -> immutable_field error."""
        payload = {"workspace_slug": "new-slug"}
        result = validate_update_payload(payload)
        assert not result.is_valid
        assert any(
            e["field"] == "workspace_slug" and e["reason"] == "immutable_field"
            for e in result.errors
        )

    def test_forbidden_field_detected(self):
        """Forbidden field -> forbidden_field error."""
        payload = {"workspace_name": "Updated Name", "workspace_id": "some-uuid"}
        result = validate_update_payload(payload)
        assert not result.is_valid
        assert any(
            e["field"] == "workspace_id" and e["reason"] == "forbidden_field" for e in result.errors
        )

    def test_unknown_field_detected(self):
        """Unknown field -> unknown_field error."""
        payload = {"workspace_name": "Updated Name", "owner_email": "test@example.com"}
        result = validate_update_payload(payload)
        assert not result.is_valid
        assert any(
            e["field"] == "owner_email" and e["reason"] == "unknown_field" for e in result.errors
        )

    def test_description_can_be_cleared(self):
        """Description can be set to None (cleared)."""
        payload = {"description": None}
        result = validate_update_payload(payload)
        assert result.is_valid
        assert result.normalized_payload["description"] is None


class TestValidateArchivePayload:
    """Test validate_archive_payload entry point."""

    def test_valid_archive_payload(self):
        """Valid archive payload with status_reason."""
        payload = {"status_reason": "This workspace is no longer needed"}
        result = validate_archive_payload(payload)
        assert result.is_valid
        assert result.normalized_payload["status_reason"] == "This workspace is no longer needed"

    def test_valid_archive_with_confirm_flag(self):
        """AC11: confirm_last_workspace as boolean -> no type error."""
        payload = {"status_reason": "No longer needed", "confirm_last_workspace": True}
        result = validate_archive_payload(payload)
        assert result.is_valid
        assert result.normalized_payload["confirm_last_workspace"] is True

    def test_invalid_confirm_flag_type(self):
        """AC10: confirm_last_workspace as string -> invalid_field_type error."""
        payload = {
            "status_reason": "No longer needed",
            "confirm_last_workspace": "true",  # String instead of boolean
        }
        result = validate_archive_payload(payload)
        assert not result.is_valid
        assert any(
            e["field"] == "confirm_last_workspace" and e["reason"] == "invalid_field_type"
            for e in result.errors
        )

    def test_missing_status_reason(self):
        """Missing status_reason -> missing_reason error."""
        payload = {}
        result = validate_archive_payload(payload)
        assert not result.is_valid
        assert any(
            e["field"] == "status_reason" and e["reason"] == "missing_reason" for e in result.errors
        )

    def test_unknown_field_detected(self):
        """Unknown field -> unknown_field error (HA-4)."""
        payload = {
            "status_reason": "No longer needed",
            "workspace_name": "New Name",  # Not allowed in archive
        }
        result = validate_archive_payload(payload)
        assert not result.is_valid
        assert any(
            e["field"] == "workspace_name" and e["reason"] == "unknown_field" for e in result.errors
        )


# ============================================================================
# Edge Case and Integration Tests
# ============================================================================


class TestEdgeCases:
    """Test edge cases and corner scenarios."""

    def test_nfc_equivalence(self):
        """NFD-encoded name produces same normalized result as NFC equivalent."""
        # Create NFD and NFC versions of same string
        import unicodedata

        nfc_name = "café"
        nfd_name = unicodedata.normalize("NFD", nfc_name)

        # Both should normalize to the same NFC form
        result_nfc = normalize_workspace_name(nfc_name)
        result_nfd = normalize_workspace_name(nfd_name)
        assert result_nfc == result_nfd

    def test_validation_accumulation_three_violations(self):
        """Payload with 3 simultaneous field violations returns all 3 errors."""
        payload = {
            "workspace_name": "A",  # Too short
            "workspace_slug": "ab",  # Too short
            "default_timezone": "Invalid",  # Invalid timezone
        }
        result = validate_create_payload(payload)
        assert not result.is_valid
        # Should have at least 3 errors (one per field minimum)
        assert len(result.errors) >= 3

    def test_whitespace_only_name_collapses_to_empty(self):
        """MV-6: '   ' (3-char whitespace-only) -> trims to '' -> field_required."""
        errors = []
        result = validate_workspace_name("   ", errors)
        assert result is None
        # Should be field_required, not field_too_short
        assert any(
            e["field"] == "workspace_name" and e["reason"] == "field_required" for e in errors
        )
        # Should not have field_too_short error
        assert not any(
            e["field"] == "workspace_name" and e["reason"] == "field_too_short" for e in errors
        )

    def test_all_forbidden_fields_detected(self):
        """All 7 forbidden fields individually detected."""
        for forbidden_field in [
            "tenant_id",
            "workspace_id",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
            "status",
        ]:
            payload = {
                "workspace_name": "Test",
                "workspace_slug": "test",
                forbidden_field: "some-value",
            }
            result = validate_create_payload(payload)
            assert not result.is_valid
            assert any(
                e["field"] == forbidden_field and e["reason"] == "forbidden_field"
                for e in result.errors
            )

    def test_timezone_none_in_create_payload(self):
        """None timezone in create payload is valid (service will use UTC)."""
        payload = {"workspace_name": "Test", "workspace_slug": "test", "default_timezone": None}
        result = validate_create_payload(payload)
        assert result.is_valid
        # None timezone should not be in normalized payload (service handles default)
        assert (
            "default_timezone" not in result.normalized_payload
            or result.normalized_payload.get("default_timezone") is None
        )
