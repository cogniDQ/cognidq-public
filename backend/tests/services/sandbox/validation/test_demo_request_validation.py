"""
F134 P03 — Tests for demo_request_validation.py
"""

import pytest
from app.services.sandbox.validation.demo_request_validation import (
    PERSONAL_EMAIL_DOMAINS,
    RESERVED_TLDS,
    VALID_TEAM_SIZES,
    is_personal_email,
    validate_company_name,
    validate_consent,
    validate_country,
    validate_demo_request,
    validate_name,
    validate_primary_use_case,
    validate_team_size,
    validate_work_email,
)

# ── validate_work_email ────────────────────────────────────────────────────────


class TestValidateWorkEmail:
    def test_valid_work_email(self):
        assert validate_work_email("user@company.com") == []

    def test_empty_email_returns_error(self):
        errs = validate_work_email("")
        assert len(errs) == 1
        assert errs[0][0] == "work_email"

    def test_whitespace_only_returns_error(self):
        assert validate_work_email("   ") != []

    def test_missing_at_returns_error(self):
        assert validate_work_email("notanemail") != []

    def test_missing_tld_returns_error(self):
        assert validate_work_email("user@company") != []

    def test_reserved_tld_local(self):
        errs = validate_work_email("user@company.local")
        assert len(errs) == 1

    def test_reserved_tld_test(self):
        assert validate_work_email("user@corp.test") != []

    def test_reserved_tld_invalid(self):
        assert validate_work_email("user@corp.invalid") != []

    def test_reserved_tld_localhost(self):
        assert validate_work_email("user@corp.localhost") != []

    def test_reserved_tld_example(self):
        assert validate_work_email("user@corp.example") != []

    def test_personal_domain_gmail_accepted_without_error(self):
        # personal email still passes email format validation (just flagged separately)
        assert validate_work_email("user@gmail.com") == []

    def test_plus_addressing_valid(self):
        assert validate_work_email("user+tag@company.org") == []

    def test_subdomain_valid(self):
        assert validate_work_email("user@mail.company.co.uk") == []


# ── is_personal_email ─────────────────────────────────────────────────────────


class TestIsPersonalEmail:
    def test_gmail_detected(self):
        assert is_personal_email("john@gmail.com") is True

    def test_work_email_not_flagged(self):
        assert is_personal_email("john@acme.com") is False

    @pytest.mark.parametrize("domain", list(PERSONAL_EMAIL_DOMAINS))
    def test_all_personal_domains_detected(self, domain):
        assert is_personal_email(f"user@{domain}") is True


# ── validate_name ─────────────────────────────────────────────────────────────


class TestValidateName:
    def test_valid_first_name(self):
        assert validate_name("Alice", "first_name") == []

    def test_empty_name_returns_error(self):
        assert validate_name("", "first_name") != []

    def test_name_too_long_returns_error(self):
        assert validate_name("A" * 61, "last_name") != []

    def test_name_at_max_length_ok(self):
        assert validate_name("A" * 60, "last_name") == []

    def test_name_with_hyphen_ok(self):
        assert validate_name("Mary-Jane", "first_name") == []

    def test_name_with_apostrophe_ok(self):
        assert validate_name("O'Brien", "last_name") == []


# ── validate_company_name ─────────────────────────────────────────────────────


class TestValidateCompanyName:
    def test_valid(self):
        assert validate_company_name("Acme Corp") == []

    def test_too_short(self):
        assert validate_company_name("A") != []

    def test_empty(self):
        assert validate_company_name("") != []

    def test_exactly_2_chars(self):
        assert validate_company_name("AB") == []

    def test_too_long(self):
        assert validate_company_name("A" * 121) != []

    def test_exactly_120_chars(self):
        assert validate_company_name("A" * 120) == []


# ── validate_team_size ────────────────────────────────────────────────────────


class TestValidateTeamSize:
    @pytest.mark.parametrize("size", list(VALID_TEAM_SIZES))
    def test_valid_team_sizes(self, size):
        assert validate_team_size(size) == []

    def test_invalid_team_size(self):
        errs = validate_team_size("lots")
        assert len(errs) == 1
        assert errs[0][0] == "team_size"

    def test_empty_team_size_invalid(self):
        assert validate_team_size("") != []


# ── validate_primary_use_case ─────────────────────────────────────────────────


class TestValidatePrimaryUseCase:
    def test_valid(self):
        assert validate_primary_use_case("We need data quality checks.") == []

    def test_too_short(self):
        errs = validate_primary_use_case("short")
        assert errs != []
        assert errs[0][0] == "primary_use_case"

    def test_exactly_10_chars(self):
        assert validate_primary_use_case("1234567890") == []

    def test_too_long(self):
        assert validate_primary_use_case("A" * 501) != []

    def test_exactly_500_chars(self):
        assert validate_primary_use_case("A" * 500) == []

    def test_empty(self):
        assert validate_primary_use_case("") != []


# ── validate_consent ──────────────────────────────────────────────────────────


class TestValidateConsent:
    def test_true_ok(self):
        assert validate_consent(True) == []

    def test_false_returns_error(self):
        errs = validate_consent(False)
        assert len(errs) == 1
        assert errs[0][0] == "consent"

    def test_none_returns_error(self):
        assert validate_consent(None) != []  # type: ignore[arg-type]


# ── validate_country ──────────────────────────────────────────────────────────


class TestValidateCountry:
    def test_none_is_ok(self):
        assert validate_country(None) == []

    def test_valid_iso2(self):
        assert validate_country("US") == []
        assert validate_country("GB") == []

    def test_lowercase_invalid(self):
        assert validate_country("us") != []

    def test_three_letter_invalid(self):
        assert validate_country("USA") != []

    def test_digits_invalid(self):
        assert validate_country("12") != []


# ── validate_demo_request (aggregate) ─────────────────────────────────────────


class TestValidateDemoRequest:
    def _valid_payload(self, **overrides):
        base = dict(
            work_email="prospect@company.io",
            first_name="Alice",
            last_name="Smith",
            company_name="Acme Corp",
            team_size="11-50",
            primary_use_case="We need to improve data quality across ETL pipelines.",
            consent=True,
            country="US",
        )
        base.update(overrides)
        return base

    def test_fully_valid_returns_empty(self):
        assert validate_demo_request(**self._valid_payload()) == []

    def test_bad_email_returned_in_errors(self):
        errs = validate_demo_request(**self._valid_payload(work_email="notvalid"))
        fields = [e[0] for e in errs]
        assert "work_email" in fields

    def test_no_consent_returned_in_errors(self):
        errs = validate_demo_request(**self._valid_payload(consent=False))
        fields = [e[0] for e in errs]
        assert "consent" in fields

    def test_multiple_field_errors_accumulated(self):
        errs = validate_demo_request(
            **self._valid_payload(
                work_email="bad",
                first_name="",
                consent=False,
            )
        )
        fields = [e[0] for e in errs]
        assert "work_email" in fields
        assert "first_name" in fields
        assert "consent" in fields

    def test_optional_country_omitted_ok(self):
        errs = validate_demo_request(
            work_email="a@company.com",
            first_name="Alice",
            last_name="Smith",
            company_name="Acme",
            team_size="1-10",
            primary_use_case="We need this tool badly.",
            consent=True,
        )
        assert errs == []
