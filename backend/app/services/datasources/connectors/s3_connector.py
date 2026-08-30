"""
F-CONN-P0-LOCAL — S3 / MinIO object-storage connector (spec §7.1, §17, §19).

Talks S3 via the official ``minio`` SDK (works against AWS S3, MinIO, and
any S3-compatible service). Each connection is bound to a single bucket;
discovery returns objects under an optional prefix and treats supported file
extensions as logical "tables".

Spec contract
-------------
- ``connection_config`` keys:
    endpoint_url:       str   (optional; default AWS S3)
    region:             str   (optional)
    bucket:             str   (required)
    access_key_id:      str   (required)
    secret_access_key:  str   (required, secret)
    secure:             bool  (optional, default True; toggles HTTPS)
    prefix:             str   (optional; restricts discovery)
- One logical "schema" (``"default"``) and one logical "table" per
  discovered object whose extension is one of csv/tsv/parquet/jsonl/ndjson.
- Preview is delegated to the format-specific connector after streaming the
  object to a temporary file.
- ``normalize_error`` maps S3 errors (auth / not found / network) to spec
  §13.4 codes.

SECURITY
--------
The minio client uses TLS by default. Object preview downloads are written
to a per-call ``tempfile.NamedTemporaryFile`` inside the OS temp dir and
deleted promptly. Credentials are never echoed in error messages.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.datasources.connectors.base import (
    BaseConnector,
    NormalizedConnectorError,
)

_FILE_EXTENSIONS = (".csv", ".tsv", ".parquet", ".pq", ".jsonl", ".ndjson", ".json")
PREVIEW_ROW_HARD_CAP: int = 2_000_000


class S3Connector(BaseConnector):
    """S3 / MinIO object-storage connector."""

    connector_type = "s3"

    # ── lifecycle ───────────────────────────────────────────────────────────

    async def test_connection(self) -> tuple[bool, str, dict[str, Any] | None]:
        cfg = self.connection_config or {}
        bucket = cfg.get("bucket")
        if not bucket:
            return False, "bucket is required.", {"error_code": "CONNECTION_INVALID_CONFIG"}

        try:
            client = self._client()
        except ValueError as exc:
            return False, str(exc), {"error_code": "CONNECTION_INVALID_CONFIG"}
        except Exception as exc:
            return False, str(exc), {"error_code": "CONNECTION_NETWORK_ERROR"}

        try:
            exists = client.bucket_exists(bucket)
        except Exception as exc:
            err = self.normalize_error(exc)
            return False, err.message, {"error_code": err.code}

        if not exists:
            return (
                False,
                f"Bucket {bucket!r} does not exist or is not accessible.",
                {"error_code": "DATASET_NOT_FOUND"},
            )

        return (
            True,
            f"Bucket {bucket!r} is reachable.",
            {"bucket": bucket, "endpoint": self._endpoint_host()},
        )

    async def connect(self) -> None:
        self.connection = self._client()

    async def disconnect(self) -> None:
        self.connection = None

    # ── §10.2 + legacy discovery ────────────────────────────────────────────

    async def get_schemas(self) -> list[str]:
        return ["default"]

    async def get_tables(self, schema_name: str | None = None) -> list[dict[str, Any]]:
        objs = await self.discover_files()
        return [
            {
                "schema_name": "default",
                "table_name": obj["name"],
                "row_count": None,
                "metadata": {
                    "object_key": obj["path"],
                    "size_bytes": obj["size_bytes"],
                    "format": obj["format"],
                },
            }
            for obj in objs
        ]

    async def discover_files(self, path: str | None = None) -> list[dict[str, Any]]:
        """List objects under the configured prefix that have a known data
        extension."""
        cfg = self.connection_config or {}
        bucket = cfg["bucket"]
        prefix = path if path is not None else (cfg.get("prefix") or "")

        client = self._client()
        out: list[dict[str, Any]] = []
        for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
            name = obj.object_name or ""
            if name.endswith("/"):
                continue
            suffix = Path(name).suffix.lower()
            if suffix not in _FILE_EXTENSIONS:
                continue
            out.append(
                {
                    "name": Path(name).name,
                    "path": name,
                    "size_bytes": int(getattr(obj, "size", 0) or 0),
                    "format": suffix.lstrip("."),
                }
            )
        return out

    async def get_columns(
        self, table_name: str, schema_name: str | None = None
    ) -> list[dict[str, Any]]:
        with self._download(table_name) as local_path:
            return await self._delegate(local_path, "get_columns", table_name)

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "S3 connector does not support SQL execution; preview the object instead."
        )

    async def get_row_count(self, table_name: str, schema_name: str | None = None) -> int:
        with self._download(table_name) as local_path:
            return await self._delegate(local_path, "get_row_count", table_name)

    async def preview_dataset(
        self,
        table_name: str,
        schema_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        capped = min(max(0, int(limit)), PREVIEW_ROW_HARD_CAP)
        if capped == 0:
            return []
        with self._download(table_name) as local_path:
            return await self._delegate(local_path, "preview_dataset", table_name, limit=capped)

    # ── error mapping ───────────────────────────────────────────────────────

    def normalize_error(self, exc: BaseException) -> NormalizedConnectorError:
        raw = str(exc) or type(exc).__name__
        lowered = raw.lower()

        if "signaturedoesnotmatch" in lowered or "invalidaccesskey" in lowered:
            return NormalizedConnectorError(
                code="CONNECTION_AUTH_FAILED", message=raw[:500], original=exc
            )
        if "accessdenied" in lowered or "access denied" in lowered:
            return NormalizedConnectorError(
                code="CONNECTION_PERMISSION_DENIED",
                message=raw[:500],
                original=exc,
            )
        if "nosuchbucket" in lowered or "nosuchkey" in lowered:
            return NormalizedConnectorError(
                code="DATASET_NOT_FOUND", message=raw[:500], original=exc
            )
        if (
            "could not connect" in lowered
            or "connection refused" in lowered
            or "name or service not known" in lowered
            or "max retries" in lowered
        ):
            return NormalizedConnectorError(
                code="CONNECTION_NETWORK_ERROR",
                message=raw[:500],
                original=exc,
            )
        return super().normalize_error(exc)

    # ── helpers ─────────────────────────────────────────────────────────────

    def _client(self):
        from minio import Minio  # type: ignore

        cfg = self.connection_config or {}
        access = cfg.get("access_key_id")
        secret = cfg.get("secret_access_key")
        if not access or not secret:
            raise ValueError("access_key_id and secret_access_key are required.")

        endpoint, secure = self._endpoint_and_scheme()
        return Minio(
            endpoint,
            access_key=access,
            secret_key=secret,
            secure=secure,
            region=cfg.get("region") or None,
        )

    def _endpoint_and_scheme(self) -> tuple[str, bool]:
        cfg = self.connection_config or {}
        url = cfg.get("endpoint_url")
        secure_default = bool(cfg.get("secure", True))
        if not url:
            # Default to AWS S3.
            return "s3.amazonaws.com", secure_default
        parsed = urlparse(url)
        if parsed.scheme:
            host = parsed.netloc or parsed.path
            secure = parsed.scheme.lower() == "https"
        else:
            host = url
            secure = secure_default
        if not host:
            raise ValueError("endpoint_url could not be parsed.")
        return host, secure

    def _endpoint_host(self) -> str:
        return self._endpoint_and_scheme()[0]

    @contextmanager
    def _download(self, object_key: str):
        """Stream an object to a temp file and yield its path."""
        cfg = self.connection_config or {}
        bucket = cfg["bucket"]
        client = self._client()
        suffix = Path(object_key).suffix or ".bin"
        fh = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        fh.close()
        try:
            client.fget_object(bucket, object_key, fh.name)
            yield Path(fh.name)
        finally:
            try:
                os.unlink(fh.name)
            except OSError:
                pass

    async def _delegate(
        self,
        local_path: Path,
        method_name: str,
        table_name: str,
        **kwargs,
    ):
        """Hand off to the file-format connector matching the object's suffix."""
        from app.services.datasources.connectors.csv_connector import CSVConnector
        from app.services.datasources.connectors.json_connector import JSONConnector
        from app.services.datasources.connectors.parquet_connector import (
            ParquetConnector,
        )

        suffix = local_path.suffix.lower()
        if suffix in (".csv", ".tsv"):
            sub = CSVConnector({"file_path": str(local_path)})
        elif suffix in (".parquet", ".pq"):
            sub = ParquetConnector({"file_path": str(local_path)})
        elif suffix in (".json", ".jsonl", ".ndjson"):
            sub = JSONConnector({"file_path": str(local_path)})
        else:
            raise ValueError(f"Unsupported S3 object type: {suffix}")

        method = getattr(sub, method_name)
        # All §10.2 methods take (table_name, schema_name=None, ...).
        if method_name == "preview_dataset":
            return await method(table_name=table_name, **kwargs)
        return await method(table_name=table_name)
