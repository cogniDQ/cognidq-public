"""
F-CONN-P0-LOCAL — JSON / NDJSON file connector (spec §7.1, §17, §19).

Supports three on-disk shapes (auto-detected unless ``json_format`` is given):

- ``ndjson`` — newline-delimited JSON (one object per line).
- ``array`` — a single top-level JSON array of objects.
- ``object`` — a single top-level JSON object whose values become a single
  pseudo-row (rare; only used when neither of the above shapes matches).

Spec contract
-------------
- ``connection_config`` keys:
    file_path:    str   (required)
    encoding:     str   (optional, default "utf-8")
    json_format:  str   (optional, one of "auto"|"ndjson"|"array"|"object";
                         default "auto")
- Like CSV, every JSON connection has a single logical "schema" (``"default"``)
  and a single "table" (the file's stem).
"""

from __future__ import annotations

import json
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

_VALID_EXTENSIONS = (".json", ".ndjson", ".jsonl")
_TYPE_INFERENCE_SAMPLE_ROWS = 1_000


class JSONConnector(BaseConnector):
    """Local JSON / NDJSON file connector."""

    connector_type = "json"

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
            shape = self._detect_shape(path)
        except Exception as exc:
            return (
                False,
                f"Could not parse JSON: {exc}",
                {"error_code": "FILE_PARSE_ERROR"},
            )

        return (
            True,
            f"File is readable ({shape}).",
            {"size_bytes": size, "path": str(path), "shape": shape},
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
        return [
            {
                "schema_name": "default",
                "table_name": path.stem,
                "row_count": None,
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
                "format": resolved.suffix.lstrip(".").lower() or "json",
            }
        ]

    async def get_columns(
        self, table_name: str, schema_name: str | None = None
    ) -> list[dict[str, Any]]:
        df = self._read(rows=_TYPE_INFERENCE_SAMPLE_ROWS)
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
        raise NotImplementedError("JSON connector does not support SQL execution.")

    async def get_row_count(self, table_name: str, schema_name: str | None = None) -> int:
        df = self._read(rows=PREVIEW_ROW_HARD_CAP)
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
        df = self._read(rows=capped).head(capped)
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
        if isinstance(exc, json.JSONDecodeError) or "expecting" in lowered or "json" in lowered:
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

    def _encoding(self) -> str:
        return (self.connection_config or {}).get("encoding") or "utf-8"

    def _format(self) -> str:
        cfg = self.connection_config or {}
        fmt = (cfg.get("json_format") or "auto").lower()
        if fmt not in ("auto", "ndjson", "array", "object"):
            fmt = "auto"
        return fmt

    def _detect_shape(self, path: Path) -> str:
        if self._format() != "auto":
            return self._format()
        # Peek: if first non-whitespace char is '[' → array; else if file
        # contains a newline-separated record set → ndjson; else object.
        with open(path, encoding=self._encoding(), errors="replace") as fh:
            head = fh.read(4096).lstrip()
        if not head:
            raise ValueError("Empty JSON document.")
        if head[0] == "[":
            return "array"
        if head[0] == "{":
            # Try to parse first line independently — if it succeeds and the
            # file has more than one line, treat as NDJSON.
            with open(path, encoding=self._encoding(), errors="replace") as fh:
                first = fh.readline().strip()
                second = fh.readline().strip()
            if second:
                try:
                    json.loads(first)
                    json.loads(second)
                    return "ndjson"
                except json.JSONDecodeError:
                    pass
            return "object"
        raise ValueError("Could not detect JSON shape; expected '[' or '{' at the start.")

    def _read(self, rows: int):
        import pandas as pd

        path = self._resolve_path()
        try:
            shape = self._detect_shape(path)
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise ValueError(f"JSON parser error: {exc}") from exc

        try:
            if shape == "ndjson":
                df = pd.read_json(
                    path,
                    lines=True,
                    encoding=self._encoding(),
                    nrows=rows if rows and rows > 0 else None,
                )
            elif shape == "array":
                # pandas read_json on an array
                df = pd.read_json(path, encoding=self._encoding())
            else:  # object → single-row frame
                with open(path, encoding=self._encoding()) as fh:
                    obj = json.load(fh)
                if not isinstance(obj, dict):
                    raise ValueError("Expected JSON object at root.")
                df = pd.DataFrame([obj])
        except FileNotFoundError:
            raise
        except json.JSONDecodeError:
            raise
        except Exception as exc:
            raise ValueError(f"JSON parser error: {exc}") from exc

        if rows and rows > 0:
            df = df.head(rows)
        return df
