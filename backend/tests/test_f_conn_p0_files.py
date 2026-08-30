"""
F-CONN-P0-LOCAL — Excel / JSON / Parquet connector unit tests.

Each connector is exercised end-to-end with a real on-disk file built in a
``tmp_path`` fixture: test_connection happy + sad paths, discovery,
preview (with NaN scrubbing), get_columns type inference, get_row_count,
normalize_error, and registry promotion to READY.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from app.services.datasources.connectors.excel_connector import ExcelConnector
from app.services.datasources.connectors.json_connector import JSONConnector
from app.services.datasources.connectors.parquet_connector import ParquetConnector
from app.services.datasources.connectors.registry import (
    ConnectorStatus,
    registry,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_xlsx(tmp_path: Path) -> Path:
    import openpyxl  # type: ignore

    p = tmp_path / "orders.xlsx"
    wb = openpyxl.Workbook()
    s1 = wb.active
    s1.title = "orders"
    s1.append(["id", "customer", "total"])
    s1.append([1, "Alice", 99.5])
    s1.append([2, "Bob", None])
    s1.append([3, "Charlie", 12.0])

    s2 = wb.create_sheet(title="customers")
    s2.append(["id", "name"])
    s2.append([10, "Acme"])
    s2.append([11, "Globex"])

    wb.save(p)
    return p


@pytest.fixture
def sample_ndjson(tmp_path: Path) -> Path:
    p = tmp_path / "events.ndjson"
    p.write_text(
        "\n".join(
            [
                json.dumps({"id": 1, "user": "alice", "amount": 10.5}),
                json.dumps({"id": 2, "user": "bob", "amount": None}),
                json.dumps({"id": 3, "user": "carol", "amount": 7.25}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def sample_json_array(tmp_path: Path) -> Path:
    p = tmp_path / "items.json"
    p.write_text(
        json.dumps(
            [
                {"sku": "A", "qty": 1, "in_stock": True},
                {"sku": "B", "qty": 2, "in_stock": False},
            ]
        ),
        encoding="utf-8",
    )
    return p


@pytest.fixture
def sample_parquet(tmp_path: Path) -> Path:
    import pandas as pd
    import pyarrow as pa  # type: ignore
    import pyarrow.parquet as pq  # type: ignore

    p = tmp_path / "events.parquet"
    df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "name": ["a", "b", "c", "d"],
            "value": [1.5, 2.5, None, 4.5],
            "active": [True, False, True, False],
        }
    )
    pq.write_table(pa.Table.from_pandas(df), p)
    return p


# ─────────────────────────────────────────────────────────────────────────────
# Excel
# ─────────────────────────────────────────────────────────────────────────────


class TestExcelConnector:
    def test_test_connection_success(self, sample_xlsx: Path):
        c = ExcelConnector({"file_path": str(sample_xlsx)})
        ok, _msg, details = _run(c.test_connection())
        assert ok is True
        assert details and details["sheet_count"] == 2

    def test_test_connection_dataset_not_found(self, tmp_path: Path):
        c = ExcelConnector({"file_path": str(tmp_path / "missing.xlsx")})
        ok, _msg, details = _run(c.test_connection())
        assert ok is False
        assert details and details["error_code"] == "DATASET_NOT_FOUND"

    def test_test_connection_unsupported_extension(self, tmp_path: Path):
        p = tmp_path / "data.csv"
        p.write_text("a,b\n1,2\n", encoding="utf-8")
        c = ExcelConnector({"file_path": str(p)})
        ok, _msg, details = _run(c.test_connection())
        assert ok is False
        assert details and details["error_code"] == "UNSUPPORTED_FILE_TYPE"

    def test_get_tables_returns_each_sheet(self, sample_xlsx: Path):
        c = ExcelConnector({"file_path": str(sample_xlsx)})
        tables = _run(c.get_tables())
        names = sorted(t["table_name"] for t in tables)
        assert names == ["customers", "orders"]

    def test_preview_dataset_returns_rows_with_nan_as_none(self, sample_xlsx: Path):
        c = ExcelConnector({"file_path": str(sample_xlsx)})
        rows = _run(c.preview_dataset(table_name="orders", limit=10))
        assert len(rows) == 3
        # Bob's total was missing → None
        assert rows[1]["total"] is None

    def test_preview_dataset_zero_limit(self, sample_xlsx: Path):
        c = ExcelConnector({"file_path": str(sample_xlsx)})
        assert _run(c.preview_dataset(table_name="orders", limit=0)) == []

    def test_get_columns_infers_types(self, sample_xlsx: Path):
        c = ExcelConnector({"file_path": str(sample_xlsx)})
        cols = _run(c.get_columns(table_name="orders"))
        types = {col["column_name"]: col["column_type"] for col in cols}
        assert types["id"] == "integer"
        assert types["customer"] == "string"
        # total has a NaN → pandas reads as float
        assert types["total"] in ("integer", "float")

    def test_get_row_count(self, sample_xlsx: Path):
        c = ExcelConnector({"file_path": str(sample_xlsx)})
        assert _run(c.get_row_count(table_name="orders")) == 3

    def test_normalize_error_file_not_found(self):
        c = ExcelConnector({"file_path": "/x.xlsx"})
        err = c.normalize_error(FileNotFoundError("no such file"))
        assert err.code == "DATASET_NOT_FOUND"

    def test_normalize_error_bad_zip(self):
        c = ExcelConnector({"file_path": "/x.xlsx"})
        err = c.normalize_error(Exception("BadZipFile: not a zip file"))
        assert err.code == "FILE_PARSE_ERROR"

    def test_registry_marks_excel_ready(self):
        spec = registry.get("excel")
        assert spec is not None
        assert spec.status == ConnectorStatus.READY
        assert any(f.name == "file_path" for f in spec.credential_schema)


# ─────────────────────────────────────────────────────────────────────────────
# JSON
# ─────────────────────────────────────────────────────────────────────────────


class TestJSONConnector:
    def test_test_connection_ndjson(self, sample_ndjson: Path):
        c = JSONConnector({"file_path": str(sample_ndjson)})
        ok, _msg, details = _run(c.test_connection())
        assert ok is True
        assert details and details["shape"] == "ndjson"

    def test_test_connection_array(self, sample_json_array: Path):
        c = JSONConnector({"file_path": str(sample_json_array)})
        ok, _msg, details = _run(c.test_connection())
        assert ok is True
        assert details and details["shape"] == "array"

    def test_test_connection_dataset_not_found(self, tmp_path: Path):
        c = JSONConnector({"file_path": str(tmp_path / "missing.json")})
        ok, _msg, details = _run(c.test_connection())
        assert ok is False
        assert details and details["error_code"] == "DATASET_NOT_FOUND"

    def test_test_connection_dataset_empty(self, tmp_path: Path):
        p = tmp_path / "empty.json"
        p.write_text("", encoding="utf-8")
        c = JSONConnector({"file_path": str(p)})
        ok, _msg, details = _run(c.test_connection())
        assert ok is False
        assert details and details["error_code"] == "DATASET_EMPTY"

    def test_test_connection_parse_error(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("not really json", encoding="utf-8")
        c = JSONConnector({"file_path": str(p)})
        ok, _msg, details = _run(c.test_connection())
        assert ok is False
        assert details and details["error_code"] == "FILE_PARSE_ERROR"

    def test_preview_ndjson_rows_nan_as_none(self, sample_ndjson: Path):
        c = JSONConnector({"file_path": str(sample_ndjson)})
        rows = _run(c.preview_dataset(table_name="events", limit=10))
        assert len(rows) == 3
        assert rows[1]["amount"] is None

    def test_preview_array_rows(self, sample_json_array: Path):
        c = JSONConnector({"file_path": str(sample_json_array)})
        rows = _run(c.preview_dataset(table_name="items", limit=10))
        assert len(rows) == 2
        assert rows[0]["sku"] == "A"

    def test_preview_zero_limit(self, sample_ndjson: Path):
        c = JSONConnector({"file_path": str(sample_ndjson)})
        assert _run(c.preview_dataset(table_name="events", limit=0)) == []

    def test_get_columns_ndjson(self, sample_ndjson: Path):
        c = JSONConnector({"file_path": str(sample_ndjson)})
        cols = _run(c.get_columns(table_name="events"))
        names = {col["column_name"] for col in cols}
        assert names == {"id", "user", "amount"}

    def test_get_row_count_ndjson(self, sample_ndjson: Path):
        c = JSONConnector({"file_path": str(sample_ndjson)})
        assert _run(c.get_row_count(table_name="events")) == 3

    def test_normalize_error_decode_error(self):
        c = JSONConnector({"file_path": "/x.json"})
        err = c.normalize_error(json.JSONDecodeError("Expecting value", "x", 0))
        assert err.code == "FILE_PARSE_ERROR"

    def test_registry_marks_json_ready(self):
        spec = registry.get("json")
        assert spec is not None
        assert spec.status == ConnectorStatus.READY
        names = {f.name for f in spec.credential_schema}
        assert {"file_path", "encoding", "json_format"} <= names


# ─────────────────────────────────────────────────────────────────────────────
# Parquet
# ─────────────────────────────────────────────────────────────────────────────


class TestParquetConnector:
    def test_test_connection_success(self, sample_parquet: Path):
        c = ParquetConnector({"file_path": str(sample_parquet)})
        ok, _msg, details = _run(c.test_connection())
        assert ok is True
        assert details and details["num_rows"] == 4

    def test_test_connection_dataset_not_found(self, tmp_path: Path):
        c = ParquetConnector({"file_path": str(tmp_path / "missing.parquet")})
        ok, _msg, details = _run(c.test_connection())
        assert ok is False
        assert details and details["error_code"] == "DATASET_NOT_FOUND"

    def test_test_connection_unsupported_extension(self, tmp_path: Path):
        p = tmp_path / "data.csv"
        p.write_text("a,b\n1,2\n", encoding="utf-8")
        c = ParquetConnector({"file_path": str(p)})
        ok, _msg, details = _run(c.test_connection())
        assert ok is False
        assert details and details["error_code"] == "UNSUPPORTED_FILE_TYPE"

    def test_test_connection_corrupt_parquet(self, tmp_path: Path):
        p = tmp_path / "bad.parquet"
        p.write_text("not parquet", encoding="utf-8")
        c = ParquetConnector({"file_path": str(p)})
        ok, _msg, details = _run(c.test_connection())
        assert ok is False
        assert details and details["error_code"] == "FILE_PARSE_ERROR"

    def test_preview_rows_with_nan_as_none(self, sample_parquet: Path):
        c = ParquetConnector({"file_path": str(sample_parquet)})
        rows = _run(c.preview_dataset(table_name="events", limit=10))
        assert len(rows) == 4
        assert rows[2]["value"] is None

    def test_preview_zero_limit(self, sample_parquet: Path):
        c = ParquetConnector({"file_path": str(sample_parquet)})
        assert _run(c.preview_dataset(table_name="events", limit=0)) == []

    def test_get_columns_uses_arrow_schema(self, sample_parquet: Path):
        c = ParquetConnector({"file_path": str(sample_parquet)})
        cols = _run(c.get_columns(table_name="events"))
        types = {col["column_name"]: col["column_type"] for col in cols}
        assert types["id"] == "integer"
        assert types["name"] == "string"
        assert types["value"] == "float"
        assert types["active"] == "boolean"

    def test_get_row_count_from_metadata(self, sample_parquet: Path):
        c = ParquetConnector({"file_path": str(sample_parquet)})
        assert _run(c.get_row_count(table_name="events")) == 4

    def test_get_tables_includes_row_count(self, sample_parquet: Path):
        c = ParquetConnector({"file_path": str(sample_parquet)})
        tables = _run(c.get_tables())
        assert tables[0]["row_count"] == 4

    def test_normalize_error_file_not_found(self):
        c = ParquetConnector({"file_path": "/x.parquet"})
        err = c.normalize_error(FileNotFoundError("no such file"))
        assert err.code == "DATASET_NOT_FOUND"

    def test_registry_marks_parquet_ready(self):
        spec = registry.get("parquet")
        assert spec is not None
        assert spec.status == ConnectorStatus.READY
        assert any(f.name == "file_path" for f in spec.credential_schema)


# ─────────────────────────────────────────────────────────────────────────────
# Shared: ConnectionManager factory wires up new file connectors
# ─────────────────────────────────────────────────────────────────────────────


class TestConnectionManagerFactory:
    def test_get_connector_csv(self, tmp_path: Path):
        from app.services.datasources.connection_manager import ConnectionManager
        from app.services.datasources.connectors.csv_connector import CSVConnector

        p = tmp_path / "x.csv"
        p.write_text("a,b\n1,2\n", encoding="utf-8")
        c = _run(ConnectionManager.get_connector("csv", {"file_path": str(p)}))
        assert isinstance(c, CSVConnector)

    def test_get_connector_excel(self, sample_xlsx: Path):
        from app.services.datasources.connection_manager import ConnectionManager

        c = _run(ConnectionManager.get_connector("excel", {"file_path": str(sample_xlsx)}))
        assert isinstance(c, ExcelConnector)

    def test_get_connector_json(self, sample_ndjson: Path):
        from app.services.datasources.connection_manager import ConnectionManager

        c = _run(ConnectionManager.get_connector("json", {"file_path": str(sample_ndjson)}))
        assert isinstance(c, JSONConnector)

    def test_get_connector_parquet(self, sample_parquet: Path):
        from app.services.datasources.connection_manager import ConnectionManager

        c = _run(ConnectionManager.get_connector("parquet", {"file_path": str(sample_parquet)}))
        assert isinstance(c, ParquetConnector)
