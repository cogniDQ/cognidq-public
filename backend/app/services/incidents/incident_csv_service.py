"""
F051 — Incident CSV Service
============================

Generates CSV bytes from incident data with formula-injection defense.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from app.models.incident import Incident

_CSV_COLUMNS = [
    "id",
    "title",
    "severity",
    "priority",
    "status",
    "impact_summary",
    "owner_id",
    "created_by_user_id",
    "opened_at",
    "acknowledged_at",
    "resolved_at",
    "closed_at",
    "resolution_summary",
    "updated_at",
]

_DANGEROUS_FIRST_CHARS = frozenset("=+-@")


def safe_csv_value(value) -> str:
    """Escape values that could trigger formula injection in spreadsheets."""
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in _DANGEROUS_FIRST_CHARS:
        return "'" + s
    return s


class IncidentCsvService:
    """Formats incident records as CSV bytes."""

    def generate_csv(
        self,
        incidents: list[Incident],
        *,
        truncated: bool = False,
    ) -> bytes:
        """Return UTF-8-BOM-prefixed CSV bytes."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(_CSV_COLUMNS)

        for inc in incidents:
            row = []
            for col in _CSV_COLUMNS:
                val = getattr(inc, col, None)
                if isinstance(val, datetime):
                    row.append(val.isoformat())
                elif val is None:
                    row.append("")
                else:
                    row.append(safe_csv_value(val))
            writer.writerow(row)

        if truncated:
            writer.writerow(
                [
                    "# NOTE: Export truncated at 10000 rows. Apply narrower filters for a complete export."
                ]
            )

        return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")
