"""
F134 P03 — Demo Request Validation (DB-free)

Validates all fields of the public intake form.
Returns a list of (field, message) tuples. An empty list means "valid".
No DB imports, no FastAPI Depends, no ORM.
"""

from __future__ import annotations

import re

# ── Constants ─────────────────────────────────────────────────────────────────

PERSONAL_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "aol.com",
        "icloud.com",
        "proton.me",
        "yandex.com",
        "live.com",
        "mail.com",
    }
)

RESERVED_TLDS: frozenset[str] = frozenset(
    {
        "local",
        "test",
        "invalid",
        "localhost",
        "example",
    }
)

VALID_TEAM_SIZES: frozenset[str] = frozenset(
    {
        "1-10",
        "11-50",
        "51-200",
        "201-1000",
        "1000+",
    }
)

# Minimal RFC-5322–inspired pattern: local@domain.tld
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*"
    r"\.[a-zA-Z]{2,}$"
)

# Names: letters (including accented), spaces, hyphens, apostrophes
_NAME_RE = re.compile(r"^[\w\s'\-]+$", re.UNICODE)

ValidationErrors = list[tuple[str, str]]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_tld(email: str) -> str:
    """Return the TLD portion of an email domain."""
    try:
        domain = email.rsplit("@", 1)[1].lower()
        return domain.rsplit(".", 1)[-1]
    except (IndexError, ValueError):
        return ""


def _get_domain(email: str) -> str:
    """Return the full domain of an email address (lowercase)."""
    try:
        return email.rsplit("@", 1)[1].lower().strip()
    except (IndexError, ValueError):
        return ""


def is_personal_email(email: str) -> bool:
    """Return True if the email's domain is in the personal-domain list."""
    return _get_domain(email) in PERSONAL_EMAIL_DOMAINS


# ── Validators ────────────────────────────────────────────────────────────────


def validate_work_email(email: str) -> ValidationErrors:
    errors: ValidationErrors = []
    if not email or not email.strip():
        errors.append(("work_email", "Please provide a valid work email."))
        return errors
    email = email.strip()
    if not _EMAIL_RE.match(email):
        errors.append(("work_email", "Please provide a valid work email."))
        return errors
    tld = _get_tld(email)
    if tld in RESERVED_TLDS:
        errors.append(("work_email", "Please provide a valid work email."))
    return errors


def validate_name(value: str, field: str) -> ValidationErrors:
    errors: ValidationErrors = []
    stripped = (value or "").strip()
    if not stripped:
        errors.append((field, "Please enter a valid name."))
        return errors
    if len(stripped) > 60:
        errors.append((field, "Please enter a valid name."))
        return errors
    if not _NAME_RE.match(stripped):
        errors.append((field, "Please enter a valid name."))
    return errors


def validate_company_name(value: str) -> ValidationErrors:
    errors: ValidationErrors = []
    stripped = (value or "").strip()
    if len(stripped) < 2:
        errors.append(("company_name", "Company name is required."))
    elif len(stripped) > 120:
        errors.append(("company_name", "Company name is required."))
    return errors


def validate_team_size(value: str) -> ValidationErrors:
    if value not in VALID_TEAM_SIZES:
        return [("team_size", "Please select a team size.")]
    return []


def validate_primary_use_case(value: str) -> ValidationErrors:
    stripped = (value or "").strip()
    if len(stripped) < 10 or len(stripped) > 500:
        return [("primary_use_case", "Please describe your use case (at least 10 characters).")]
    return []


def validate_consent(value: bool) -> ValidationErrors:
    if value is not True:
        return [("consent", "You must accept the terms to continue.")]
    return []


def validate_country(value: str | None) -> ValidationErrors:
    """Country is optional; if provided must be 2 uppercase letters."""
    if value is None:
        return []
    if not re.match(r"^[A-Z]{2}$", value):
        return [("country", "Country must be a valid ISO-3166-1 alpha-2 code.")]
    return []


def validate_demo_request(
    *,
    work_email: str,
    first_name: str,
    last_name: str,
    company_name: str,
    team_size: str,
    primary_use_case: str,
    consent: bool,
    country: str | None = None,
) -> ValidationErrors:
    """
    Full intake form validation — run all field validators and aggregate errors.
    Returns a list of (field, message) errors. Empty list means valid.
    """
    errors: ValidationErrors = []
    errors.extend(validate_work_email(work_email))
    errors.extend(validate_name(first_name, "first_name"))
    errors.extend(validate_name(last_name, "last_name"))
    errors.extend(validate_company_name(company_name))
    errors.extend(validate_team_size(team_size))
    errors.extend(validate_primary_use_case(primary_use_case))
    errors.extend(validate_consent(consent))
    errors.extend(validate_country(country))
    return errors
