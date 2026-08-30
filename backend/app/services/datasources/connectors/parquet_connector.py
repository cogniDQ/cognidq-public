"""
F-CONN-P0-LOCAL — Parquet file connector (spec §7.1, §17, §19).

Reads ``.parquet`` files via pyarrow. The schema is derived from the
parquet metadata (no inference), so type detection is exact.

Spec contract
-------------
- ``connection_config`` keys:
    file_path:  str  (required)
- One logical schema (``"default"``) and one logical table (file stem).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.services.datasources.connectors.base import (
    BaseConnector,
    NormalizedConnectorError,
)
from app.services.datasources.connectors.file_helpers import (
    PREVIEW_ROW_HARD_CAP,
    resolve_local_path,
    scrub_records,
)

_VALID_EXTENSIONS = (".parquet", ".pq")


def _arrow_to_logical(arrow_type) -> str:
    """Map a pyarrow type to a coarse logical type label."""
    import pyarrow as pa  # type: ignore

    if pa.types.is_integer(arrow_type):
        return "integer"
    if pa.types.is_floating(arrow_type):
        return "float"
    if pa.types.is_boolean(arrow_type):
        return "boolean"
    if pa.types.is_timestamp(arrow_type):
        return "timestamp"
    if pa.types.is_date(arrow_type):
        return "date"
    if pa.types.is_time(arrow_type):
        return "time"
    return "string"


class ParquetConnector(BaseConnector):
    """Local Apache Parquet file connector."""

    connector_type = "parquet"

    # ── lifecycle ───────────────────────────────────────────────────────────

    async def test_connection(self) -> tuple[bool, str, dict[str, Any] | None]:
        try:
            path = self._resolve_path()
        except FileNotFoundError as exc:
            return False, str(exc), {"error_code": "DATASET_NOT_FOUND"}
        except ValueError as exc:
            return False, str(exc), {"error_code": "UNSUPPORTED_FILE_TYPE"}

        size = os.path.getsize(path)
        if size == 0:
            return False, "File is empty.", {"error_code": "DATASET_EMPTY"}

        try:
            num_rows, num_cols = self._inspect_metadata(path)
        except Exception as exc:
            return (
                False,
                f"Could not read parquet metadata: {exc}",
                {"error_code": "FILE_PARSE_ERROR"},
            )

        return (
            True,
            f"Parquet readable ({num_rows} rows, {num_cols} cols).",
            {
                "size_bytes": size,
                "path": str(path),
                "num_rows": num_rows,
                "num_columns": num_cols,
            },
        )

    async def connect(self) -> None:
        self.connection = self._resolve_path()

    async def disconnect(self) -> None:
        self.connection = None

    # ── §10.2 + legacy discovery ────────────────────────────────────────────

    async def get_schemas(self) -> list[str]:
        return ["default"]

    async def get_tables(self, schema_name: str | None = None) -> list[dict[str, Any]]:
        path = self._resolve_path()
        num_rows, _ = self._inspect_metadata(path)
        return [
            {
                "schema_name": "default",
                "table_name": path.stem,
                "row_count": num_rows,
                "metadata": {
                    "file_path": str(path),
                    "size_bytes": os.path.getsize(path),
                },
            }
        ]

    async def discover_files(self, path: str | None = None) -> list[dict[str, Any]]:
        resolved = self._resolve_path()
        return [
            {
                "name": resolved.name,
                "path": str(resolved),
                "size_bytes": os.path.getsize(resolved),
                "format": "parquet",
            }
        ]

    async def get_columns(
        self, table_name: str, schema_name: str | None = None
    ) -> list[dict[str, Any]]:
        import pyarrow.parquet as pq  # type: ignore

        path = self._resolve_path()
        schema = pq.read_schema(path)
        out: list[dict[str, Any]] = []
        for field in schema:
            out.append(
                {
                    "column_name": field.name,
                    "column_type": _arrow_to_logical(field.type),
                    "is_nullable": bool(field.nullable),
                    "is_primary_key": False,
                }
            )
        return out

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("Parquet connector does not support SQL execution.")

    async def get_row_count(self, table_name: str, schema_name: str | None = None) -> int:
        path = self._resolve_path()
        num_rows, _ = self._inspect_metadata(path)
        return num_rows

    async def preview_dataset(
        self,
        table_name: str,
        schema_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        capped = min(max(0, int(limit)), PREVIEW_ROW_HARD_CAP)
        if capped == 0:
            return []

        import pyarrow.parquet as pq  # type: ignore

        path = self._resolve_path()
        try:
            pf = pq.ParquetFile(path)
        except Exception as exc:
            raise ValueError(f"Parquet parser error: {exc}") from exc

        # Stream batches up to the row cap.
        collected: list[dict[str, Any]] = []
        remaining = capped
        for batch in pf.iter_batches(batch_size=min(remaining, 10_000)):
            if remaining <= 0:
                break
            df = batch.to_pandas()
            if len(df) > remaining:
                df = df.head(remaining)
            collected.extend(scrub_records(df.to_dict(orient="records")))
            remaining -= len(df)
        return collected

    # ── error mapping ───────────────────────────────────────────────────────

    def normalize_error(self, exc: BaseException) -> NormalizedConnectorError:
        raw = str(exc) or type(exc).__name__
        lowered = raw.lower()

        if isinstance(exc, FileNotFoundError) or "no such file" in lowered:
            return NormalizedConnectorError(
                code="DATASET_NOT_FOUND", message=raw[:500], original=exc
            )
        if isinstance(exc, PermissionError):
            return NormalizedConnectorError(
                code="CONNECTION_PERMISSION_DENIED",
                message=raw[:500],
                original=exc,
            )
        if isinstance(exc, ValueError) and "unsupported file type" in lowered:
            return NormalizedConnectorError(
                code="UNSUPPORTED_FILE_TYPE",
                message=raw[:500],
                original=exc,
            )
        if "parquet" in lowered or "thrift" in lowered or "magic" in lowered or "footer" in lowered:
            return NormalizedConnectorError(
                code="FILE_PARSE_ERROR",
                message=raw[:500],
                original=exc,
            )
        return super().normalize_error(exc)

    # ── helpers ─────────────────────────────────────────────────────────────

    def _resolve_path(self) -> Path:
        return resolve_local_path(
            (self.connection_config or {}).get("file_path"),
            _VALID_EXTENSIONS,
        )

    def _inspect_metadata(self, path: Path) -> tuple[int, int]:
        import pyarrow.parquet as pq  # type: ignore

        meta = pq.read_metadata(path)
        return int(meta.num_rows), int(meta.num_columns)
