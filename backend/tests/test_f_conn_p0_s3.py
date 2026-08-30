"""
F-CONN-P0-LOCAL — S3 / MinIO connector unit tests.

The S3 connector talks to a real bucket via the ``minio`` SDK; for unit
tests we patch ``minio.Minio`` with a stub that returns canned responses
and tracks the calls. Format-specific delegation (CSV / Parquet / JSON)
goes through real connectors against tmp-path files, so we cover the
whole download → preview path without the network.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest
from app.services.datasources.connectors.registry import (
    ConnectorStatus,
    registry,
)
from app.services.datasources.connectors.s3_connector import S3Connector


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# Fake Minio client
# ─────────────────────────────────────────────────────────────────────────────


class _FakeObj:
    def __init__(self, key: str, size: int):
        self.object_name = key
        self.size = size


class FakeMinio:
    """A minimal Minio drop-in that backs all reads with a local directory.

    Pass ``files`` as a dict of ``object_key -> local_disk_path``. Methods
    used by S3Connector:
      - ``bucket_exists(bucket)``
      - ``list_objects(bucket, prefix=, recursive=)``
      - ``fget_object(bucket, key, dest_path)``
    """

    def __init__(self, files: dict[str, Path], *, bucket_name: str = "demo"):
        self._files = files
        self._bucket_name = bucket_name
        self.calls: list[str] = []

    def bucket_exists(self, bucket: str) -> bool:
        self.calls.append(f"bucket_exists:{bucket}")
        return bucket == self._bucket_name

    def list_objects(self, bucket: str, prefix: str = "", recursive: bool = True):
        self.calls.append(f"list_objects:{bucket}:{prefix}")
        for key, src in self._files.items():
            if not key.startswith(prefix):
                continue
            yield _FakeObj(key, os.path.getsize(src))

    def fget_object(self, bucket: str, key: str, dest_path: str) -> None:
        self.calls.append(f"fget_object:{bucket}:{key}")
        src = self._files[key]
        shutil.copyfile(src, dest_path)


def _patched(connector: S3Connector, fake: FakeMinio):
    return patch.object(connector, "_client", return_value=fake)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def csv_obj(tmp_path: Path) -> Path:
    p = tmp_path / "customers.csv"
    p.write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf-8")
    return p


@pytest.fixture
def jsonl_obj(tmp_path: Path) -> Path:
    p = tmp_path / "events.ndjson"
    p.write_text(
        "\n".join(
            [
                json.dumps({"id": 1, "type": "click"}),
                json.dumps({"id": 2, "type": "view"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def parquet_obj(tmp_path: Path) -> Path:
    import pandas as pd
    import pyarrow as pa  # type: ignore
    import pyarrow.parquet as pq  # type: ignore

    p = tmp_path / "events.parquet"
    df = pd.DataFrame({"id": [1, 2, 3], "v": [0.1, 0.2, 0.3]})
    pq.write_table(pa.Table.from_pandas(df), p)
    return p


def _connector(bucket: str = "demo", **overrides) -> S3Connector:
    cfg = {
        "endpoint_url": "http://minio:9000",
        "bucket": bucket,
        "access_key_id": "minio",
        "secret_access_key": "minio12345",
        "secure": False,
    }
    cfg.update(overrides)
    return S3Connector(cfg)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestS3TestConnection:
    def test_bucket_exists_returns_true(self, csv_obj: Path):
        c = _connector()
        fake = FakeMinio({"customers.csv": csv_obj})
        with _patched(c, fake):
            ok, _msg, details = _run(c.test_connection())
        assert ok is True
        assert details and details["bucket"] == "demo"

    def test_missing_bucket_returns_dataset_not_found(self, csv_obj: Path):
        c = _connector(bucket="other")
        fake = FakeMinio({"customers.csv": csv_obj}, bucket_name="demo")
        with _patched(c, fake):
            ok, _msg, details = _run(c.test_connection())
        assert ok is False
        assert details and details["error_code"] == "DATASET_NOT_FOUND"

    def test_missing_bucket_field_returns_invalid_config(self):
        c = S3Connector(
            {
                "endpoint_url": "http://minio:9000",
                "access_key_id": "x",
                "secret_access_key": "y",
            }
        )
        ok, _msg, details = _run(c.test_connection())
        assert ok is False
        assert details and details["error_code"] == "CONNECTION_INVALID_CONFIG"

    def test_missing_credentials_returns_invalid_config(self):
        c = S3Connector(
            {
                "endpoint_url": "http://minio:9000",
                "bucket": "demo",
            }
        )
        ok, _msg, details = _run(c.test_connection())
        assert ok is False
        assert details and details["error_code"] == "CONNECTION_INVALID_CONFIG"


class TestS3Discovery:
    def test_discover_files_filters_by_extension_and_prefix(self, csv_obj: Path, parquet_obj: Path):
        c = _connector(prefix="datasets/")
        fake = FakeMinio(
            {
                "datasets/customers.csv": csv_obj,
                "datasets/events.parquet": parquet_obj,
                "logs/ignore.log": csv_obj,  # wrong extension → filtered
                "ignored/customers.csv": csv_obj,  # wrong prefix
            }
        )
        with _patched(c, fake):
            files = _run(c.discover_files())
        names = sorted(f["name"] for f in files)
        assert names == ["customers.csv", "events.parquet"]

    def test_get_tables_maps_objects(self, csv_obj: Path):
        c = _connector()
        fake = FakeMinio({"customers.csv": csv_obj})
        with _patched(c, fake):
            tables = _run(c.get_tables())
        assert len(tables) == 1
        assert tables[0]["table_name"] == "customers.csv"
        assert tables[0]["metadata"]["object_key"] == "customers.csv"


class TestS3Preview:
    def test_preview_csv_object(self, csv_obj: Path):
        c = _connector()
        fake = FakeMinio({"customers.csv": csv_obj})
        with _patched(c, fake):
            rows = _run(c.preview_dataset(table_name="customers.csv", limit=10))
        assert rows == [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

    def test_preview_parquet_object(self, parquet_obj: Path):
        c = _connector()
        fake = FakeMinio({"events.parquet": parquet_obj})
        with _patched(c, fake):
            rows = _run(c.preview_dataset(table_name="events.parquet", limit=10))
        assert len(rows) == 3
        assert rows[0]["id"] == 1

    def test_preview_jsonl_object(self, jsonl_obj: Path):
        c = _connector()
        fake = FakeMinio({"events.ndjson": jsonl_obj})
        with _patched(c, fake):
            rows = _run(c.preview_dataset(table_name="events.ndjson", limit=10))
        assert len(rows) == 2
        assert rows[1]["type"] == "view"

    def test_preview_zero_limit_returns_empty(self, csv_obj: Path):
        c = _connector()
        fake = FakeMinio({"customers.csv": csv_obj})
        with _patched(c, fake):
            assert _run(c.preview_dataset(table_name="customers.csv", limit=0)) == []

    def test_get_columns_delegates_to_format(self, csv_obj: Path):
        c = _connector()
        fake = FakeMinio({"customers.csv": csv_obj})
        with _patched(c, fake):
            cols = _run(c.get_columns(table_name="customers.csv"))
        names = sorted(c["column_name"] for c in cols)
        assert names == ["id", "name"]


class TestS3ErrorMapping:
    def test_signature_mismatch_to_auth_failed(self):
        c = _connector()
        err = c.normalize_error(Exception("S3Error: SignatureDoesNotMatch"))
        assert err.code == "CONNECTION_AUTH_FAILED"

    def test_no_such_bucket_to_dataset_not_found(self):
        c = _connector()
        err = c.normalize_error(Exception("NoSuchBucket"))
        assert err.code == "DATASET_NOT_FOUND"

    def test_access_denied_to_permission_denied(self):
        c = _connector()
        err = c.normalize_error(Exception("AccessDenied"))
        assert err.code == "CONNECTION_PERMISSION_DENIED"

    def test_connection_refused_to_network_error(self):
        c = _connector()
        err = c.normalize_error(Exception("connection refused"))
        assert err.code == "CONNECTION_NETWORK_ERROR"


class TestS3EndpointParsing:
    def test_https_endpoint_marks_secure(self):
        c = _connector(endpoint_url="https://s3.amazonaws.com")
        host, secure = c._endpoint_and_scheme()
        assert host == "s3.amazonaws.com"
        assert secure is True

    def test_http_endpoint_marks_insecure(self):
        c = _connector(endpoint_url="http://minio:9000")
        host, secure = c._endpoint_and_scheme()
        assert host == "minio:9000"
        assert secure is False

    def test_no_endpoint_defaults_to_aws(self):
        c = S3Connector(
            {
                "bucket": "demo",
                "access_key_id": "x",
                "secret_access_key": "y",
            }
        )
        host, _ = c._endpoint_and_scheme()
        assert host == "s3.amazonaws.com"


class TestS3Registry:
    def test_registry_marks_s3_ready(self):
        spec = registry.get("s3")
        assert spec is not None
        assert spec.status == ConnectorStatus.READY
        names = {f.name for f in spec.credential_schema}
        assert {"bucket", "access_key_id", "secret_access_key"} <= names

    def test_factory_wires_s3_connector(self, csv_obj: Path):
        from app.services.datasources.connection_manager import ConnectionManager

        # connect() calls _client(), which constructs a Minio object — patch
        # the class to avoid an outbound DNS lookup.
        with patch(
            "app.services.datasources.connectors.s3_connector.Minio",
            create=True,
        ) as fake_minio_cls:
            fake_minio_cls.return_value = object()  # any non-None
            c = _run(
                ConnectionManager.get_connector(
                    "s3",
                    {
                        "bucket": "demo",
                        "access_key_id": "x",
                        "secret_access_key": "y",
                    },
                )
            )
        assert isinstance(c, S3Connector)
