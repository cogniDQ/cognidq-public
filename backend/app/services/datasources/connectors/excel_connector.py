"""
F-CONN-P0-LOCAL — Excel file connector (spec §7.1, §17, §19).

Excel workbooks expose each worksheet as a logical "table" inside a single
"default" schema. Sheet selection is handled by ``preview_dataset`` and
``get_columns`` via the ``table_name`` argument; each sheet name is the
unmodified worksheet title.

Spec contract
-------------
- ``connection_config`` keys:
    file_path:   str   (required)
    has_header:  bool  (optional, default True)
- Backed by pandas + openpyxl (pinned in requirements.txt).
- Inherits the global 2 000 000-row preview cap.
- ``normalize_error`` maps file-system / openpyxl exceptions to spec §13.4
  codes.

SECURITY
--------
Same realpath escape protection as the CSV connector — see
``file_helpers.resolve_local_path``.
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
    map_pandas_dtype,
    resolve_local_path,
    scrub_records,
)

_VALID_EXTENSIONS = (".xlsx", ".xls", ".xlsm")
_TYPE_INFERENCE_SAMPLE_ROWS = 1_000


class ExcelConnector(BaseConnector):
    """Local Excel workbook connector — one connection per .xlsx file."""

    connector_type = "excel"

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
            sheets = self._sheet_names()
        except Exception as exc:  # parser errors
            return (
                False,
                f"Could not open workbook: {exc}",
                {"error_code": "FILE_PARSE_ERROR"},
            )

        if not sheets:
            return (
                False,
                "Workbook has no sheets.",
                {"error_code": "DATASET_EMPTY"},
            )

        return (
            True,
            f"Workbook is readable ({len(sheets)} sheet(s)).",
            {"size_bytes": size, "path": str(path), "sheet_count": len(sheets)},
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
        sheets = self._sheet_names()
        return [
            {
                "schema_name": "default",
                "table_name": s,
                "row_count": None,
                "metadata": {"file_path": str(path), "sheet_name": s},
            }
            for s in sheets
        ]

    async def discover_files(self, path: str | None = None) -> list[dict[str, Any]]:
        resolved = self._resolve_path()
        return [
            {
                "name": resolved.name,
                "path": str(resolved),
                "size_bytes": os.path.getsize(resolved),
                "format": resolved.suffix.lstrip(".").lower() or "xlsx",
            }
        ]

    async def get_columns(
        self, table_name: str, schema_name: str | None = None
    ) -> list[dict[str, Any]]:
        df = self._read_sheet(table_name, rows=_TYPE_INFERENCE_SAMPLE_ROWS)
        out: list[dict[str, Any]] = []
        for col_name, dtype in df.dtypes.items():
            out.append(
                {
                    "column_name": str(col_name),
                    "column_type": map_pandas_dtype(str(dtype)),
                    "is_nullable": bool(df[col_name].isna().any()),
                    "is_primary_key": False,
                }
            )
        return out

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("Excel connector does not support SQL execution.")

    async def get_row_count(self, table_name: str, schema_name: str | None = None) -> int:
        # No streaming line API for xlsx — load just the sheet shape.
        df = self._read_sheet(table_name, rows=PREVIEW_ROW_HARD_CAP)
        return int(df.shape[0])

    async def preview_dataset(
        self,
        table_name: str,
        schema_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        capped = min(max(0, int(limit)), PREVIEW_ROW_HARD_CAP)
        if capped == 0:
            return []
        # pandas openpyxl reader has no nrows for xlsx; load then slice.
        df = self._read_sheet(table_name, rows=capped).head(capped)
        return scrub_records(df.to_dict(orient="records"))

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
        if ("worksheet" in lowered and "not found" in lowered) or "no sheet named" in lowered:
            return NormalizedConnectorError(
                code="DATASET_NOT_FOUND",
                message=raw[:500],
                original=exc,
            )
        if (
            "badzipfile" in lowered
            or "not a zip" in lowered
            or "invalid file" in lowered
            or "openpyxl" in lowered
        ):
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

    def _has_header(self) -> bool:
        cfg = self.connection_config or {}
        if "has_header" not in cfg:
            return True
        return bool(cfg["has_header"])

    def _sheet_names(self) -> list[str]:
        import openpyxl  # type: ignore

        path = self._resolve_path()
        # read_only + data_only avoids loading formulas / styles.
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
        try:
            return list(wb.sheetnames)
        finally:
            wb.close()

    def _read_sheet(self, sheet_name: str, rows: int):
        import pandas as pd

        path = self._resolve_path()
        try:
            df = pd.read_excel(
                path,
                sheet_name=sheet_name,
                header=0 if self._has_header() else None,
                engine="openpyxl",
            )
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise ValueError(f"Excel parser error: {exc}") from exc
        if rows and rows > 0:
            df = df.head(rows)
        return df
