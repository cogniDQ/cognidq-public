"""
F005 — Dataset domain models
===============================

Plain Python dataclasses used by every layer from repository to controller.
No database, HTTP, or I/O dependencies.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────


class DatasetStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    inactive = "inactive"
    archived = "archived"


class DatasetType(str, enum.Enum):
    table = "table"
    view = "view"
    file = "file"
    logical = "logical"


class Criticality(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class SensitivityClassification(str, enum.Enum):
    public = "public"
    internal = "internal"
    confidential = "confidential"
    restricted = "restricted"


IMMUTABLE_DATASET_FIELDS = frozenset({"dataset_type", "data_source_id", "physical_identifier"})


# ─────────────────────────────────────────────────────────────────────────────
# Domain models
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class Dataset:
    workspace_id: UUID
    tenant_id: UUID
    data_source_id: UUID | None
    dataset_name: str
    dataset_type: str
    physical_identifier: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    dataset_id: UUID | None = None
    schema_name: str | None = None
    description: str | None = None
    business_domain: str | None = None
    criticality: str = "low"
    owner_user_id: UUID | None = None
    freshness_expectation: str | None = None
    status: DatasetStatus = DatasetStatus.draft
    updated_by: UUID | None = None
    activated_at: datetime | None = None
    archived_at: datetime | None = None
    archived_by: UUID | None = None


@dataclass(slots=True)
class DatasetField:
    dataset_id: UUID
    field_name: str
    data_type: str
    ordinal_position: int
    created_at: datetime
    updated_at: datetime

    field_id: UUID | None = None
    nullable: bool = True
    business_definition: str | None = None
    sensitivity_classification: str = "internal"
    is_key_candidate: bool = False
    # E2 — candidate enrichment with table preview
    sample_values: list[str] = field(default_factory=list)
    sample_values_updated_at: datetime | None = None


@dataclass(slots=True)
class DatasetListItem:
    dataset_id: UUID
    workspace_id: UUID
    dataset_name: str
    dataset_type: str
    physical_identifier: str
    status: str
    business_domain: str | None
    criticality: str
    owner_user_id: UUID | None
    data_source_id: UUID | None
    data_source_name: str | None
    field_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class DatasetListResult:
    items: list[DatasetListItem]
    total_count: int
    limit: int
    offset: int


@dataclass(slots=True)
class CreateDatasetPayload:
    dataset_name: str
    dataset_type: str
    physical_identifier: str
    data_source_id: UUID | None = None
    schema_name: str | None = None
    description: str | None = None
    business_domain: str | None = None
    criticality: str = "low"
    owner_user_id: UUID | None = None
    freshness_expectation: str | None = None


@dataclass(slots=True)
class UpdateDatasetPayload:
    dataset_name: str | None = None
    description: str | None = None
    business_domain: str | None = None
    criticality: str | None = None
    owner_user_id: UUID | None = None
    freshness_expectation: str | None = None
    schema_name: str | None = None


@dataclass(slots=True)
class CreateFieldPayload:
    field_name: str
    data_type: str
    nullable: bool = True
    business_definition: str | None = None
    sensitivity_classification: str = "internal"
    is_key_candidate: bool = False


@dataclass(slots=True)
class UpdateFieldPayload:
    data_type: str | None = None
    nullable: bool | None = None
    business_definition: str | None = None
    sensitivity_classification: str | None = None
    is_key_candidate: bool | None = None
    ordinal_position: int | None = None


@dataclass(slots=True)
class DatasetListFilters:
    status: str | None = None
    data_source_id: UUID | None = None
    owner_user_id: UUID | None = None
    business_domain: str | None = None
    criticality: str | None = None
    dataset_type: str | None = None
    search: str | None = None
    sort_by: str = "created_at"
    sort_order: str = "desc"
    limit: int = 20
    offset: int = 0


@dataclass(slots=True)
class BulkImportResult:
    mode: str
    fields_added: int
    fields_removed: int
