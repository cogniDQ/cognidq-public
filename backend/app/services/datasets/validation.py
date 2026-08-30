"""
F005 — Pure validation layer for Dataset operations
======================================================

All functions are database-free and I/O-free. They accept raw Python
values and return lists of field-level error dicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.datasets.models import (
    IMMUTABLE_DATASET_FIELDS,
    Criticality,
    DatasetType,
    SensitivityClassification,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_MAX_DATASET_NAME_LEN = 200
_MAX_PHYSICAL_ID_LEN = 500
_MAX_DESCRIPTION_LEN = 1000
_MAX_BUSINESS_DOMAIN_LEN = 100
_MAX_FRESHNESS_LEN = 200
_MAX_SCHEMA_NAME_LEN = 200
_MAX_FIELD_NAME_LEN = 200
_MAX_DATA_TYPE_LEN = 100
_MAX_BUSINESS_DEFINITION_LEN = 1000
_MAX_BULK_IMPORT_FIELDS = 500

VALID_DATASET_TYPES = frozenset(e.value for e in DatasetType)
VALID_CRITICALITIES = frozenset(e.value for e in Criticality)
VALID_SENSITIVITIES = frozenset(e.value for e in SensitivityClassification)
VALID_SORT_COLUMNS = frozenset(
    {
        "created_at",
        "updated_at",
        "dataset_name",
        "status",
        "dataset_type",
        "criticality",
        "business_domain",
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    errors: list[dict[str, str]]

    @property
    def is_valid(self) -> bool:
        return not self.errors


# ─────────────────────────────────────────────────────────────────────────────
# Individual field validators
# ─────────────────────────────────────────────────────────────────────────────


def validate_dataset_name(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, str):
        return [{"field": "dataset_name", "message": "Must be a string."}]
    stripped = value.strip()
    if not stripped:
        return [{"field": "dataset_name", "message": "Cannot be empty."}]
    if len(stripped) > _MAX_DATASET_NAME_LEN:
        return [
            {
                "field": "dataset_name",
                "message": f"Exceeds maximum length of {_MAX_DATASET_NAME_LEN} characters.",
            }
        ]
    return []


def validate_physical_identifier(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, str):
        return [{"field": "physical_identifier", "message": "Must be a string."}]
    stripped = value.strip()
    if not stripped:
        return [{"field": "physical_identifier", "message": "Cannot be empty."}]
    if len(stripped) > _MAX_PHYSICAL_ID_LEN:
        return [
            {
                "field": "physical_identifier",
                "message": f"Exceeds maximum length of {_MAX_PHYSICAL_ID_LEN} characters.",
            }
        ]
    return []


def validate_description(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, str):
        return [{"field": "description", "message": "Must be a string."}]
    if len(value) > _MAX_DESCRIPTION_LEN:
        return [
            {
                "field": "description",
                "message": f"Exceeds maximum length of {_MAX_DESCRIPTION_LEN} characters.",
            }
        ]
    return []


def validate_business_domain(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, str):
        return [{"field": "business_domain", "message": "Must be a string."}]
    if len(value) > _MAX_BUSINESS_DOMAIN_LEN:
        return [
            {
                "field": "business_domain",
                "message": f"Exceeds maximum length of {_MAX_BUSINESS_DOMAIN_LEN} characters.",
            }
        ]
    return []


def validate_freshness_expectation(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, str):
        return [{"field": "freshness_expectation", "message": "Must be a string."}]
    if len(value) > _MAX_FRESHNESS_LEN:
        return [
            {
                "field": "freshness_expectation",
                "message": f"Exceeds maximum length of {_MAX_FRESHNESS_LEN} characters.",
            }
        ]
    return []


def validate_schema_name(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, str):
        return [{"field": "schema_name", "message": "Must be a string."}]
    if len(value) > _MAX_SCHEMA_NAME_LEN:
        return [
            {
                "field": "schema_name",
                "message": f"Exceeds maximum length of {_MAX_SCHEMA_NAME_LEN} characters.",
            }
        ]
    return []


def validate_dataset_type(value: Any) -> list[dict[str, str]]:
    if value not in VALID_DATASET_TYPES:
        return [
            {"field": "dataset_type", "message": f"Must be one of: {sorted(VALID_DATASET_TYPES)}."}
        ]
    return []


def validate_criticality(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if value not in VALID_CRITICALITIES:
        return [
            {"field": "criticality", "message": f"Must be one of: {sorted(VALID_CRITICALITIES)}."}
        ]
    return []


def validate_sensitivity(value: Any) -> list[dict[str, str]]:
    if value not in VALID_SENSITIVITIES:
        return [
            {
                "field": "sensitivity_classification",
                "message": f"Must be one of: {sorted(VALID_SENSITIVITIES)}.",
            }
        ]
    return []


# ─── Field-level validators ────────────────────────────────────────────────


def validate_field_name(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, str):
        return [{"field": "field_name", "message": "Must be a string."}]
    stripped = value.strip()
    if not stripped:
        return [{"field": "field_name", "message": "Cannot be empty."}]
    if len(stripped) > _MAX_FIELD_NAME_LEN:
        return [
            {
                "field": "field_name",
                "message": f"Exceeds maximum length of {_MAX_FIELD_NAME_LEN} characters.",
            }
        ]
    return []


def validate_data_type(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, str):
        return [{"field": "data_type", "message": "Must be a string."}]
    stripped = value.strip()
    if not stripped:
        return [{"field": "data_type", "message": "Cannot be empty."}]
    if len(stripped) > _MAX_DATA_TYPE_LEN:
        return [
            {
                "field": "data_type",
                "message": f"Exceeds maximum length of {_MAX_DATA_TYPE_LEN} characters.",
            }
        ]
    return []


def validate_business_definition(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, str):
        return [{"field": "business_definition", "message": "Must be a string."}]
    if len(value) > _MAX_BUSINESS_DEFINITION_LEN:
        return [
            {
                "field": "business_definition",
                "message": f"Exceeds maximum length of {_MAX_BUSINESS_DEFINITION_LEN} characters.",
            }
        ]
    return []


# ─── Composite validators ──────────────────────────────────────────────────


def validate_create_dataset_payload(payload: dict[str, Any]) -> ValidationResult:
    errors: list[dict[str, str]] = []
    errors.extend(validate_dataset_name(payload.get("dataset_name", "")))
    errors.extend(validate_dataset_type(payload.get("dataset_type", "")))
    errors.extend(validate_physical_identifier(payload.get("physical_identifier", "")))
    errors.extend(validate_schema_name(payload.get("schema_name")))
    errors.extend(validate_description(payload.get("description")))
    errors.extend(validate_business_domain(payload.get("business_domain")))
    errors.extend(validate_criticality(payload.get("criticality", "low")))
    errors.extend(validate_freshness_expectation(payload.get("freshness_expectation")))
    return ValidationResult(errors=errors)


def validate_update_dataset_payload(payload: dict[str, Any]) -> ValidationResult:
    errors: list[dict[str, str]] = []
    # Reject immutable fields
    for field_name in IMMUTABLE_DATASET_FIELDS:
        if field_name in payload:
            errors.append(
                {
                    "field": field_name,
                    "message": f"'{field_name}' cannot be changed after creation.",
                }
            )
    if "dataset_name" in payload:
        errors.extend(validate_dataset_name(payload["dataset_name"]))
    if "description" in payload:
        errors.extend(validate_description(payload["description"]))
    if "business_domain" in payload:
        errors.extend(validate_business_domain(payload["business_domain"]))
    if "criticality" in payload:
        errors.extend(validate_criticality(payload["criticality"]))
    if "freshness_expectation" in payload:
        errors.extend(validate_freshness_expectation(payload["freshness_expectation"]))
    if "schema_name" in payload:
        errors.extend(validate_schema_name(payload["schema_name"]))
    return ValidationResult(errors=errors)


def validate_create_field_payload(payload: dict[str, Any]) -> ValidationResult:
    errors: list[dict[str, str]] = []
    errors.extend(validate_field_name(payload.get("field_name", "")))
    errors.extend(validate_data_type(payload.get("data_type", "")))
    errors.extend(validate_business_definition(payload.get("business_definition")))
    sc = payload.get("sensitivity_classification", "internal")
    errors.extend(validate_sensitivity(sc))
    return ValidationResult(errors=errors)


def validate_update_field_payload(payload: dict[str, Any]) -> ValidationResult:
    errors: list[dict[str, str]] = []
    if "field_name" in payload:
        errors.append(
            {
                "field": "field_name",
                "message": "'field_name' cannot be changed after creation.",
            }
        )
    if "data_type" in payload and payload["data_type"] is not None:
        errors.extend(validate_data_type(payload["data_type"]))
    if "business_definition" in payload:
        errors.extend(validate_business_definition(payload["business_definition"]))
    if (
        "sensitivity_classification" in payload
        and payload["sensitivity_classification"] is not None
    ):
        errors.extend(validate_sensitivity(payload["sensitivity_classification"]))
    return ValidationResult(errors=errors)


def validate_bulk_import_fields(
    fields: list[dict[str, Any]],
    mode: str,
) -> ValidationResult:
    errors: list[dict[str, str]] = []
    if mode not in ("append", "replace"):
        errors.append({"field": "mode", "message": "Must be 'append' or 'replace'."})
    if not fields:
        errors.append({"field": "fields", "message": "Field list cannot be empty."})
        return ValidationResult(errors=errors)
    if len(fields) > _MAX_BULK_IMPORT_FIELDS:
        errors.append(
            {
                "field": "fields",
                "message": f"Cannot import more than {_MAX_BULK_IMPORT_FIELDS} fields at once.",
            }
        )
        return ValidationResult(errors=errors)
    # Check for duplicate names within the batch
    seen_names: set = set()
    for i, f in enumerate(fields):
        name = f.get("field_name", "")
        if isinstance(name, str):
            lower_name = name.strip().lower()
            if lower_name in seen_names:
                errors.append(
                    {
                        "field": f"fields[{i}].field_name",
                        "message": f"Duplicate field name '{name}' in batch.",
                    }
                )
            seen_names.add(lower_name)
        # Validate each field
        result = validate_create_field_payload(f)
        for err in result.errors:
            errors.append(
                {
                    "field": f"fields[{i}].{err['field']}",
                    "message": err["message"],
                }
            )
    return ValidationResult(errors=errors)
