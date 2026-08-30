"""
F-CONN-P0-LOCAL — CSVConnector unit tests.

Coverage:
    1.  validate_config requires file_path.
    2.  test_connection succeeds for a real file.
    3.  test_connection reports DATASET_NOT_FOUND on a missing file.
    4.  test_connection reports DATASET_EMPTY on a 0-byte file.
    5.  test_connection rejects unsupported file extensions.
    6.  preview_dataset returns parsed rows with NaN -> None.
    7.  preview_dataset honours limit and the 2M hard cap.
    8.  get_columns infers logical types.
    9.  get_row_count counts data rows (header excluded).
    10. discover_files returns the configured file as one entry.
    11. normalize_error maps FileNotFoundError -> DATASET_NOT_FOUND.
    12. normalize_error maps PermissionError -> CONNECTION_PERMISSION_DENIED.
    13. normalize_error maps UnicodeDecodeError -> FILE_PARSE_ERROR.
    14. _resolve_path rejects paths escaping UPLOAD_DIR.
    15. Custom delimiter (TSV) is honoured.
    16. has_header=False makes column names positional.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from app.services.datasources.connectors.csv_connector import (
    PREVIEW_ROW_HARD_CAP,
    CSVConnector,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    p = tmp_path / "customers.csv"
    p.write_text(
        "id,name,age,balance\n1,Alice,30,1234.50\n2,Bob,,2500.00\n3,Charlie,42,\n",
        encoding="utf-8",
    )
    return p


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_validate_config_requires_file_path():
    c = CSVConnector({})
    errs = c.validate_config()
    assert any(e["field"] == "file_path" for e in errs)


def test_test_connection_success_for_real_file(sample_csv: Path):
    c = CSVConnector({"file_path": str(sample_csv)})
    ok, msg, details = _run(c.test_connection())
    assert ok is True
    assert details is not None
    assert details["size_bytes"] > 0


def test_test_connection_reports_dataset_not_found(tmp_path: Path):
    c = CSVConnector({"file_path": str(tmp_path / "nope.csv")})
    ok, _msg, details = _run(c.test_connection())
    assert ok is False
    assert details and details["error_code"] == "DATASET_NOT_FOUND"


def test_test_connection_reports_dataset_empty(tmp_path: Path):
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    c = CSVConnector({"file_path": str(p)})
    ok, _msg, details = _run(c.test_connection())
    assert ok is False
    assert details and details["error_code"] == "DATASET_EMPTY"


def test_test_connection_rejects_unsupported_extension(tmp_path: Path):
    p = tmp_path / "data.xlsx"
    p.write_text("not really excel", encoding="utf-8")
    c = CSVConnector({"file_path": str(p)})
    ok, _msg, details = _run(c.test_connection())
    assert ok is False
    assert details and details["error_code"] == "UNSUPPORTED_FILE_TYPE"


def test_preview_dataset_returns_records_with_nan_as_none(sample_csv: Path):
    c = CSVConnector({"file_path": str(sample_csv)})
    rows = _run(c.preview_dataset(table_name="customers", limit=10))
    assert len(rows) == 3
    # Bob's age was missing → None
    assert rows[1]["age"] is None
    # Charlie's balance was missing → None
    assert rows[2]["balance"] is None


def test_preview_dataset_caps_at_hard_cap(sample_csv: Path):
    c = CSVConnector({"file_path": str(sample_csv)})
    # Asking for absurdly large should clamp to hard cap, then to file size.
    rows = _run(c.preview_dataset(table_name="customers", limit=PREVIEW_ROW_HARD_CAP * 2))
    # Real file has 3 rows; cap clamp should not error and just return all 3.
    assert len(rows) == 3


def test_preview_dataset_zero_limit_returns_empty(sample_csv: Path):
    c = CSVConnector({"file_path": str(sample_csv)})
    rows = _run(c.preview_dataset(table_name="customers", limit=0))
    assert rows == []


def test_get_columns_infers_logical_types(sample_csv: Path):
    c = CSVConnector({"file_path": str(sample_csv)})
    cols = _run(c.get_columns(table_name="customers"))
    types = {col["column_name"]: col["column_type"] for col in cols}
    assert types["id"] == "integer"
    assert types["name"] == "string"
    # age has a NaN → pandas reads as float
    assert types["age"] in ("integer", "float")
    assert types["balance"] in ("integer", "float")


def test_get_columns_marks_nullable_when_nan_present(sample_csv: Path):
    c = CSVConnector({"file_path": str(sample_csv)})
    cols = _run(c.get_columns(table_name="customers"))
    by_name = {col["column_name"]: col for col in cols}
    assert by_name["age"]["is_nullable"] is True
    assert by_name["id"]["is_nullable"] is False


def test_get_row_count_excludes_header(sample_csv: Path):
    c = CSVConnector({"file_path": str(sample_csv)})
    count = _run(c.get_row_count(table_name="customers"))
    assert count == 3


def test_discover_files_returns_single_entry(sample_csv: Path):
    c = CSVConnector({"file_path": str(sample_csv)})
    files = _run(c.discover_files())
    assert len(files) == 1
    assert files[0]["name"] == "customers.csv"
    assert files[0]["format"] == "csv"


def test_get_schemas_returns_default(sample_csv: Path):
    c = CSVConnector({"file_path": str(sample_csv)})
    assert _run(c.get_schemas()) == ["default"]


def test_get_tables_returns_one_pseudo_table(sample_csv: Path):
    c = CSVConnector({"file_path": str(sample_csv)})
    tables = _run(c.get_tables())
    assert len(tables) == 1
    assert tables[0]["table_name"] == "customers"
    assert tables[0]["schema_name"] == "default"


def test_normalize_error_file_not_found():
    c = CSVConnector({"file_path": "/nonexistent.csv"})
    err = c.normalize_error(FileNotFoundError("No such file: /x"))
    assert err.code == "DATASET_NOT_FOUND"


def test_normalize_error_permission_denied():
    c = CSVConnector({"file_path": "/x.csv"})
    err = c.normalize_error(PermissionError("denied"))
    assert err.code == "CONNECTION_PERMISSION_DENIED"


def test_normalize_error_unicode_decode():
    c = CSVConnector({"file_path": "/x.csv"})
    exc = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
    err = c.normalize_error(exc)
    assert err.code == "FILE_PARSE_ERROR"


def test_normalize_error_unsupported_file_type():
    c = CSVConnector({"file_path": "/x.csv"})
    err = c.normalize_error(ValueError("Unsupported file type: .xyz"))
    assert err.code == "UNSUPPORTED_FILE_TYPE"


def test_resolve_path_rejects_escape_attempt(tmp_path: Path, monkeypatch):
    """Relative paths with ../../ that escape UPLOAD_DIR are rejected."""
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    from app.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_root))

    c = CSVConnector({"file_path": "../../etc/passwd"})
    with pytest.raises(PermissionError):
        c._resolve_path()


def test_relative_path_resolves_under_upload_dir(tmp_path: Path, monkeypatch):
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    f = upload_root / "data.csv"
    f.write_text("a,b\n1,2\n", encoding="utf-8")
    from app.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_root))

    c = CSVConnector({"file_path": "data.csv"})
    resolved = c._resolve_path()
    assert resolved == f.resolve()


def test_custom_delimiter_tsv(tmp_path: Path):
    p = tmp_path / "data.tsv"
    p.write_text("col1\tcol2\nv1\tv2\n", encoding="utf-8")
    c = CSVConnector({"file_path": str(p), "delimiter": "\t"})
    rows = _run(c.preview_dataset(table_name="data", limit=10))
    assert rows == [{"col1": "v1", "col2": "v2"}]


def test_has_header_false_uses_positional_columns(tmp_path: Path):
    p = tmp_path / "noheader.csv"
    p.write_text("1,Alice\n2,Bob\n", encoding="utf-8")
    c = CSVConnector({"file_path": str(p), "has_header": False})
    cols = _run(c.get_columns(table_name="noheader"))
    # pandas uses 0,1,... as column names; map_pandas treats them as ints → string label
    assert len(cols) == 2


def test_registry_marks_csv_as_ready():
    """Sanity: registry should now expose CSV as a READY connector."""
    from app.services.datasources.connectors.registry import (
        ConnectorStatus,
        registry,
    )

    spec = registry.get("csv")
    assert spec is not None
    assert spec.status == ConnectorStatus.READY
    assert any(f.name == "file_path" for f in spec.credential_schema)
