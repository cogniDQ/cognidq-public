"""
Pure validation layer for Workspace creation, update, and archival.

All functions in this module are database-free pure functions. No DB queries are performed here.
All normalization must be applied before validation.
Field-level errors are accumulated (not fail-fast).
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# Try to use zoneinfo (Python 3.9+), fallback to pytz if not available or on Windows without tzdata
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    USING_ZONEINFO = True
except ImportError:
    try:
        import pytz  # noqa: F401

        USING_ZONEINFO = False
    except ImportError:
        raise ImportError("Neither zoneinfo nor pytz is available. Install pytz: pip install pytz")


@dataclass
class ValidationResult:
    """
    Result of payload validation.

    Attributes:
        errors: List of field-level errors
        normalized_payload: Payload with normalized values (applicable fields only)
    """

    errors: list[dict[str, str]] = field(default_factory=list)
    normalized_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Returns True if there are no validation errors."""
        return len(self.errors) == 0


# ============================================================================
# Normalization Functions
# ============================================================================


def normalize_workspace_name(value: str) -> str:
    """
    Normalize workspace_name: strip whitespace, apply Unicode NFC normalization.

    Args:
        value: Raw workspace name string

    Returns:
        Normalized workspace name
    """
    trimmed = value.strip()
    return unicodedata.normalize("NFC", trimmed)


def normalize_workspace_slug(value: str) -> str:
    """
    Normalize workspace_slug: convert to lowercase.

    Args:
        value: Raw workspace slug string

    Returns:
        Lowercase workspace slug
    """
    return value.lower()


def normalize_status_reason(value: str) -> str:
    """
    Normalize status_reason: strip whitespace.

    Args:
        value: Raw status reason string

    Returns:
        Trimmed status reason
    """
    return value.strip()


def resolve_iana_timezone(value: str | None) -> str | None:
    """
    Resolve an IANA timezone string to its canonical form.

    Handles deprecated link identifiers (e.g., 'US/Eastern' -> 'America/New_York').

    Args:
        value: IANA timezone identifier or None

    Returns:
        Canonical IANA timezone identifier, or None if value is None, empty, or unresolvable
    """
    if value is None:
        return None

    if value == "":
        return None

    if USING_ZONEINFO:
        try:
            # ZoneInfo accepts both canonical and deprecated link identifiers
            zone = ZoneInfo(value)
            # Get the canonical key
            return zone.key
        except (ZoneInfoNotFoundError, ValueError, KeyError, AttributeError):
            # Fallback: if timezone data is missing (e.g., Windows without tzdata), use pytz
            try:
                import pytz

                tz = pytz.timezone(value)
                # pytz returns the zone name from the zone attribute
                return tz.zone
            except:
                return None
    else:
        # Using pytz
        try:
            tz = pytz.timezone(value)
            return tz.zone
        except:
            return None


# ============================================================================
# Character Validation Helpers
# ============================================================================


def contains_forbidden_characters(value: str) -> bool:
    """
    Check if value contains forbidden characters: < > & " ' `

    Args:
        value: String to check

    Returns:
        True if forbidden characters are present
    """
    forbidden_chars = {"<", ">", "&", '"', "'", "`"}
    return any(char in forbidden_chars for char in value)


def contains_ascii_control_characters(value: str) -> bool:
    """
    Check if value contains ASCII control characters (0x00-0x1F, 0x7F).

    Args:
        value: String to check

    Returns:
        True if ASCII control characters are present
    """
    for char in value:
        code_point = ord(char)
        if (0x00 <= code_point <= 0x1F) or (code_point == 0x7F):
            return True
    return False


def get_unicode_code_point_count(value: str) -> int:
    """
    Count Unicode code points in a string.

    Args:
        value: String to measure

    Returns:
        Number of Unicode code points
    """
    return len(value)


# ============================================================================
# Field Validators
# ============================================================================


def validate_workspace_name(raw_value: Any, errors: list[dict[str, str]]) -> str | None:
    """
    Validate and normalize workspace_name field.

    All validation errors are accumulated in the errors list.

    Args:
        raw_value: Raw workspace name value from payload
        errors: List to append validation errors to

    Returns:
        Normalized workspace name if no fatal errors, or None
    """
    if raw_value is None or raw_value == "":
        errors.append({"field": "workspace_name", "reason": "field_required"})
        return None

    if not isinstance(raw_value, str):
        errors.append({"field": "workspace_name", "reason": "invalid_field_type"})
        return None

    # Apply normalization
    normalized = normalize_workspace_name(raw_value)

    # Check if empty after trim (whitespace-only input)
    if normalized == "":
        errors.append({"field": "workspace_name", "reason": "field_required"})
        return None

    # Length checks (after normalization)
    code_point_count = get_unicode_code_point_count(normalized)

    if code_point_count < 2:
        errors.append({"field": "workspace_name", "reason": "field_too_short"})

    if code_point_count > 150:
        errors.append({"field": "workspace_name", "reason": "field_too_long"})

    # Character restrictions
    if contains_forbidden_characters(normalized):
        errors.append({"field": "workspace_name", "reason": "invalid_characters"})

    if contains_ascii_control_characters(normalized):
        errors.append({"field": "workspace_name", "reason": "invalid_characters"})

    return normalized


def validate_workspace_slug(raw_value: Any, errors: list[dict[str, str]]) -> str | None:
    """
    Validate and normalize workspace_slug field.

    All validation errors are accumulated in the errors list.

    Args:
        raw_value: Raw workspace slug value from payload
        errors: List to append validation errors to

    Returns:
        Normalized workspace slug if no fatal errors, or None
    """
    if raw_value is None or raw_value == "":
        errors.append({"field": "workspace_slug", "reason": "field_required"})
        return None

    if not isinstance(raw_value, str):
        errors.append({"field": "workspace_slug", "reason": "invalid_field_type"})
        return None

    # Apply normalization (lowercase)
    normalized = normalize_workspace_slug(raw_value)

    # Length checks (after normalization)
    slug_length = len(normalized)

    if slug_length < 3:
        errors.append({"field": "workspace_slug", "reason": "field_too_short"})

    if slug_length > 80:
        errors.append({"field": "workspace_slug", "reason": "field_too_long"})

    # Character pattern: only [a-z0-9-]
    if not re.match(r"^[a-z0-9-]+$", normalized):
        errors.append({"field": "workspace_slug", "reason": "invalid_characters"})

    # No leading hyphen
    if normalized.startswith("-"):
        errors.append({"field": "workspace_slug", "reason": "invalid_format"})

    # No trailing hyphen
    if normalized.endswith("-"):
        errors.append({"field": "workspace_slug", "reason": "invalid_format"})

    # No consecutive hyphens
    if "--" in normalized:
        errors.append({"field": "workspace_slug", "reason": "invalid_format"})

    return normalized


def validate_description(raw_value: Any, errors: list[dict[str, str]]) -> str | None:
    """
    Validate and normalize description field.

    Description is optional. None or empty string are both valid (treated as NULL).

    Args:
        raw_value: Raw description value from payload
        errors: List to append validation errors to

    Returns:
        Trimmed description or None if empty/None
    """
    # None or empty string are valid (optional field)
    if raw_value is None or raw_value == "":
        return None

    if not isinstance(raw_value, str):
        errors.append({"field": "description", "reason": "invalid_field_type"})
        return None

    # Apply trim
    trimmed = raw_value.strip()

    # Empty after trim is valid
    if trimmed == "":
        return None

    # Length check
    code_point_count = get_unicode_code_point_count(trimmed)

    if code_point_count > 500:
        errors.append({"field": "description", "reason": "field_too_long"})

    # Character restrictions
    if contains_ascii_control_characters(trimmed):
        errors.append({"field": "description", "reason": "invalid_characters"})

    return trimmed


def validate_default_timezone(raw_value: Any, errors: list[dict[str, str]]) -> str | None:
    """
    Validate and resolve default_timezone field.

    Empty string "" is explicitly rejected (not treated as None).
    None is valid (service layer will apply UTC default).

    Args:
        raw_value: Raw timezone value from payload
        errors: List to append validation errors to

    Returns:
        Canonical IANA timezone identifier or None
    """
    # None is valid (service will default to UTC)
    if raw_value is None:
        return None

    if not isinstance(raw_value, str):
        errors.append({"field": "default_timezone", "reason": "invalid_field_type"})
        return None

    # Empty string is explicitly rejected
    if raw_value == "":
        errors.append({"field": "default_timezone", "reason": "invalid_timezone"})
        return None

    # Resolve to canonical IANA form
    canonical = resolve_iana_timezone(raw_value)

    if canonical is None:
        errors.append({"field": "default_timezone", "reason": "invalid_timezone"})
        return None

    return canonical


def validate_status_reason(raw_value: Any, errors: list[dict[str, str]]) -> str | None:
    """
    Validate and normalize status_reason field for archival.

    Required for archival operations. Must be non-empty and at least 10 code points after trim.

    Args:
        raw_value: Raw status reason value from payload
        errors: List to append validation errors to

    Returns:
        Normalized status reason if valid, or None
    """
    if raw_value is None:
        errors.append({"field": "status_reason", "reason": "missing_reason"})
        return None

    if not isinstance(raw_value, str):
        errors.append({"field": "status_reason", "reason": "invalid_field_type"})
        return None

    # Apply normalization (trim)
    normalized = normalize_status_reason(raw_value)

    # Check if empty or whitespace-only
    if normalized == "":
        errors.append({"field": "status_reason", "reason": "missing_reason"})
        return None

    # Length checks (after trim)
    code_point_count = get_unicode_code_point_count(normalized)

    if code_point_count < 10:
        errors.append({"field": "status_reason", "reason": "reason_too_short"})

    if code_point_count > 500:
        errors.append({"field": "status_reason", "reason": "field_too_long"})

    # Character restrictions
    if contains_ascii_control_characters(normalized):
        errors.append({"field": "status_reason", "reason": "invalid_characters"})

    return normalized


# ============================================================================
# Field Detection Helpers
# ============================================================================


def detect_forbidden_fields(raw_payload: dict[str, Any], forbidden_set: set[str]) -> list[str]:
    """
    Detect forbidden fields in payload.

    Args:
        raw_payload: Request payload
        forbidden_set: Set of forbidden field names

    Returns:
        List of detected forbidden field names
    """
    return [field for field in raw_payload.keys() if field in forbidden_set]


def detect_unknown_fields(raw_payload: dict[str, Any], allowed_set: set[str]) -> list[str]:
    """
    Detect unknown fields in payload.

    Args:
        raw_payload: Request payload
        allowed_set: Set of allowed field names

    Returns:
        List of detected unknown field names
    """
    return [field for field in raw_payload.keys() if field not in allowed_set]


# ============================================================================
# Multi-Field Entry Points
# ============================================================================

# Forbidden fields for all endpoints (system-managed fields)
FORBIDDEN_FIELDS = {
    "tenant_id",
    "workspace_id",
    "created_by",
    "created_at",
    "updated_by",
    "updated_at",
    "status",
    "version",
    "workspace_name_lower",
}

# Allowed fields per endpoint
CREATE_ALLOWED_FIELDS = {"workspace_name", "workspace_slug", "description", "default_timezone"}

UPDATE_ALLOWED_FIELDS = {"workspace_name", "description", "default_timezone"}

# workspace_slug is always immutable in updates (checked separately)
IMMUTABLE_FIELDS = {"workspace_slug"}

ARCHIVE_ALLOWED_FIELDS = {"status_reason", "confirm_last_workspace"}


def validate_create_payload(raw_payload: dict[str, Any]) -> ValidationResult:
    """
    Validate create workspace payload.

    Steps:
    1. Detect forbidden fields
    2. Detect unknown fields
    3. Validate all required and optional fields
    4. Accumulate all errors

    Args:
        raw_payload: Raw request payload

    Returns:
        ValidationResult with errors and normalized payload
    """
    result = ValidationResult()

    # Detect forbidden fields
    forbidden = detect_forbidden_fields(raw_payload, FORBIDDEN_FIELDS)
    for field_name in forbidden:
        result.errors.append({"field": field_name, "reason": "forbidden_field"})

    # Detect unknown fields
    unknown = detect_unknown_fields(raw_payload, CREATE_ALLOWED_FIELDS)
    for field_name in unknown:
        result.errors.append({"field": field_name, "reason": "unknown_field"})

    # If forbidden or unknown fields detected, stop here (HTTP 400)
    if forbidden or unknown:
        return result

    # Validate individual fields (accumulate all errors)
    normalized_name = validate_workspace_name(raw_payload.get("workspace_name"), result.errors)

    normalized_slug = validate_workspace_slug(raw_payload.get("workspace_slug"), result.errors)

    normalized_description = validate_description(raw_payload.get("description"), result.errors)

    normalized_timezone = validate_default_timezone(
        raw_payload.get("default_timezone"), result.errors
    )

    # Build normalized payload
    if normalized_name is not None:
        result.normalized_payload["workspace_name"] = normalized_name

    if normalized_slug is not None:
        result.normalized_payload["workspace_slug"] = normalized_slug

    if normalized_description is not None:
        result.normalized_payload["description"] = normalized_description

    # Timezone: if None submitted, service layer applies UTC default
    # If canonical resolved, use it
    if normalized_timezone is not None:
        result.normalized_payload["default_timezone"] = normalized_timezone
    elif raw_payload.get("default_timezone") is None:
        # Explicitly None from payload, will use service default
        pass

    return result


def validate_update_payload(raw_payload: dict[str, Any]) -> ValidationResult:
    """
    Validate update workspace payload.

    Steps:
    1. Detect immutable field (workspace_slug) -> immutable_field error (HTTP 422)
    2. Detect forbidden fields -> forbidden_field error (HTTP 400)
    3. Detect unknown fields -> unknown_field error (HTTP 400)
    4. Validate submitted editable fields
    5. Empty payload {} is valid (returns zero errors)

    Args:
        raw_payload: Raw request payload

    Returns:
        ValidationResult with errors and normalized payload
    """
    result = ValidationResult()

    # Detect immutable fields (HTTP 422)
    immutable = [field for field in raw_payload.keys() if field in IMMUTABLE_FIELDS]
    for field_name in immutable:
        result.errors.append({"field": field_name, "reason": "immutable_field"})

    # Detect forbidden fields (HTTP 400)
    forbidden = detect_forbidden_fields(raw_payload, FORBIDDEN_FIELDS)
    for field_name in forbidden:
        result.errors.append({"field": field_name, "reason": "forbidden_field"})

    # Detect unknown fields (HTTP 400)
    # Allowed fields for update: workspace_name, description, default_timezone
    # workspace_slug is NOT in allowed set (it's immutable, handled separately)
    allowed_with_immutable = UPDATE_ALLOWED_FIELDS | IMMUTABLE_FIELDS
    unknown = detect_unknown_fields(raw_payload, allowed_with_immutable)
    for field_name in unknown:
        result.errors.append({"field": field_name, "reason": "unknown_field"})

    # If immutable, forbidden, or unknown fields detected, stop here
    if immutable or forbidden or unknown:
        return result

    # Empty payload is valid (no-op detection is service layer responsibility)
    if not raw_payload:
        return result

    # Validate submitted editable fields (only fields present in payload)
    if "workspace_name" in raw_payload:
        normalized_name = validate_workspace_name(raw_payload["workspace_name"], result.errors)
        if normalized_name is not None:
            result.normalized_payload["workspace_name"] = normalized_name

    if "description" in raw_payload:
        normalized_description = validate_description(raw_payload["description"], result.errors)
        # Description can be None (cleared field)
        result.normalized_payload["description"] = normalized_description

    if "default_timezone" in raw_payload:
        normalized_timezone = validate_default_timezone(
            raw_payload["default_timezone"], result.errors
        )
        if normalized_timezone is not None:
            result.normalized_payload["default_timezone"] = normalized_timezone

    return result


def validate_archive_payload(raw_payload: dict[str, Any]) -> ValidationResult:
    """
    Validate archive workspace payload.

    Steps:
    1. Detect unknown fields
    2. Validate confirm_last_workspace type (must be JSON boolean if present)
    3. Validate status_reason (required)

    Args:
        raw_payload: Raw request payload

    Returns:
        ValidationResult with errors and normalized payload
    """
    result = ValidationResult()

    # Detect unknown fields
    unknown = detect_unknown_fields(raw_payload, ARCHIVE_ALLOWED_FIELDS)
    for field_name in unknown:
        result.errors.append({"field": field_name, "reason": "unknown_field"})

    # If unknown fields detected, stop here
    if unknown:
        return result

    # Validate confirm_last_workspace type (must be boolean if present)
    if "confirm_last_workspace" in raw_payload:
        confirm_value = raw_payload["confirm_last_workspace"]
        if not isinstance(confirm_value, bool):
            result.errors.append(
                {"field": "confirm_last_workspace", "reason": "invalid_field_type"}
            )

    # Validate status_reason (required)
    normalized_reason = validate_status_reason(raw_payload.get("status_reason"), result.errors)

    if normalized_reason is not None:
        result.normalized_payload["status_reason"] = normalized_reason

    # Pass through confirm_last_workspace if present and valid
    if "confirm_last_workspace" in raw_payload and isinstance(
        raw_payload["confirm_last_workspace"], bool
    ):
        result.normalized_payload["confirm_last_workspace"] = raw_payload["confirm_last_workspace"]

    return result
