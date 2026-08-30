"""
Packet 3 — Unit tests: field-level validators and normalisation
================================================================

Tests for every rule in TDD §6.1–6.8 applied to the validator functions
in ``app.services.tenants.validators``.

No database dependency. All 422-producing paths are asserted by catching
``TenantAPIError`` and checking ``.code`` and ``.fields``.

Run inside Docker:
    docker-compose exec backend python -m pytest \
        tests/unit/services/f001/test_p3_create_tenant_validators.py -v
"""

from __future__ import annotations

import pytest
from app.api.v1.dependencies.tenant_auth import TenantAPIError
from app.services.tenants.validators import (
    VALID_CREATE_STATUSES,
    VALID_PLANS,
    VALID_REGIONS,
    validate_initial_status,
    validate_plan,
    validate_region,
    validate_service_start_date,
    validate_status_reason,
    validate_tenant_name,
    validate_tenant_notes,
    validate_tenant_slug,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raises(fn, *args, expected_code: str, **kwargs) -> TenantAPIError:
    """Assert that *fn* raises TenantAPIError with the given code."""
    with pytest.raises(TenantAPIError) as exc_info:
        fn(*args, **kwargs)
    err: TenantAPIError = exc_info.value
    assert err.code == expected_code, (
        f"Expected code='{expected_code}' but got '{err.code}'. message={err.message!r}"
    )
    assert err.status_code == 422
    return err


# ===========================================================================
# validate_tenant_name — TDD §6.1
# ===========================================================================


class TestValidateTenantName:
    def test_valid_name_returned_trimmed(self):
        assert validate_tenant_name("  Acme Corp  ") == "Acme Corp"

    def test_valid_minimal_name(self):
        assert validate_tenant_name("AB") == "AB"  # exactly 2 chars

    def test_valid_max_length_name(self):
        assert validate_tenant_name("A" * 150) == "A" * 150

    def test_none_raises_required(self):
        err = _raises(validate_tenant_name, None, expected_code="validation_error")
        assert any(
            f["field"] == "tenant_name" and f["reason"] == "required" for f in (err.fields or [])
        )

    def test_empty_string_raises_required(self):
        err = _raises(validate_tenant_name, "", expected_code="validation_error")
        assert any(f["field"] == "tenant_name" for f in (err.fields or []))

    def test_whitespace_only_raises_required(self):
        _raises(validate_tenant_name, "   ", expected_code="validation_error")

    def test_too_short_one_char_raises(self):
        err = _raises(validate_tenant_name, "A", expected_code="validation_error")
        assert any(f["reason"] == "min_length" for f in (err.fields or []))

    def test_too_long_151_chars_raises(self):
        err = _raises(validate_tenant_name, "A" * 151, expected_code="validation_error")
        assert any(f["reason"] == "max_length" for f in (err.fields or []))

    @pytest.mark.parametrize("char", ["<", ">", "&", '"', "'", "`"])
    def test_forbidden_char_raises(self, char):
        err = _raises(validate_tenant_name, f"Valid{char}Name", expected_code="validation_error")
        assert any(f["reason"] == "invalid_characters" for f in (err.fields or []))

    @pytest.mark.parametrize("code_point", ["\x00", "\x1f", "\x7f"])
    def test_ascii_control_char_raises(self, code_point):
        err = _raises(validate_tenant_name, f"Name{code_point}X", expected_code="validation_error")
        assert any(f["reason"] == "invalid_characters" for f in (err.fields or []))

    def test_name_with_unicode_letters_accepted(self):
        # Accented characters are NOT in the forbidden set
        result = validate_tenant_name("München GmbH")
        assert result == "München GmbH"

    def test_name_with_dash_and_numbers_accepted(self):
        assert validate_tenant_name("Tenant-01") == "Tenant-01"

    def test_leading_trailing_whitespace_trimmed(self):
        assert validate_tenant_name("  Hello  ") == "Hello"


# ===========================================================================
# validate_tenant_slug — TDD §6.2
# ===========================================================================


class TestValidateTenantSlug:
    def test_valid_slug_returned_normalised(self):
        assert validate_tenant_slug("acme-corp") == "acme-corp"

    def test_uppercase_normalised_to_lowercase(self):
        assert validate_tenant_slug("ACME-Corp") == "acme-corp"

    def test_with_leading_trailing_spaces(self):
        assert validate_tenant_slug("  myslug  ") == "myslug"

    def test_none_raises_required(self):
        _raises(validate_tenant_slug, None, expected_code="validation_error")

    def test_empty_raises_required(self):
        _raises(validate_tenant_slug, "", expected_code="validation_error")

    def test_too_short_two_chars_raises(self):
        err = _raises(validate_tenant_slug, "ab", expected_code="validation_error")
        assert any(f["reason"] == "invalid_length" for f in (err.fields or []))

    def test_exactly_three_chars_accepted(self):
        assert validate_tenant_slug("abc") == "abc"

    def test_exactly_80_chars_accepted(self):
        slug = "a" * 80
        assert validate_tenant_slug(slug) == slug

    def test_81_chars_raises(self):
        err = _raises(validate_tenant_slug, "a" * 81, expected_code="validation_error")
        assert any(f["reason"] == "invalid_length" for f in (err.fields or []))

    def test_leading_hyphen_raises(self):
        err = _raises(validate_tenant_slug, "-acme", expected_code="validation_error")
        assert any(f["reason"] == "invalid_format" for f in (err.fields or []))

    def test_trailing_hyphen_raises(self):
        err = _raises(validate_tenant_slug, "acme-", expected_code="validation_error")
        assert any(f["reason"] == "invalid_format" for f in (err.fields or []))

    def test_consecutive_hyphens_raises(self):
        err = _raises(validate_tenant_slug, "ac--me", expected_code="validation_error")
        assert any(f["reason"] == "invalid_format" for f in (err.fields or []))

    @pytest.mark.parametrize("char", ["_", ".", " ", "!", "@"])
    def test_invalid_chars_raises(self, char):
        err = _raises(validate_tenant_slug, f"valid{char}slug", expected_code="validation_error")
        # Either invalid_characters or invalid_format depending on char
        assert err.fields is not None

    def test_numbers_in_slug_accepted(self):
        assert validate_tenant_slug("tenant-123") == "tenant-123"

    def test_all_digits_accepted(self):
        assert validate_tenant_slug("1234") == "1234"


# ===========================================================================
# validate_region — TDD §6.3
# ===========================================================================


class TestValidateRegion:
    @pytest.mark.parametrize("region", sorted(VALID_REGIONS))
    def test_valid_regions_accepted(self, region):
        assert validate_region(region) == region

    def test_uppercase_normalised(self):
        assert validate_region("EU-WEST") == "eu-west"

    def test_with_whitespace(self):
        assert validate_region("  eu-west  ") == "eu-west"

    def test_none_raises_required(self):
        _raises(validate_region, None, expected_code="validation_error")

    def test_empty_raises_required(self):
        _raises(validate_region, "", expected_code="validation_error")

    def test_invalid_region_code(self):
        _raises(validate_region, "ap-southeast", expected_code="invalid_region")

    def test_unknown_string_raises_invalid_region(self):
        _raises(validate_region, "somewhere", expected_code="invalid_region")


# ===========================================================================
# validate_plan — TDD §6.4
# ===========================================================================


class TestValidatePlan:
    @pytest.mark.parametrize("plan", sorted(VALID_PLANS))
    def test_valid_plans_accepted(self, plan):
        assert validate_plan(plan) == plan

    def test_uppercase_normalised(self):
        assert validate_plan("STARTER") == "starter"

    def test_none_raises_required(self):
        _raises(validate_plan, None, expected_code="validation_error")

    def test_empty_raises_required(self):
        _raises(validate_plan, "", expected_code="validation_error")

    def test_invalid_plan_string(self):
        _raises(validate_plan, "premium", expected_code="invalid_plan")


# ===========================================================================
# validate_initial_status — TDD §6.5
# ===========================================================================


class TestValidateInitialStatus:
    def test_none_defaults_to_draft(self):
        assert validate_initial_status(None) == "draft"

    def test_empty_string_defaults_to_draft(self):
        assert validate_initial_status("") == "draft"

    def test_whitespace_only_defaults_to_draft(self):
        assert validate_initial_status("   ") == "draft"

    def test_draft_accepted(self):
        assert validate_initial_status("draft") == "draft"

    def test_active_accepted(self):
        assert validate_initial_status("active") == "active"

    def test_uppercase_draft_normalised(self):
        assert validate_initial_status("DRAFT") == "draft"

    def test_suspended_raises_invalid_status(self):
        _raises(validate_initial_status, "suspended", expected_code="invalid_status")

    def test_archived_raises_invalid_status(self):
        _raises(validate_initial_status, "archived", expected_code="invalid_status")

    def test_arbitrary_string_raises_invalid_status(self):
        _raises(validate_initial_status, "online", expected_code="invalid_status")


# ===========================================================================
# validate_service_start_date — TDD §6.6
# ===========================================================================


class TestValidateServiceStartDate:
    def test_none_returns_none(self):
        assert validate_service_start_date(None) is None

    def test_empty_returns_none(self):
        assert validate_service_start_date("") is None

    def test_valid_date_parsed(self):
        from datetime import date

        result = validate_service_start_date("2025-01-15")
        assert result == date(2025, 1, 15)

    def test_wrong_format_raises(self):
        _raises(validate_service_start_date, "15/01/2025", expected_code="validation_error")

    def test_invalid_calendar_date_raises(self):
        _raises(validate_service_start_date, "2025-02-30", expected_code="validation_error")

    def test_iso_date_with_time_rejected(self):
        _raises(
            validate_service_start_date, "2025-01-15T10:00:00", expected_code="validation_error"
        )


# ===========================================================================
# validate_tenant_notes — TDD §6.7
# ===========================================================================


class TestValidateTenantNotes:
    def test_none_returns_none(self):
        assert validate_tenant_notes(None) is None

    def test_whitespace_only_coerced_to_none(self):
        assert validate_tenant_notes("   ") is None

    def test_valid_notes_trimmed(self):
        assert validate_tenant_notes("  Some notes  ") == "Some notes"

    def test_exactly_5000_chars_accepted(self):
        assert validate_tenant_notes("A" * 5000) == "A" * 5000

    def test_5001_chars_raises(self):
        err = _raises(validate_tenant_notes, "A" * 5001, expected_code="validation_error")
        assert any(f["reason"] == "max_length" for f in (err.fields or []))

    @pytest.mark.parametrize("code_point", ["\x00", "\x01", "\x1f", "\x7f"])
    def test_control_char_raises(self, code_point):
        err = _raises(
            validate_tenant_notes, f"Notes{code_point}content", expected_code="validation_error"
        )
        assert any(f["reason"] == "invalid_characters" for f in (err.fields or []))

    def test_newline_char_raises(self):
        # \n is \x0A, inside 0x00–0x1F control range
        _raises(validate_tenant_notes, "Line1\nLine2", expected_code="validation_error")

    def test_unicode_content_accepted(self):
        notes = "Résumé notes — €500 budget"
        assert validate_tenant_notes(notes) == notes


# ===========================================================================
# validate_status_reason
# ===========================================================================


class TestValidateStatusReason:
    def test_none_returns_none(self):
        assert validate_status_reason(None) is None

    def test_empty_returns_none(self):
        assert validate_status_reason("") is None

    def test_whitespace_returns_none(self):
        assert validate_status_reason("   ") is None

    def test_valid_reason_trimmed(self):
        assert validate_status_reason("  valid reason  ") == "valid reason"

    def test_501_chars_raises(self):
        _raises(validate_status_reason, "x" * 501, expected_code="validation_error")

    def test_exactly_500_chars_accepted(self):
        assert validate_status_reason("x" * 500) == "x" * 500

    def test_control_char_raises(self):
        _raises(validate_status_reason, "reason\x00here", expected_code="validation_error")


# ===========================================================================
# Normalisation integration — combined field flow
# ===========================================================================


class TestNormalisationFlow:
    """Verify that the field order and combination of validators matches §4.2 step 2."""

    def test_all_required_fields_normalised_together(self):
        from datetime import date

        name = validate_tenant_name("  Acme Corp  ")
        slug = validate_tenant_slug("  ACME-Corp  ")
        region = validate_region("  EU-WEST  ")
        plan = validate_plan("  STARTER  ")
        status = validate_initial_status(None)  # defaults to draft
        ssd = validate_service_start_date("2025-06-01")
        notes = validate_tenant_notes("  Some notes.  ")
        reason = validate_status_reason(None)

        assert name == "Acme Corp"
        assert slug == "acme-corp"
        assert region == "eu-west"
        assert plan == "starter"
        assert status == "draft"
        assert ssd == date(2025, 6, 1)
        assert notes == "Some notes."
        assert reason is None

    def test_created_by_and_updated_by_come_from_actor_not_body(self):
        """
        The endpoint must ignore any 'created_by' / 'updated_by' values in the
        body (CreateTenantRequest.model_config extra='ignore' handles this).
        We assert the model silently drops unknown fields.
        """
        from app.services.tenants.commands import CreateTenantRequest

        req = CreateTenantRequest.model_validate(
            {
                "tenant_name": "Acme",
                "tenant_slug": "acme",
                "region": "eu-west",
                "plan": "starter",
                "created_by": "should-be-ignored",
                "updated_by": "should-be-ignored",
                "version": 99,
            }
        )
        assert not hasattr(req, "created_by")
        assert not hasattr(req, "version")
