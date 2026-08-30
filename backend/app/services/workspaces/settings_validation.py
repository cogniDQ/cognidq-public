"""
F003 — Pure validation layer for workspace settings
=====================================================

All functions are database-free and I/O-free.  They accept raw Python
dicts/strings as input (not domain model objects) and produce lists of
``FieldError`` objects or a ``ValidationResult``.

All validators **collect** all errors before returning (not fail-fast) so
that a single PATCH call can report every problem in one response.

Design notes
------------
* ``resolve_iana_timezone`` from ``validation.py`` is reused — not duplicated.
* Regex patterns are compiled via ``re.compile(pattern, re.UNICODE)`` solely
  to check compilability; the compiled pattern is discarded immediately.
* Label constraints: stripped length 1–50, no control characters.
* SLA hours: integer 1–8760 (inclusive).  Ordering: critical ≤ major ≤ minor.
* Naming fields: optional per-domain sub-objects; empty dict ``{}`` is valid
  (means "clear constraints for this domain").
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.services.workspaces.validation import resolve_iana_timezone

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

ALLOWED_GROUPING_MODES = frozenset(
    {
        "one_per_execution",
        "one_per_rule",
        "one_per_day",
    }
)

# Top-level PATCH body keys that are recognised policy fields.
RECOGNISED_POLICY_FIELDS = frozenset(
    {
        "timezone_policy",
        "severity_policy",
        "sla_policy",
        "issue_grouping_policy",
        "naming_standards",
        "llm_config",
        "incident_policy",
    }
)

_MAX_LABEL_LEN = 50
_MAX_HOURS = 8760  # 365 days
_MIN_HOURS = 1
_MAX_NAMING_PREFIX_LEN = 50
_MAX_NAMING_SUFFIX_LEN = 50
_MAX_NAMING_MAX_LENGTH = 500
_MIN_NAMING_MAX_LENGTH = 1


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class FieldError:
    """A single field-level validation error (TDD §4.2 error shape)."""

    field: str
    error_code: str
    message: str


@dataclass(slots=True, frozen=True)
class ValidationResult:
    """Aggregate result of ``validate_settings_update_payload``."""

    is_valid: bool
    errors: list[FieldError]


# ─────────────────────────────────────────────────────────────────────────────
# Body-level checks
# ─────────────────────────────────────────────────────────────────────────────


def detect_unknown_fields(body: dict) -> list[str]:
    """Return list of top-level keys in ``body`` not in RECOGNISED_POLICY_FIELDS."""
    return [k for k in body if k not in RECOGNISED_POLICY_FIELDS]


def is_empty_request(body: dict) -> bool:
    """Return True if ``body`` contains no recognised policy field."""
    return not any(k in RECOGNISED_POLICY_FIELDS for k in body)


# ─────────────────────────────────────────────────────────────────────────────
# Domain validators
# ─────────────────────────────────────────────────────────────────────────────


def validate_timezone_policy(value: dict) -> list[FieldError]:
    """Validate the ``timezone_policy`` sub-object from a PATCH body.

    ``value`` must be a dict with the key ``default_timezone``.
    Returns a list of ``FieldError`` (empty = valid).
    """
    errors: list[FieldError] = []
    tz_raw = value.get("default_timezone") if isinstance(value, dict) else None

    if tz_raw is None or (isinstance(tz_raw, str) and tz_raw.strip() == ""):
        errors.append(
            FieldError(
                field="timezone_policy.default_timezone",
                error_code="required_field",
                message="default_timezone is required and must not be empty or whitespace.",
            )
        )
        return errors

    if not isinstance(tz_raw, str):
        errors.append(
            FieldError(
                field="timezone_policy.default_timezone",
                error_code="invalid_field_type",
                message="default_timezone must be a string.",
            )
        )
        return errors

    canonical = resolve_iana_timezone(tz_raw)
    if canonical is None:
        errors.append(
            FieldError(
                field="timezone_policy.default_timezone",
                error_code="invalid_timezone",
                message=f"'{tz_raw}' is not a recognised IANA timezone identifier.",
            )
        )

    return errors


def _validate_label(value, field_path: str) -> FieldError | None:
    """Validate a single severity label value."""
    if not isinstance(value, str):
        return FieldError(
            field=field_path,
            error_code="invalid_field_type",
            message=f"{field_path} must be a string.",
        )
    stripped = value.strip()
    if len(stripped) == 0:
        return FieldError(
            field=field_path,
            error_code="invalid_label",
            message=f"{field_path} must not be empty or whitespace-only.",
        )
    if len(stripped) > _MAX_LABEL_LEN:
        return FieldError(
            field=field_path,
            error_code="invalid_label",
            message=f"{field_path} must not exceed {_MAX_LABEL_LEN} characters (got {len(stripped)}).",
        )
    # No control characters (newlines, tabs, etc.)
    if any(c in value for c in ("\n", "\r", "\t")):
        return FieldError(
            field=field_path,
            error_code="invalid_label",
            message=f"{field_path} must not contain control characters.",
        )
    return None


def validate_severity_policy(value: dict) -> list[FieldError]:
    """Validate the ``severity_policy`` dict from a PATCH body.

    All four label keys are required.  Each must be a non-empty string of
    1–50 stripped characters with no control characters.
    """
    errors: list[FieldError] = []
    if not isinstance(value, dict):
        errors.append(
            FieldError(
                field="severity_policy",
                error_code="invalid_field_type",
                message="severity_policy must be an object.",
            )
        )
        return errors

    required_keys = ["critical_label", "major_label", "minor_label", "informational_label"]
    missing = [k for k in required_keys if k not in value]
    if missing:
        errors.append(
            FieldError(
                field="severity_policy",
                error_code="incomplete_severity_policy",
                message=f"severity_policy is missing required field(s): {', '.join(missing)}.",
            )
        )
        return errors

    for key in required_keys:
        err = _validate_label(value[key], f"severity_policy.{key}")
        if err:
            errors.append(err)

    return errors


def _validate_hours(value, field_path: str, required: bool = True) -> FieldError | None:
    """Validate a single SLA hours integer value."""
    if value is None:
        if required:
            return FieldError(
                field=field_path,
                error_code="required_field",
                message=f"{field_path} is required.",
            )
        return None  # Optional and absent — OK
    if not isinstance(value, int) or isinstance(value, bool):
        return FieldError(
            field=field_path,
            error_code="invalid_sla_hours",
            message=f"{field_path} must be an integer.",
        )
    if value < _MIN_HOURS or value > _MAX_HOURS:
        return FieldError(
            field=field_path,
            error_code="invalid_sla_hours",
            message=f"{field_path} must be between {_MIN_HOURS} and {_MAX_HOURS} (got {value}).",
        )
    return None


def validate_sla_policy(value: dict) -> list[FieldError]:
    """Validate the ``sla_policy`` dict from a PATCH body.

    Required keys: ``critical_hours``, ``major_hours``, ``minor_hours``
    (each integer 1–8760).  ``informational_hours`` is optional (integer
    1–8760 or null/None).  Ordering: critical ≤ major ≤ minor.
    """
    errors: list[FieldError] = []
    if not isinstance(value, dict):
        errors.append(
            FieldError(
                field="sla_policy",
                error_code="invalid_field_type",
                message="sla_policy must be an object.",
            )
        )
        return errors

    required_keys = ["critical_hours", "major_hours", "minor_hours"]
    missing = [k for k in required_keys if k not in value]
    if missing:
        errors.append(
            FieldError(
                field="sla_policy",
                error_code="incomplete_sla_policy",
                message=f"sla_policy is missing required field(s): {', '.join(missing)}.",
            )
        )
        return errors

    for key in required_keys:
        err = _validate_hours(value[key], f"sla_policy.{key}", required=True)
        if err:
            errors.append(err)

    # Validate optional informational_hours (present key with None value is allowed)
    if "informational_hours" in value and value["informational_hours"] is not None:
        err = _validate_hours(
            value["informational_hours"], "sla_policy.informational_hours", required=False
        )
        if err:
            errors.append(err)

    # Cross-field ordering — only check if all required values were valid
    if not errors:
        c = value.get("critical_hours")
        m = value.get("major_hours")
        n = value.get("minor_hours")
        if isinstance(c, int) and isinstance(m, int) and isinstance(n, int):
            if c > m:
                errors.append(
                    FieldError(
                        field="sla_policy",
                        error_code="sla_ordering_violation",
                        message="critical_hours must be <= major_hours.",
                    )
                )
            elif m > n:
                errors.append(
                    FieldError(
                        field="sla_policy",
                        error_code="sla_ordering_violation",
                        message="major_hours must be <= minor_hours.",
                    )
                )

    return errors


def validate_issue_grouping_policy(value) -> list[FieldError]:
    """Validate ``issue_grouping_policy`` string value."""
    errors: list[FieldError] = []
    if not isinstance(value, str):
        errors.append(
            FieldError(
                field="issue_grouping_policy",
                error_code="invalid_field_type",
                message="issue_grouping_policy must be a string.",
            )
        )
        return errors
    if value not in ALLOWED_GROUPING_MODES:
        errors.append(
            FieldError(
                field="issue_grouping_policy",
                error_code="invalid_grouping_mode",
                message=(
                    f"'{value}' is not a valid grouping mode. "
                    f"Allowed values: {sorted(ALLOWED_GROUPING_MODES)}."
                ),
            )
        )
    return errors


# ─────────────────────────────────────────────────────────────────────────────
# LLM config
# ─────────────────────────────────────────────────────────────────────────────

_ALLOWED_LLM_PROVIDERS = frozenset({"openai", "azure_openai", "anthropic"})
_MAX_MODEL_LEN = 100
_MIN_TEMPERATURE = 0.0
_MAX_TEMPERATURE = 2.0
_MIN_MAX_TOKENS = 1
_MAX_MAX_TOKENS = 16000


def validate_llm_config(value: dict) -> list[FieldError]:
    """Validate the ``llm_config`` dict from a PATCH body."""
    errors: list[FieldError] = []
    if not isinstance(value, dict):
        errors.append(
            FieldError(
                field="llm_config",
                error_code="invalid_field_type",
                message="llm_config must be an object.",
            )
        )
        return errors

    # provider — required
    provider = value.get("provider")
    if not isinstance(provider, str) or provider not in _ALLOWED_LLM_PROVIDERS:
        errors.append(
            FieldError(
                field="llm_config.provider",
                error_code="invalid_llm_provider",
                message=f"provider must be one of {sorted(_ALLOWED_LLM_PROVIDERS)}.",
            )
        )

    # api_key — required, non-empty string
    api_key = value.get("api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        errors.append(
            FieldError(
                field="llm_config.api_key",
                error_code="invalid_api_key",
                message="api_key is required and must be a non-empty string.",
            )
        )

    # model — required, non-empty, max 100 chars
    model = value.get("model")
    if not isinstance(model, str) or not model.strip():
        errors.append(
            FieldError(
                field="llm_config.model",
                error_code="invalid_model",
                message="model is required and must be a non-empty string.",
            )
        )
    elif len(model) > _MAX_MODEL_LEN:
        errors.append(
            FieldError(
                field="llm_config.model",
                error_code="invalid_model",
                message=f"model must be at most {_MAX_MODEL_LEN} characters.",
            )
        )

    # temperature — optional, float 0.0–2.0
    if "temperature" in value and value["temperature"] is not None:
        temp = value["temperature"]
        if isinstance(temp, bool) or not isinstance(temp, (int, float)):
            errors.append(
                FieldError(
                    field="llm_config.temperature",
                    error_code="invalid_temperature",
                    message="temperature must be a number.",
                )
            )
        else:
            temp = float(temp)
            value["temperature"] = temp  # coerce in-place
            if temp < _MIN_TEMPERATURE or temp > _MAX_TEMPERATURE:
                errors.append(
                    FieldError(
                        field="llm_config.temperature",
                        error_code="invalid_temperature",
                        message=f"temperature must be between {_MIN_TEMPERATURE} and {_MAX_TEMPERATURE}.",
                    )
                )

    # max_tokens — optional, integer 1–16000 (accept float and coerce to int)
    if "max_tokens" in value and value["max_tokens"] is not None:
        mt = value["max_tokens"]
        if isinstance(mt, bool) or not isinstance(mt, (int, float)):
            errors.append(
                FieldError(
                    field="llm_config.max_tokens",
                    error_code="invalid_max_tokens",
                    message="max_tokens must be a number.",
                )
            )
        else:
            mt = int(mt)
            value["max_tokens"] = mt  # coerce in-place for downstream
            if mt < _MIN_MAX_TOKENS or mt > _MAX_MAX_TOKENS:
                errors.append(
                    FieldError(
                        field="llm_config.max_tokens",
                        error_code="invalid_max_tokens",
                        message=f"max_tokens must be between {_MIN_MAX_TOKENS} and {_MAX_MAX_TOKENS}.",
                    )
                )

    return errors


def _validate_naming_constraint(constraint: dict, domain: str) -> list[FieldError]:
    """Validate a single domain's naming constraint sub-object.

    Empty dict ``{}`` is valid — means no constraints for this domain.
    """
    errors: list[FieldError] = []
    prefix = f"naming_standards.{domain}"

    if not isinstance(constraint, dict):
        errors.append(
            FieldError(
                field=prefix,
                error_code="invalid_field_type",
                message=f"{prefix} must be an object.",
            )
        )
        return errors

    # required_prefix
    if "required_prefix" in constraint:
        v = constraint["required_prefix"]
        if not isinstance(v, str):
            errors.append(
                FieldError(
                    field=f"{prefix}.required_prefix",
                    error_code="invalid_field_type",
                    message=f"{prefix}.required_prefix must be a string.",
                )
            )
        elif v.strip() == "" or len(v.strip()) > _MAX_NAMING_PREFIX_LEN:
            errors.append(
                FieldError(
                    field=f"{prefix}.required_prefix",
                    error_code="invalid_prefix",
                    message=f"{prefix}.required_prefix must be 1–{_MAX_NAMING_PREFIX_LEN} characters (stripped).",
                )
            )

    # required_suffix
    if "required_suffix" in constraint:
        v = constraint["required_suffix"]
        if not isinstance(v, str):
            errors.append(
                FieldError(
                    field=f"{prefix}.required_suffix",
                    error_code="invalid_field_type",
                    message=f"{prefix}.required_suffix must be a string.",
                )
            )
        elif v.strip() == "" or len(v.strip()) > _MAX_NAMING_SUFFIX_LEN:
            errors.append(
                FieldError(
                    field=f"{prefix}.required_suffix",
                    error_code="invalid_suffix",
                    message=f"{prefix}.required_suffix must be 1–{_MAX_NAMING_SUFFIX_LEN} characters (stripped).",
                )
            )

    # pattern — must be a compilable regex
    if "pattern" in constraint:
        v = constraint["pattern"]
        if not isinstance(v, str):
            errors.append(
                FieldError(
                    field=f"{prefix}.pattern",
                    error_code="invalid_field_type",
                    message=f"{prefix}.pattern must be a string.",
                )
            )
        else:
            try:
                re.compile(v, re.UNICODE)
            except re.error:
                errors.append(
                    FieldError(
                        field=f"{prefix}.pattern",
                        error_code="invalid_pattern",
                        message=f"{prefix}.pattern is not a valid regular expression: {v!r}.",
                    )
                )

    # max_length — integer 1–500
    if "max_length" in constraint:
        v = constraint["max_length"]
        if isinstance(v, bool) or not isinstance(v, int):
            errors.append(
                FieldError(
                    field=f"{prefix}.max_length",
                    error_code="invalid_field_type",
                    message=f"{prefix}.max_length must be an integer.",
                )
            )
        elif v < _MIN_NAMING_MAX_LENGTH or v > _MAX_NAMING_MAX_LENGTH:
            errors.append(
                FieldError(
                    field=f"{prefix}.max_length",
                    error_code="invalid_max_length",
                    message=f"{prefix}.max_length must be between {_MIN_NAMING_MAX_LENGTH} and {_MAX_NAMING_MAX_LENGTH} (got {v}).",
                )
            )

    # allow_special_characters — boolean
    if "allow_special_characters" in constraint:
        v = constraint["allow_special_characters"]
        if not isinstance(v, bool):
            errors.append(
                FieldError(
                    field=f"{prefix}.allow_special_characters",
                    error_code="invalid_field_type",
                    message=f"{prefix}.allow_special_characters must be a boolean.",
                )
            )

    return errors


def validate_naming_standards(value: dict) -> list[FieldError]:
    """Validate the ``naming_standards`` dict from a PATCH body.

    ``datasets`` and ``rules`` sub-objects are independently optional.
    An empty sub-object ``{}`` is valid (means: clear constraints for domain).
    """
    errors: list[FieldError] = []
    if not isinstance(value, dict):
        errors.append(
            FieldError(
                field="naming_standards",
                error_code="invalid_field_type",
                message="naming_standards must be an object.",
            )
        )
        return errors

    if "datasets" in value:
        errors.extend(_validate_naming_constraint(value["datasets"], "datasets"))
    if "rules" in value:
        errors.extend(_validate_naming_constraint(value["rules"], "rules"))

    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def validate_settings_update_payload(body: dict) -> ValidationResult:
    """Validate the full PATCH /settings request body.

    Dispatches to all applicable domain validators and collects ALL errors
    before returning (not fail-fast).  The caller must check
    ``result.is_valid`` before proceeding.

    Does NOT check for unknown fields or empty request — those are checked
    earlier by the service layer using ``detect_unknown_fields`` and
    ``is_empty_request``.
    """
    errors: list[FieldError] = []

    if "timezone_policy" in body:
        errors.extend(validate_timezone_policy(body["timezone_policy"]))

    if "severity_policy" in body:
        errors.extend(validate_severity_policy(body["severity_policy"]))

    if "sla_policy" in body:
        errors.extend(validate_sla_policy(body["sla_policy"]))

    if "issue_grouping_policy" in body:
        errors.extend(validate_issue_grouping_policy(body["issue_grouping_policy"]))

    if "naming_standards" in body:
        errors.extend(validate_naming_standards(body["naming_standards"]))

    if "llm_config" in body:
        errors.extend(validate_llm_config(body["llm_config"]))

    return ValidationResult(is_valid=(len(errors) == 0), errors=errors)
