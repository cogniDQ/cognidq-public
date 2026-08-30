"""
Shared helpers for local-file connectors (CSV, Excel, JSON, Parquet).

These helpers keep file-resolution rules and DataFrame-record scrubbing
consistent across connectors, and avoid drift between the four file
implementations.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

#: Hard cap on rows returned by any preview call (product spec §17.4).
PREVIEW_ROW_HARD_CAP: int = 2_000_000


def resolve_local_path(
    raw_path: str | None,
    valid_extensions: tuple[str, ...],
    *,
    field_name: str = "file_path",
) -> Path:
    """Resolve a configured ``file_path`` against ``settings.UPLOAD_DIR``.

    - Absolute paths are accepted only after ``Path.resolve()``.
    - Relative paths are resolved under ``settings.UPLOAD_DIR``; any path
      that escapes that base after realpath resolution raises
      :class:`PermissionError`.
    - The file's suffix must be in ``valid_extensions`` (lower-case, with
      leading dot, e.g. ``(".csv",)``).
    """
    if not raw_path:
        raise FileNotFoundError(f"{field_name} is required.")

    candidate = Path(raw_path).expanduser()

    if not candidate.is_absolute():
        from app.core.config import settings

        base = Path(settings.UPLOAD_DIR).resolve()
        candidate = (base / candidate).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            raise PermissionError(f"{field_name} resolves outside of UPLOAD_DIR.")
    else:
        candidate = candidate.resolve()

    if not candidate.exists():
        raise FileNotFoundError(f"File not found: {candidate}")
    if not candidate.is_file():
        raise FileNotFoundError(f"Not a regular file: {candidate}")
    if candidate.suffix.lower() not in valid_extensions:
        raise ValueError(
            f"Unsupported file type: {candidate.suffix}. Expected one of {valid_extensions}."
        )
    return candidate


def map_pandas_dtype(dtype: str) -> str:
    """Map a pandas dtype string to a coarse logical type label."""
    d = dtype.lower()
    if "int" in d:
        return "integer"
    if "float" in d:
        return "float"
    if "bool" in d:
        return "boolean"
    if "datetime" in d:
        return "timestamp"
    if "date" in d:
        return "date"
    return "string"


def scrub_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace NaN floats with ``None`` for JSON-safe payloads.

    pandas 2.x ``DataFrame.to_dict('records')`` re-introduces NaN even after
    ``df.where(df.notna(), None)``; iterate explicitly to be safe. Also
    coerces numpy scalars to Python natives where ``isinstance`` works.
    """
    out: list[dict[str, Any]] = []
    for raw in records:
        cleaned: dict[str, Any] = {}
        for k, v in raw.items():
            if isinstance(v, float) and math.isnan(v):
                cleaned[k] = None
            else:
                cleaned[k] = v
        out.append(cleaned)
    return out
