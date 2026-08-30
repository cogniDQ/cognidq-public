"""
F005 — Dataset Field repository layer
=======================================

Provides ``DatasetFieldRepository`` — CRUD against ``control.dataset_fields``.

All SQL via SQLAlchemy ``text()`` with named bind params.
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
    DatasetFieldNotFoundError,
    DuplicateFieldNameError,
)
from app.services.datasets.models import DatasetField

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# SQL constants
# ─────────────────────────────────────────────────────────────────────────────

_FIELD_COLUMNS = """
    field_id, dataset_id, field_name, data_type,
    nullable, business_definition, sensitivity_classification,
    is_key_candidate, ordinal_position, created_at, updated_at,
    sample_values, sample_values_updated_at
"""

_INSERT_SQL = f"""
INSERT INTO control.dataset_fields (
    field_id, dataset_id, field_name, data_type,
    nullable, business_definition, sensitivity_classification,
    is_key_candidate, ordinal_position, created_at, updated_at
) VALUES (
    :field_id, :dataset_id, :field_name, :data_type,
    :nullable, :business_definition, :sensitivity_classification,
    :is_key_candidate, :ordinal_position, :now, :now
)
RETURNING {_FIELD_COLUMNS}
"""

_SELECT_BY_ID_SQL = f"""
SELECT {_FIELD_COLUMNS}
FROM control.dataset_fields
WHERE field_id   = CAST(:field_id   AS UUID)
  AND dataset_id = CAST(:dataset_id AS UUID)
"""

_SELECT_ALL_BY_DATASET_SQL = f"""
SELECT {_FIELD_COLUMNS}
FROM control.dataset_fields
WHERE dataset_id = CAST(:dataset_id AS UUID)
ORDER BY ordinal_position ASC
"""

_UPDATE_SQL = f"""
UPDATE control.dataset_fields
SET
    data_type                  = COALESCE(:data_type,                  data_type),
    nullable                   = COALESCE(:nullable,                   nullable),
    business_definition        = COALESCE(:business_definition,        business_definition),
    sensitivity_classification = COALESCE(:sensitivity_classification, sensitivity_classification),
    is_key_candidate           = COALESCE(:is_key_candidate,           is_key_candidate),
    ordinal_position           = COALESCE(:ordinal_position,           ordinal_position),
    updated_at                 = :now
WHERE field_id   = CAST(:field_id   AS UUID)
  AND dataset_id = CAST(:dataset_id AS UUID)
RETURNING {_FIELD_COLUMNS}
"""

_DELETE_SQL = """
DELETE FROM control.dataset_fields
WHERE field_id   = CAST(:field_id   AS UUID)
  AND dataset_id = CAST(:dataset_id AS UUID)
"""

_DELETE_ALL_BY_DATASET_SQL = """
DELETE FROM control.dataset_fields
WHERE dataset_id = CAST(:dataset_id AS UUID)
"""

_COUNT_BY_DATASET_SQL = """
SELECT COUNT(*) FROM control.dataset_fields
WHERE dataset_id = CAST(:dataset_id AS UUID)
"""

_MAX_ORDINAL_SQL = """
SELECT COALESCE(MAX(ordinal_position), 0)
FROM control.dataset_fields
WHERE dataset_id = CAST(:dataset_id AS UUID)
"""

_CHECK_NAME_SQL = """
SELECT 1 FROM control.dataset_fields
WHERE dataset_id = CAST(:dataset_id AS UUID)
  AND lower(field_name) = lower(:field_name)
  AND (:exclude_id IS NULL OR field_id != CAST(:exclude_id AS UUID))
LIMIT 1
"""

_CONSTRAINT_DUPLICATE_NAME = "uq_field_name_dataset"


# ─────────────────────────────────────────────────────────────────────────────
# Row → domain model
# ─────────────────────────────────────────────────────────────────────────────


def _row_to_field(row) -> DatasetField:
    return DatasetField(
        field_id=row[0],
        dataset_id=row[1],
        field_name=row[2],
        data_type=row[3],
        nullable=row[4],
        business_definition=row[5],
        sensitivity_classification=row[6],
        is_key_candidate=row[7],
        ordinal_position=row[8],
        created_at=row[9],
        updated_at=row[10],
        sample_values=list(row[11] or []),
        sample_values_updated_at=row[12],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Repository
# ─────────────────────────────────────────────────────────────────────────────


class DatasetFieldRepository:
    """All SQL operations against ``control.dataset_fields``."""

    # ── insert ──────────────────────────────────────────────────────────────

    def insert(self, db: Session, field: DatasetField) -> DatasetField:
        fid = field.field_id or uuid.uuid4()
        now = datetime.now(UTC)
        try:
            result = db.execute(
                text(_INSERT_SQL),
                {
                    "field_id": str(fid),
                    "dataset_id": str(field.dataset_id),
                    "field_name": field.field_name,
                    "data_type": field.data_type,
                    "nullable": field.nullable,
                    "business_definition": field.business_definition,
                    "sensitivity_classification": field.sensitivity_classification,
                    "is_key_candidate": field.is_key_candidate,
                    "ordinal_position": field.ordinal_position,
                    "now": now,
                },
            )
            row = result.fetchone()
        except IntegrityError as exc:
            orig = getattr(exc, "orig", None)
            err_str = str(orig) if orig else str(exc)
            if _CONSTRAINT_DUPLICATE_NAME in err_str:
                raise DuplicateFieldNameError(
                    f"A field named '{field.field_name}' already exists in this dataset."
                ) from exc
            raise
        return _row_to_field(row)

    # ── read ────────────────────────────────────────────────────────────────

    def find_by_id(
        self,
        db: Session,
        *,
        dataset_id: UUID,
        field_id: UUID,
    ) -> DatasetField | None:
        result = db.execute(
            text(_SELECT_BY_ID_SQL),
            {"field_id": str(field_id), "dataset_id": str(dataset_id)},
        )
        row = result.fetchone()
        return _row_to_field(row) if row else None

    def find_all_by_dataset(
        self,
        db: Session,
        *,
        dataset_id: UUID,
    ) -> list[DatasetField]:
        result = db.execute(
            text(_SELECT_ALL_BY_DATASET_SQL),
            {"dataset_id": str(dataset_id)},
        )
        return [_row_to_field(row) for row in result.fetchall()]

    # ── update ──────────────────────────────────────────────────────────────

    def update(self, db: Session, field: DatasetField) -> DatasetField:
        now = datetime.now(UTC)
        try:
            result = db.execute(
                text(_UPDATE_SQL),
                {
                    "field_id": str(field.field_id),
                    "dataset_id": str(field.dataset_id),
                    "data_type": field.data_type,
                    "nullable": field.nullable,
                    "business_definition": field.business_definition,
                    "sensitivity_classification": field.sensitivity_classification,
                    "is_key_candidate": field.is_key_candidate,
                    "ordinal_position": field.ordinal_position,
                    "now": now,
                },
            )
            row = result.fetchone()
        except IntegrityError as exc:
            orig = getattr(exc, "orig", None)
            err_str = str(orig) if orig else str(exc)
            if _CONSTRAINT_DUPLICATE_NAME in err_str:
                raise DuplicateFieldNameError(
                    f"A field named '{field.field_name}' already exists in this dataset."
                ) from exc
            raise
        if row is None:
            raise DatasetFieldNotFoundError(
                f"Field {field.field_id} not found in dataset {field.dataset_id}."
            )
        return _row_to_field(row)

    # ── delete ──────────────────────────────────────────────────────────────

    def delete(
        self,
        db: Session,
        *,
        dataset_id: UUID,
        field_id: UUID,
    ) -> bool:
        result = db.execute(
            text(_DELETE_SQL),
            {"field_id": str(field_id), "dataset_id": str(dataset_id)},
        )
        return result.rowcount > 0

    def delete_all_by_dataset(self, db: Session, *, dataset_id: UUID) -> int:
        result = db.execute(
            text(_DELETE_ALL_BY_DATASET_SQL),
            {"dataset_id": str(dataset_id)},
        )
        return result.rowcount

    # ── helpers ─────────────────────────────────────────────────────────────

    def count_by_dataset(self, db: Session, *, dataset_id: UUID) -> int:
        result = db.execute(
            text(_COUNT_BY_DATASET_SQL),
            {"dataset_id": str(dataset_id)},
        )
        return result.scalar() or 0

    def max_ordinal(self, db: Session, *, dataset_id: UUID) -> int:
        result = db.execute(
            text(_MAX_ORDINAL_SQL),
            {"dataset_id": str(dataset_id)},
        )
        return result.scalar() or 0

    def check_name_exists(
        self,
        db: Session,
        *,
        dataset_id: UUID,
        field_name: str,
        exclude_id: UUID | None = None,
    ) -> bool:
        result = db.execute(
            text(_CHECK_NAME_SQL),
            {
                "dataset_id": str(dataset_id),
                "field_name": field_name,
                "exclude_id": str(exclude_id) if exclude_id else None,
            },
        )
        return result.fetchone() is not None

    # ── bulk ────────────────────────────────────────────────────────────────

    def bulk_insert(
        self,
        db: Session,
        fields: list[DatasetField],
    ) -> list[DatasetField]:
        inserted: list[DatasetField] = []
        now = datetime.now(UTC)
        for field in fields:
            fid = field.field_id or uuid.uuid4()
            try:
                result = db.execute(
                    text(_INSERT_SQL),
                    {
                        "field_id": str(fid),
                        "dataset_id": str(field.dataset_id),
                        "field_name": field.field_name,
                        "data_type": field.data_type,
                        "nullable": field.nullable,
                        "business_definition": field.business_definition,
                        "sensitivity_classification": field.sensitivity_classification,
                        "is_key_candidate": field.is_key_candidate,
                        "ordinal_position": field.ordinal_position,
                        "now": now,
                    },
                )
                row = result.fetchone()
                inserted.append(_row_to_field(row))
            except IntegrityError as exc:
                orig = getattr(exc, "orig", None)
                err_str = str(orig) if orig else str(exc)
                if _CONSTRAINT_DUPLICATE_NAME in err_str:
                    raise DuplicateFieldNameError(
                        f"A field named '{field.field_name}' already exists in this dataset."
                    ) from exc
                raise
        return inserted
