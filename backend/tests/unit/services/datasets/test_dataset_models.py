"""
Unit tests — F005 P02: Dataset Domain Models

Tests that enums, dataclasses, and constants are defined correctly.

Test IDs: MDL-01 through MDL-05
"""

from datetime import UTC

import pytest
from app.services.datasets.models import (
    IMMUTABLE_DATASET_FIELDS,
    BulkImportResult,
    CreateDatasetPayload,
    CreateFieldPayload,
    Criticality,
    Dataset,
    DatasetField,
    DatasetListFilters,
    DatasetListItem,
    DatasetListResult,
    DatasetStatus,
    DatasetType,
    SensitivityClassification,
    UpdateDatasetPayload,
    UpdateFieldPayload,
)

# ─────────────────────────────────────────────────────────────────────────────
# MDL-01: Enum values
# ─────────────────────────────────────────────────────────────────────────────


class TestEnums:
    """MDL-01"""

    def test_dataset_status_values(self):
        assert set(DatasetStatus) == {
            DatasetStatus.draft,
            DatasetStatus.active,
            DatasetStatus.inactive,
            DatasetStatus.archived,
        }

    def test_dataset_type_values(self):
        assert set(DatasetType) == {
            DatasetType.table,
            DatasetType.view,
            DatasetType.file,
            DatasetType.logical,
        }

    def test_criticality_values(self):
        assert set(Criticality) == {
            Criticality.low,
            Criticality.medium,
            Criticality.high,
            Criticality.critical,
        }

    def test_sensitivity_values(self):
        assert set(SensitivityClassification) == {
            SensitivityClassification.public,
            SensitivityClassification.internal,
            SensitivityClassification.confidential,
            SensitivityClassification.restricted,
        }

    def test_enums_are_str(self):
        assert DatasetStatus.draft == "draft"
        assert DatasetType.table == "table"
        assert Criticality.low == "low"
        assert SensitivityClassification.internal == "internal"


# ─────────────────────────────────────────────────────────────────────────────
# MDL-02: Immutable fields constant
# ─────────────────────────────────────────────────────────────────────────────


class TestImmutableFields:
    """MDL-02"""

    def test_immutable_fields_content(self):
        assert IMMUTABLE_DATASET_FIELDS == frozenset(
            {
                "dataset_type",
                "data_source_id",
                "physical_identifier",
            }
        )

    def test_immutable_fields_is_frozenset(self):
        assert isinstance(IMMUTABLE_DATASET_FIELDS, frozenset)


# ─────────────────────────────────────────────────────────────────────────────
# MDL-03: Dataset defaults
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetDefaults:
    """MDL-03"""

    def test_default_status_is_draft(self):
        from datetime import datetime, timezone
        from uuid import uuid4

        ds = Dataset(
            workspace_id=uuid4(),
            tenant_id=uuid4(),
            data_source_id=uuid4(),
            dataset_name="test",
            dataset_type="table",
            physical_identifier="public.test",
            created_by=uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert ds.status == DatasetStatus.draft
        assert ds.criticality == "low"
        assert ds.dataset_id is None
        assert ds.archived_at is None


# ─────────────────────────────────────────────────────────────────────────────
# MDL-04: DatasetField defaults
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetFieldDefaults:
    """MDL-04"""

    def test_field_defaults(self):
        from datetime import datetime, timezone
        from uuid import uuid4

        f = DatasetField(
            dataset_id=uuid4(),
            field_name="col1",
            data_type="integer",
            ordinal_position=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert f.nullable is True
        assert f.sensitivity_classification == "internal"
        assert f.is_key_candidate is False
        assert f.field_id is None


# ─────────────────────────────────────────────────────────────────────────────
# MDL-05: DatasetListFilters defaults
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetListFiltersDefaults:
    """MDL-05"""

    def test_default_filters(self):
        f = DatasetListFilters()
        assert f.sort_by == "created_at"
        assert f.sort_order == "desc"
        assert f.limit == 20
        assert f.offset == 0
        assert f.status is None
        assert f.search is None
