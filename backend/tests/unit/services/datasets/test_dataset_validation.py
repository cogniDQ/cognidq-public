"""
Unit tests — F005 P02: Dataset Validation Layer

Tests every validation function in datasets.validation without any
database or I/O.

Test IDs: VAL-01 through VAL-15
"""

import pytest
from app.services.datasets.validation import (
    ValidationResult,
    validate_bulk_import_fields,
    validate_business_definition,
    validate_business_domain,
    validate_create_dataset_payload,
    validate_create_field_payload,
    validate_criticality,
    validate_data_type,
    validate_dataset_name,
    validate_dataset_type,
    validate_description,
    validate_field_name,
    validate_freshness_expectation,
    validate_physical_identifier,
    validate_schema_name,
    validate_sensitivity,
    validate_update_dataset_payload,
    validate_update_field_payload,
)

# ─────────────────────────────────────────────────────────────────────────────
# VAL-01: validate_dataset_name
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateDatasetName:
    """VAL-01"""

    def test_valid_name(self):
        assert validate_dataset_name("orders_fact") == []

    def test_name_with_whitespace(self):
        assert validate_dataset_name("  my dataset  ") == []

    def test_empty_string_rejected(self):
        errors = validate_dataset_name("")
        assert any(e["field"] == "dataset_name" for e in errors)

    def test_whitespace_only_rejected(self):
        errors = validate_dataset_name("   ")
        assert any(e["field"] == "dataset_name" for e in errors)

    def test_max_200_chars_accepted(self):
        assert validate_dataset_name("x" * 200) == []

    def test_201_chars_rejected(self):
        errors = validate_dataset_name("x" * 201)
        assert any(e["field"] == "dataset_name" for e in errors)

    def test_non_string_rejected(self):
        errors = validate_dataset_name(123)
        assert any(e["field"] == "dataset_name" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-02: validate_physical_identifier
# ─────────────────────────────────────────────────────────────────────────────


class TestValidatePhysicalIdentifier:
    """VAL-02"""

    def test_valid_identifier(self):
        assert validate_physical_identifier("public.orders") == []

    def test_empty_rejected(self):
        errors = validate_physical_identifier("")
        assert any(e["field"] == "physical_identifier" for e in errors)

    def test_max_500_accepted(self):
        assert validate_physical_identifier("x" * 500) == []

    def test_501_rejected(self):
        errors = validate_physical_identifier("x" * 501)
        assert any(e["field"] == "physical_identifier" for e in errors)

    def test_non_string_rejected(self):
        errors = validate_physical_identifier(42)
        assert any(e["field"] == "physical_identifier" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-03: validate_description
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateDescription:
    """VAL-03"""

    def test_none_accepted(self):
        assert validate_description(None) == []

    def test_valid_string(self):
        assert validate_description("A dataset of orders.") == []

    def test_max_1000_accepted(self):
        assert validate_description("x" * 1000) == []

    def test_1001_rejected(self):
        errors = validate_description("x" * 1001)
        assert any(e["field"] == "description" for e in errors)

    def test_non_string_rejected(self):
        errors = validate_description(42)
        assert any(e["field"] == "description" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-04: validate_business_domain
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateBusinessDomain:
    """VAL-04"""

    def test_none_accepted(self):
        assert validate_business_domain(None) == []

    def test_valid_string(self):
        assert validate_business_domain("finance") == []

    def test_max_100_accepted(self):
        assert validate_business_domain("x" * 100) == []

    def test_101_rejected(self):
        errors = validate_business_domain("x" * 101)
        assert any(e["field"] == "business_domain" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-05: validate_freshness_expectation
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateFreshnessExpectation:
    """VAL-05"""

    def test_none_accepted(self):
        assert validate_freshness_expectation(None) == []

    def test_valid_string(self):
        assert validate_freshness_expectation("daily") == []

    def test_201_rejected(self):
        errors = validate_freshness_expectation("x" * 201)
        assert any(e["field"] == "freshness_expectation" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-06: validate_schema_name
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateSchemaName:
    """VAL-06"""

    def test_none_accepted(self):
        assert validate_schema_name(None) == []

    def test_valid_string(self):
        assert validate_schema_name("public") == []

    def test_201_rejected(self):
        errors = validate_schema_name("x" * 201)
        assert any(e["field"] == "schema_name" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-07: validate_dataset_type
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateDatasetType:
    """VAL-07"""

    def test_all_valid_types(self):
        for t in ("table", "view", "file", "logical"):
            assert validate_dataset_type(t) == []

    def test_invalid_rejected(self):
        errors = validate_dataset_type("stream")
        assert any(e["field"] == "dataset_type" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-08: validate_criticality
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateCriticality:
    """VAL-08"""

    def test_none_accepted(self):
        assert validate_criticality(None) == []

    def test_all_valid(self):
        for c in ("low", "medium", "high", "critical"):
            assert validate_criticality(c) == []

    def test_invalid_rejected(self):
        errors = validate_criticality("extreme")
        assert any(e["field"] == "criticality" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-09: validate_sensitivity
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateSensitivity:
    """VAL-09"""

    def test_all_valid(self):
        for s in ("public", "internal", "confidential", "restricted"):
            assert validate_sensitivity(s) == []

    def test_invalid_rejected(self):
        errors = validate_sensitivity("secret")
        assert any(e["field"] == "sensitivity_classification" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-10: validate_field_name / validate_data_type / validate_business_definition
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldLevelValidators:
    """VAL-10"""

    def test_valid_field_name(self):
        assert validate_field_name("order_id") == []

    def test_empty_field_name_rejected(self):
        errors = validate_field_name("")
        assert any(e["field"] == "field_name" for e in errors)

    def test_field_name_max_200(self):
        assert validate_field_name("x" * 200) == []
        errors = validate_field_name("x" * 201)
        assert any(e["field"] == "field_name" for e in errors)

    def test_valid_data_type(self):
        assert validate_data_type("varchar(50)") == []

    def test_empty_data_type_rejected(self):
        errors = validate_data_type("")
        assert any(e["field"] == "data_type" for e in errors)

    def test_data_type_max_100(self):
        assert validate_data_type("x" * 100) == []
        errors = validate_data_type("x" * 101)
        assert any(e["field"] == "data_type" for e in errors)

    def test_business_definition_none_accepted(self):
        assert validate_business_definition(None) == []

    def test_business_definition_max_1000(self):
        assert validate_business_definition("x" * 1000) == []
        errors = validate_business_definition("x" * 1001)
        assert any(e["field"] == "business_definition" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-11: validate_create_dataset_payload — composite
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateCreateDatasetPayload:
    """VAL-11"""

    def _valid_payload(self):
        return {
            "dataset_name": "orders_fact",
            "dataset_type": "table",
            "physical_identifier": "public.orders",
            "data_source_id": "some-uuid",
            "criticality": "medium",
        }

    def test_valid_payload_passes(self):
        result = validate_create_dataset_payload(self._valid_payload())
        assert result.is_valid

    def test_empty_name_caught(self):
        p = self._valid_payload()
        p["dataset_name"] = ""
        result = validate_create_dataset_payload(p)
        assert not result.is_valid
        assert any(e["field"] == "dataset_name" for e in result.errors)

    def test_invalid_type_caught(self):
        p = self._valid_payload()
        p["dataset_type"] = "stream"
        result = validate_create_dataset_payload(p)
        assert not result.is_valid

    def test_multiple_errors_accumulated(self):
        result = validate_create_dataset_payload(
            {
                "dataset_name": "",
                "dataset_type": "invalid",
                "physical_identifier": "",
            }
        )
        assert not result.is_valid
        fields = {e["field"] for e in result.errors}
        assert len(fields) >= 3


# ─────────────────────────────────────────────────────────────────────────────
# VAL-12: validate_update_dataset_payload — immutable field check
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateUpdateDatasetPayload:
    """VAL-12"""

    def test_valid_update(self):
        result = validate_update_dataset_payload({"dataset_name": "new-name"})
        assert result.is_valid

    def test_immutable_dataset_type_rejected(self):
        result = validate_update_dataset_payload({"dataset_type": "view"})
        assert not result.is_valid
        assert any("dataset_type" in e["field"] for e in result.errors)

    def test_immutable_data_source_id_rejected(self):
        result = validate_update_dataset_payload({"data_source_id": "abc"})
        assert not result.is_valid

    def test_immutable_physical_identifier_rejected(self):
        result = validate_update_dataset_payload({"physical_identifier": "new.table"})
        assert not result.is_valid


# ─────────────────────────────────────────────────────────────────────────────
# VAL-13: validate_create_field_payload
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateCreateFieldPayload:
    """VAL-13"""

    def test_valid_payload(self):
        result = validate_create_field_payload(
            {
                "field_name": "order_id",
                "data_type": "bigint",
            }
        )
        assert result.is_valid

    def test_empty_field_name(self):
        result = validate_create_field_payload(
            {
                "field_name": "",
                "data_type": "bigint",
            }
        )
        assert not result.is_valid

    def test_empty_data_type(self):
        result = validate_create_field_payload(
            {
                "field_name": "col1",
                "data_type": "",
            }
        )
        assert not result.is_valid


# ─────────────────────────────────────────────────────────────────────────────
# VAL-14: validate_update_field_payload
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateUpdateFieldPayload:
    """VAL-14"""

    def test_valid_update(self):
        result = validate_update_field_payload({"data_type": "bigint"})
        assert result.is_valid

    def test_field_name_immutable(self):
        result = validate_update_field_payload({"field_name": "new_name"})
        assert not result.is_valid
        assert any("field_name" in e["field"] for e in result.errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-15: validate_bulk_import_fields
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateBulkImportFields:
    """VAL-15"""

    def test_valid_batch(self):
        fields = [
            {"field_name": "col1", "data_type": "int"},
            {"field_name": "col2", "data_type": "varchar"},
        ]
        result = validate_bulk_import_fields(fields, mode="append")
        assert result.is_valid

    def test_empty_list_rejected(self):
        result = validate_bulk_import_fields([], mode="append")
        assert not result.is_valid
        assert any(e["field"] == "fields" for e in result.errors)

    def test_invalid_mode_rejected(self):
        result = validate_bulk_import_fields(
            [{"field_name": "c1", "data_type": "int"}],
            mode="overwrite",
        )
        assert not result.is_valid
        assert any(e["field"] == "mode" for e in result.errors)

    def test_duplicate_names_rejected(self):
        fields = [
            {"field_name": "col1", "data_type": "int"},
            {"field_name": "Col1", "data_type": "varchar"},
        ]
        result = validate_bulk_import_fields(fields, mode="append")
        assert not result.is_valid
        assert any("Duplicate" in e["message"] for e in result.errors)

    def test_over_500_fields_rejected(self):
        fields = [{"field_name": f"c{i}", "data_type": "int"} for i in range(501)]
        result = validate_bulk_import_fields(fields, mode="replace")
        assert not result.is_valid
        assert any("500" in e["message"] for e in result.errors)

    def test_per_field_validation_errors(self):
        fields = [
            {"field_name": "", "data_type": "int"},
        ]
        result = validate_bulk_import_fields(fields, mode="append")
        assert not result.is_valid
        assert any("fields[0]" in e["field"] for e in result.errors)

    def test_replace_mode_accepted(self):
        fields = [{"field_name": "a", "data_type": "int"}]
        result = validate_bulk_import_fields(fields, mode="replace")
        assert result.is_valid
