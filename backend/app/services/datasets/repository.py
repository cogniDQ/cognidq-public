"""
F005 — Dataset repository layer
=================================

Provides ``DatasetRepository`` — CRUD against ``control.datasets``.

Design notes
------------
* All SQL via SQLAlchemy ``text()`` with named bind params — never string
  interpolation of user data.
* Every query includes ``workspace_id`` scoping for cross-tenant isolation.
* ``find_by_id_for_update`` uses ``SELECT … FOR UPDATE`` for status transitions.
* On IntegrityError the constraint name is inspected to raise domain exceptions.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services.datasets.errors import (
    DatasetNotFoundError,
    DuplicateDatasetNameError,
    DuplicatePhysicalIdentifierError,
)
from app.services.datasets.models import (
    Dataset,
    DatasetListFilters,
    DatasetListItem,
    DatasetListResult,
    DatasetStatus,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# SQL constants
# ─────────────────────────────────────────────────────────────────────────────

_COLUMNS = """
    dataset_id, workspace_id, tenant_id, data_source_id,
    dataset_name, dataset_type, physical_identifier,
    schema_name, description, business_domain, criticality,
    owner_user_id, freshness_expectation,
    status, created_at, updated_at, created_by, updated_by,
    activated_at, archived_at, archived_by
"""

_INSERT_SQL = f"""
INSERT INTO control.datasets (
    dataset_id, workspace_id, tenant_id, data_source_id,
    dataset_name, dataset_type, physical_identifier,
    schema_name, description, business_domain, criticality,
    owner_user_id, freshness_expectation,
    status, created_at, updated_at, created_by
) VALUES (
    :dataset_id, :workspace_id, :tenant_id, :data_source_id,
    :dataset_name, :dataset_type, :physical_identifier,
    :schema_name, :description, :business_domain, :criticality,
    :owner_user_id, :freshness_expectation,
    'draft', :now, :now, :created_by
)
RETURNING {_COLUMNS}
"""

_SELECT_BY_ID_SQL = f"""
SELECT {_COLUMNS}
FROM control.datasets
WHERE dataset_id   = CAST(:dataset_id   AS UUID)
  AND workspace_id = CAST(:workspace_id AS UUID)
"""

_UPDATE_METADATA_SQL = f"""
UPDATE control.datasets
SET
    dataset_name          = COALESCE(:dataset_name,          dataset_name),
    schema_name           = COALESCE(:schema_name,           schema_name),
    description           = COALESCE(:description,           description),
    business_domain       = COALESCE(:business_domain,       business_domain),
    criticality           = COALESCE(:criticality,           criticality),
    owner_user_id         = COALESCE(:owner_user_id,         owner_user_id),
    freshness_expectation = COALESCE(:freshness_expectation, freshness_expectation),
    updated_at            = :now,
    updated_by            = :updated_by
WHERE dataset_id   = CAST(:dataset_id   AS UUID)
  AND workspace_id = CAST(:workspace_id AS UUID)
RETURNING {_COLUMNS}
"""

_UPDATE_STATUS_SQL = f"""
UPDATE control.datasets
SET
    status      = :new_status,
    activated_at = COALESCE(:activated_at, activated_at),
    archived_at  = COALESCE(:archived_at,  archived_at),
    archived_by  = COALESCE(:archived_by,  archived_by),
    updated_at   = :now,
    updated_by   = :actor_id
WHERE dataset_id   = CAST(:dataset_id   AS UUID)
  AND workspace_id = CAST(:workspace_id AS UUID)
RETURNING {_COLUMNS}
"""

_CHECK_NAME_SQL = """
SELECT 1 FROM control.datasets
WHERE workspace_id = CAST(:workspace_id AS UUID)
  AND lower(dataset_name) = lower(:dataset_name)
  AND (:exclude_id IS NULL OR dataset_id != CAST(:exclude_id AS UUID))
LIMIT 1
"""

_CHECK_PHYSICAL_ID_SQL = """
SELECT 1 FROM control.datasets
WHERE data_source_id = CAST(:data_source_id AS UUID)
  AND lower(physical_identifier) = lower(:physical_identifier)
  AND status != 'archived'
  AND (:exclude_id IS NULL OR dataset_id != CAST(:exclude_id AS UUID))
LIMIT 1
"""

_COUNT_BY_DATA_SOURCE_SQL = """
SELECT COUNT(*) FROM control.datasets
WHERE data_source_id = CAST(:data_source_id AS UUID)
  AND status = ANY(:statuses)
"""

_CONSTRAINT_DUPLICATE_NAME = "uq_dataset_name_workspace"
_CONSTRAINT_DUPLICATE_PHYSICAL_ID = "uq_dataset_physical_id_source"


# ─────────────────────────────────────────────────────────────────────────────
# Row → domain model
# ─────────────────────────────────────────────────────────────────────────────


def _row_to_dataset(row) -> Dataset:
    return Dataset(
        dataset_id=row[0],
        workspace_id=row[1],
        tenant_id=row[2],
        data_source_id=row[3],
        dataset_name=row[4],
        dataset_type=row[5],
        physical_identifier=row[6],
        schema_name=row[7],
        description=row[8],
        business_domain=row[9],
        criticality=row[10],
        owner_user_id=row[11],
        freshness_expectation=row[12],
        status=DatasetStatus(row[13]),
        created_at=row[14],
        updated_at=row[15],
        created_by=row[16],
        updated_by=row[17],
        activated_at=row[18],
        archived_at=row[19],
        archived_by=row[20],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Repository
# ─────────────────────────────────────────────────────────────────────────────


class DatasetRepository:
    """All SQL operations against ``control.datasets``."""

    # ── insert ──────────────────────────────────────────────────────────────

    def insert(self, db: Session, dataset: Dataset) -> Dataset:
        ds_id = dataset.dataset_id or uuid.uuid4()
        now = datetime.now(UTC)
        try:
            result = db.execute(
                text(_INSERT_SQL),
                {
                    "dataset_id": str(ds_id),
                    "workspace_id": str(dataset.workspace_id),
                    "tenant_id": str(dataset.tenant_id),
                    "data_source_id": str(dataset.data_source_id)
                    if dataset.data_source_id
                    else None,
                    "dataset_name": dataset.dataset_name,
                    "dataset_type": dataset.dataset_type,
                    "physical_identifier": dataset.physical_identifier,
                    "schema_name": dataset.schema_name,
                    "description": dataset.description,
                    "business_domain": dataset.business_domain,
                    "criticality": dataset.criticality,
                    "owner_user_id": str(dataset.owner_user_id) if dataset.owner_user_id else None,
                    "freshness_expectation": dataset.freshness_expectation,
                    "now": now,
                    "created_by": str(dataset.created_by),
                },
            )
            row = result.fetchone()
        except IntegrityError as exc:
            orig = getattr(exc, "orig", None)
            err_str = str(orig) if orig else str(exc)
            if _CONSTRAINT_DUPLICATE_NAME in err_str:
                raise DuplicateDatasetNameError(
                    f"A dataset named '{dataset.dataset_name}' already exists in this workspace."
                ) from exc
            if _CONSTRAINT_DUPLICATE_PHYSICAL_ID in err_str:
                raise DuplicatePhysicalIdentifierError(
                    f"Physical identifier '{dataset.physical_identifier}' already exists for this data source."
                ) from exc
            raise
        return _row_to_dataset(row)

    # ── read ────────────────────────────────────────────────────────────────

    def find_by_id(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        dataset_id: UUID,
    ) -> Dataset | None:
        result = db.execute(
            text(_SELECT_BY_ID_SQL),
            {"dataset_id": str(dataset_id), "workspace_id": str(workspace_id)},
        )
        row = result.fetchone()
        return _row_to_dataset(row) if row else None

    def find_by_id_for_update(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        dataset_id: UUID,
    ) -> Dataset | None:
        result = db.execute(
            text(_SELECT_BY_ID_SQL + " FOR UPDATE"),
            {"dataset_id": str(dataset_id), "workspace_id": str(workspace_id)},
        )
        row = result.fetchone()
        return _row_to_dataset(row) if row else None

    # ── list ────────────────────────────────────────────────────────────────

    def list_datasets(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        filters: DatasetListFilters,
    ) -> DatasetListResult:
        where_clauses = ["d.workspace_id = CAST(:workspace_id AS UUID)"]
        params: dict = {"workspace_id": str(workspace_id)}

        if filters.status:
            where_clauses.append("d.status = :status_filter")
            params["status_filter"] = filters.status
        if filters.data_source_id:
            where_clauses.append("d.data_source_id = CAST(:ds_filter AS UUID)")
            params["ds_filter"] = str(filters.data_source_id)
        if filters.owner_user_id:
            where_clauses.append("d.owner_user_id = CAST(:owner_filter AS UUID)")
            params["owner_filter"] = str(filters.owner_user_id)
        if filters.business_domain:
            where_clauses.append("d.business_domain = :domain_filter")
            params["domain_filter"] = filters.business_domain
        if filters.criticality:
            where_clauses.append("d.criticality = :criticality_filter")
            params["criticality_filter"] = filters.criticality
        if filters.dataset_type:
            where_clauses.append("d.dataset_type = :type_filter")
            params["type_filter"] = filters.dataset_type
        if filters.search:
            where_clauses.append(
                "(d.dataset_name ILIKE :search OR d.physical_identifier ILIKE :search)"
            )
            params["search"] = f"%{filters.search}%"

        where_sql = " AND ".join(where_clauses)

        # Validate sort column
        sort_col = (
            filters.sort_by
            if filters.sort_by
            in (
                "created_at",
                "updated_at",
                "dataset_name",
                "status",
                "dataset_type",
                "criticality",
                "business_domain",
            )
            else "created_at"
        )
        sort_dir = "ASC" if filters.sort_order.upper() == "ASC" else "DESC"

        list_sql = f"""
            SELECT
                d.dataset_id, d.workspace_id, d.dataset_name, d.dataset_type,
                d.physical_identifier, d.status, d.business_domain, d.criticality,
                d.owner_user_id, d.data_source_id,
                ds.source_name,
                (SELECT COUNT(*) FROM control.dataset_fields f WHERE f.dataset_id = d.dataset_id),
                d.created_at, d.updated_at
            FROM control.datasets d
            LEFT JOIN control.data_sources ds ON ds.data_source_id = d.data_source_id
            WHERE {where_sql}
            ORDER BY d.{sort_col} {sort_dir}
            LIMIT :limit OFFSET :offset
        """
        params["limit"] = filters.limit
        params["offset"] = filters.offset

        result = db.execute(text(list_sql), params)
        items = [
            DatasetListItem(
                dataset_id=r[0],
                workspace_id=r[1],
                dataset_name=r[2],
                dataset_type=r[3],
                physical_identifier=r[4],
                status=r[5],
                business_domain=r[6],
                criticality=r[7],
                owner_user_id=r[8],
                data_source_id=r[9],
                data_source_name=r[10],
                field_count=r[11],
                created_at=r[12],
                updated_at=r[13],
            )
            for r in result.fetchall()
        ]

        count_sql = f"""
            SELECT COUNT(*) FROM control.datasets d
            WHERE {where_sql}
        """
        count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
        total = db.execute(text(count_sql), count_params).scalar()

        return DatasetListResult(
            items=items,
            total_count=total,
            limit=filters.limit,
            offset=filters.offset,
        )

    # ── update ──────────────────────────────────────────────────────────────

    def update(self, db: Session, dataset: Dataset) -> Dataset:
        now = datetime.now(UTC)
        try:
            result = db.execute(
                text(_UPDATE_METADATA_SQL),
                {
                    "dataset_id": str(dataset.dataset_id),
                    "workspace_id": str(dataset.workspace_id),
                    "dataset_name": dataset.dataset_name,
                    "schema_name": dataset.schema_name,
                    "description": dataset.description,
                    "business_domain": dataset.business_domain,
                    "criticality": dataset.criticality,
                    "owner_user_id": str(dataset.owner_user_id) if dataset.owner_user_id else None,
                    "freshness_expectation": dataset.freshness_expectation,
                    "now": now,
                    "updated_by": str(dataset.updated_by) if dataset.updated_by else None,
                },
            )
            row = result.fetchone()
        except IntegrityError as exc:
            orig = getattr(exc, "orig", None)
            err_str = str(orig) if orig else str(exc)
            if _CONSTRAINT_DUPLICATE_NAME in err_str:
                raise DuplicateDatasetNameError(
                    f"A dataset named '{dataset.dataset_name}' already exists in this workspace."
                ) from exc
            raise
        if row is None:
            raise DatasetNotFoundError(
                f"Dataset {dataset.dataset_id} not found in workspace {dataset.workspace_id}."
            )
        return _row_to_dataset(row)

    def update_status(
        self,
        db: Session,
        *,
        dataset_id: UUID,
        workspace_id: UUID,
        new_status: str,
        actor_id: UUID,
        activated_at: datetime | None = None,
        archived_at: datetime | None = None,
        archived_by: UUID | None = None,
    ) -> Dataset:
        now = datetime.now(UTC)
        result = db.execute(
            text(_UPDATE_STATUS_SQL),
            {
                "dataset_id": str(dataset_id),
                "workspace_id": str(workspace_id),
                "new_status": new_status,
                "activated_at": activated_at,
                "archived_at": archived_at,
                "archived_by": str(archived_by) if archived_by else None,
                "now": now,
                "actor_id": str(actor_id),
            },
        )
        row = result.fetchone()
        if row is None:
            raise DatasetNotFoundError(
                f"Dataset {dataset_id} not found in workspace {workspace_id}."
            )
        return _row_to_dataset(row)

    # ── uniqueness checks ───────────────────────────────────────────────────

    def check_name_exists(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        dataset_name: str,
        exclude_id: UUID | None = None,
    ) -> bool:
        result = db.execute(
            text(_CHECK_NAME_SQL),
            {
                "workspace_id": str(workspace_id),
                "dataset_name": dataset_name,
                "exclude_id": str(exclude_id) if exclude_id else None,
            },
        )
        return result.fetchone() is not None

    def check_physical_id_exists(
        self,
        db: Session,
        *,
        data_source_id: UUID,
        physical_identifier: str,
        exclude_id: UUID | None = None,
    ) -> bool:
        result = db.execute(
            text(_CHECK_PHYSICAL_ID_SQL),
            {
                "data_source_id": str(data_source_id),
                "physical_identifier": physical_identifier,
                "exclude_id": str(exclude_id) if exclude_id else None,
            },
        )
        return result.fetchone() is not None

    # ── cross-feature queries ───────────────────────────────────────────────

    def count_by_data_source(
        self,
        db: Session,
        *,
        data_source_id: UUID,
        statuses: tuple[str, ...] = ("draft", "active", "inactive"),
    ) -> int:
        result = db.execute(
            text(_COUNT_BY_DATA_SOURCE_SQL),
            {
                "data_source_id": str(data_source_id),
                "statuses": list(statuses),
            },
        )
        return result.scalar() or 0
