"""
Dataset metadata loader for the NL Rule Builder.

Loads the full schema (columns, types, nullability, descriptions, key hints)
for a *selected* dataset so the LLM parser is grounded in real metadata
instead of guessing at column names and types.

Spec §4.1, §15 — must work even without glossary terms; uses dataset
metadata, column names + types, nullability, key hints, and descriptions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from dataclasses import field as _dc_field
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ColumnMeta:
    name: str
    data_type: str
    nullable: bool = True
    description: str | None = None
    is_key_candidate: bool = False
    sensitivity_classification: str | None = None


@dataclass(slots=True)
class DatasetMeta:
    dataset_id: str
    dataset_name: str
    schema_name: str | None = None
    description: str | None = None
    business_domain: str | None = None
    columns: list[ColumnMeta] = _dc_field(default_factory=list)

    def column_by_name(self, name: str) -> ColumnMeta | None:
        if not name:
            return None
        n = name.strip().lower()
        for c in self.columns:
            if c.name.lower() == n:
                return c
        return None

    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def to_prompt_block(self, max_columns: int = 80) -> str:
        """Render the dataset as a compact, deterministic block for the LLM prompt."""
        cols = self.columns[:max_columns]
        lines = [f"Dataset: {self.dataset_name}"]
        if self.schema_name:
            lines.append(f"Schema: {self.schema_name}")
        if self.business_domain:
            lines.append(f"Domain: {self.business_domain}")
        if self.description:
            lines.append(f"Description: {self.description}")
        lines.append("Columns:")
        for c in cols:
            null_str = "" if c.nullable else " NOT NULL"
            key_str = " [key]" if c.is_key_candidate else ""
            desc = f" — {c.description}" if c.description else ""
            lines.append(f"  - {c.name}: {c.data_type}{null_str}{key_str}{desc}")
        if len(self.columns) > max_columns:
            lines.append(f"  … and {len(self.columns) - max_columns} more columns")
        return "\n".join(lines)


def load_dataset_meta(
    db: Session,
    workspace_id: UUID,
    dataset_id: UUID,
) -> DatasetMeta | None:
    """Load a single dataset's full metadata (header + columns).

    Returns None if the dataset does not exist in this workspace.
    """
    try:
        row = db.execute(
            text(
                """
                SELECT dataset_id, dataset_name, schema_name, description, business_domain
                FROM control.datasets
                WHERE dataset_id = CAST(:id AS UUID)
                  AND workspace_id = CAST(:ws AS UUID)
                """
            ),
            {"id": str(dataset_id), "ws": str(workspace_id)},
        ).first()
        if not row:
            return None
        col_rows = db.execute(
            text(
                """
                SELECT field_name, data_type, nullable, business_definition,
                       is_key_candidate, sensitivity_classification
                FROM control.dataset_fields
                WHERE dataset_id = CAST(:id AS UUID)
                ORDER BY ordinal_position
                """
            ),
            {"id": str(dataset_id)},
        ).all()
        columns = [
            ColumnMeta(
                name=r[0],
                data_type=r[1] or "unknown",
                nullable=bool(r[2]) if r[2] is not None else True,
                description=r[3],
                is_key_candidate=bool(r[4]) if r[4] is not None else False,
                sensitivity_classification=r[5],
            )
            for r in col_rows
        ]
        return DatasetMeta(
            dataset_id=str(row[0]),
            dataset_name=row[1],
            schema_name=row[2],
            description=row[3],
            business_domain=row[4],
            columns=columns,
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("Failed to load dataset metadata for %s: %s", dataset_id, exc)
        return None


def load_dataset_meta_by_name(
    db: Session,
    workspace_id: UUID,
    dataset_name: str,
) -> list[DatasetMeta]:
    """Resolve a dataset name to one or more datasets in the workspace
    (case-insensitive). Multiple matches → caller asks user to pick (spec §4.2).
    """
    if not dataset_name or not dataset_name.strip():
        return []
    try:
        rows = db.execute(
            text(
                """
                SELECT dataset_id
                FROM control.datasets
                WHERE workspace_id = CAST(:ws AS UUID)
                  AND LOWER(dataset_name) = LOWER(:name)
                """
            ),
            {"ws": str(workspace_id), "name": dataset_name.strip()},
        ).all()
        out: list[DatasetMeta] = []
        for r in rows:
            ds = load_dataset_meta(db, workspace_id, UUID(str(r[0])))
            if ds is not None:
                out.append(ds)
        return out
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to resolve dataset by name '%s': %s", dataset_name, exc)
        return []
