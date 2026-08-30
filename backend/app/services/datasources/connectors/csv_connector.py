"""
F-CONN-P0-LOCAL — CSV file connector (spec §7.1, §17, §19).

Bound to a single CSV file path stored in ``connection_config['file_path']``.
Implements the spec §10.2 surface (validate_config, discover_*, preview_dataset,
normalize_error) plus the legacy abstract interface from
:class:`BaseConnector`. Reads are streamed via pandas.

Spec contract
-------------
- ``connection_config`` keys (validated against the registry credential schema):
    file_path:    str   (required, absolute or relative to UPLOAD_DIR)
    delimiter:    str   (optional, default ",")
    encoding:     str   (optional, default "utf-8")
    has_header:   bool  (optional, default True)
    quote_char:   str   (optional, default '"')
- A CSV connection has exactly one logical "schema" (``"default"``) and one
  logical "table" (the file). Discovery returns a single entry whose
  ``table_name`` is the file's basename without extension. Preview reads
  ``limit`` rows.
- ``preview_dataset`` enforces the global 2 million row hard cap from the
  product spec; callers asking for more get the cap.
- ``normalize_error`` maps file-system / parser exceptions to spec §13.4
  codes plus the F-CONN file-specific codes
  (``UNSUPPORTED_FILE_TYPE``, ``FILE_PARSE_ERROR``, ``DATASET_EMPTY``).

SECURITY
--------
Resolves ``file_path`` against ``settings.UPLOAD_DIR`` if relative, and
rejects any resolved path whose realpath escapes that root. The connector
never echoes credentials in errors (consistent with :meth:`normalize_error`).
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

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

#: Maximum number of distinct categories to consider when inferring types.
_TYPE_INFERENCE_SAMPLE_ROWS: int = 1_000

_VALID_EXTENSIONS = (".csv", ".tsv", ".txt")


class CSVConnector(BaseConnector):
    """Local CSV file connector."""

    connector_type = "csv"

    # ── lifecycle ───────────────────────────────────────────────────────────

    async def test_connection(self) -> tuple[bool, str, dict[str, Any] | None]:
        """Resolve the configured path and check it is a readable file.

        Returns:
            (success, message, details). ``details`` carries ``size_bytes``
            on success and ``error_code`` on failure.
        """
        try:
            path = self._resolve_path()
        except FileNotFoundError as exc:
            return False, str(exc), {"error_code": "DATASET_NOT_FOUND"}
        except ValueError as exc:
            return False, str(exc), {"error_code": "UNSUPPORTED_FILE_TYPE"}

        try:
            size = os.path.getsize(path)
        except OSError as exc:
            return False, str(exc), {"error_code": "FILE_PARSE_ERROR"}

        if size == 0:
            return False, "File is empty.", {"error_code": "DATASET_EMPTY"}

        return True, "File is readable.", {"size_bytes": size, "path": str(path)}

    async def connect(self) -> None:
        """No-op for CSV — the file is opened lazily per operation."""
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
                "row_count": None,  # would require a full scan; deferred
                "metadata": {
                    "file_path": str(path),
                    "size_bytes": os.path.getsize(path),
                },
            }
        ]

    async def discover_files(self, path: str | None = None) -> list[dict[str, Any]]:
        """Return a single entry describing the configured CSV."""
        resolved = self._resolve_path()
        return [
            {
                "name": resolved.name,
                "path": str(resolved),
                "size_bytes": os.path.getsize(resolved),
                "format": resolved.suffix.lstrip(".") or "csv",
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
        """Not supported for CSV — DQ checks must be evaluated in Python."""
        raise NotImplementedError(
            "CSV connector does not support SQL execution. "
            "Use preview_dataset / execute_check instead."
        )

    async def get_row_count(self, table_name: str, schema_name: str | None = None) -> int:
        path = self._resolve_path()
        # Streaming line count, minus header if present.
        encoding = self.connection_config.get("encoding") or "utf-8"
        count = 0
        with open(path, encoding=encoding, errors="replace") as fh:
            for _ in fh:
                count += 1
        if self._has_header():
            count = max(0, count - 1)
        return count

    async def preview_dataset(
        self,
        table_name: str,
        schema_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        capped = min(max(0, int(limit)), PREVIEW_ROW_HARD_CAP)
        if capped == 0:
            return []
        df = self._read(rows=capped)
        return scrub_records(df.to_dict(orient="records"))

    # ── §10.2 error mapping ─────────────────────────────────────────────────

    def normalize_error(self, exc: BaseException) -> NormalizedConnectorError:
        """File-aware extension of the base error mapper."""
        raw = str(exc) or type(exc).__name__
        lowered = raw.lower()

        if isinstance(exc, FileNotFoundError) or "no such file" in lowered:
            return NormalizedConnectorError(
                code="DATASET_NOT_FOUND",
                message=raw[:500],
                original=exc,
            )
        if isinstance(exc, PermissionError):
            return NormalizedConnectorError(
                code="CONNECTION_PERMISSION_DENIED",
                message=raw[:500],
                original=exc,
            )
        if isinstance(exc, UnicodeDecodeError) or "codec can't decode" in lowered:
            return NormalizedConnectorError(
                code="FILE_PARSE_ERROR",
                message=raw[:500],
                original=exc,
            )
        if "no columns to parse" in lowered or "empty data" in lowered:
            return NormalizedConnectorError(
                code="DATASET_EMPTY",
                message=raw[:500],
                original=exc,
            )
        if isinstance(exc, ValueError) and "unsupported file type" in lowered:
            return NormalizedConnectorError(
                code="UNSUPPORTED_FILE_TYPE",
                message=raw[:500],
                original=exc,
            )
        if "parser" in lowered or "tokenizing" in lowered or "expected" in lowered:
            return NormalizedConnectorError(
                code="FILE_PARSE_ERROR",
                message=raw[:500],
                original=exc,
            )
        # Defer to the base mapper for everything else.
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

    def _read(self, rows: int):
        """Read up to ``rows`` rows into a pandas DataFrame.

        ``rows`` is treated as a soft cap; pandas may return fewer if the
        file is shorter. ``PREVIEW_ROW_HARD_CAP`` is enforced here as a
        defense-in-depth — preview_dataset already caps before calling.
        """
        import pandas as pd  # local import to keep import cost out of cold-path

        path = self._resolve_path()
        cfg = self.connection_config or {}

        delimiter = cfg.get("delimiter") or ","
        encoding = cfg.get("encoding") or "utf-8"
        quote = cfg.get("quote_char") or '"'
        nrows = min(max(0, int(rows)), PREVIEW_ROW_HARD_CAP)

        try:
            df = pd.read_csv(
                path,
                delimiter=delimiter,
                encoding=encoding,
                quotechar=quote,
                header=0 if self._has_header() else None,
                nrows=nrows if nrows > 0 else None,
                low_memory=False,
                on_bad_lines="error",
            )
        except FileNotFoundError:
            raise
        except UnicodeDecodeError:
            raise
        except Exception as exc:
            # Re-raise with a marker so normalize_error maps to FILE_PARSE_ERROR.
            raise ValueError(f"CSV parser error: {exc}") from exc

        if df.empty:
            return df

        return df
