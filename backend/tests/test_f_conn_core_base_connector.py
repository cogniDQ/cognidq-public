"""
F-CONN-CORE — BaseConnector spec §10.2 surface tests.

Verifies the concrete defaults added to ``BaseConnector``:
  - validate_config (uses registry credential schema)
  - discover_schemas / discover_tables / discover_files / discover_assets
  - preview_dataset (delegates to get_sample_data)
  - register_dataset / execute_check (NotImplementedError stubs)
  - normalize_error (maps exceptions to spec §13.4 codes; never leaks creds)

Also checks legacy abstract methods still required, and that
PostgreSQLConnector picks up the new surface via inheritance.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest
from app.services.datasources.connectors.base import (
    BaseConnector,
    NormalizedConnectorError,
)

# ─── Fake subclass that satisfies the legacy abstract surface ───────────────


class FakeConnector(BaseConnector):
    """Minimal subclass for testing the spec §10.2 defaults."""

    connector_type = "postgresql"  # use real registry entry for validate_config

    def __init__(self, cfg: dict[str, Any] | None = None):
        super().__init__(cfg or {})
        self._schemas = ["public", "analytics"]
        self._tables = [{"schema_name": "public", "table_name": "users"}]
        self._sample_rows = [{"id": 1, "name": "ada"}, {"id": 2, "name": "grace"}]

    async def test_connection(self) -> tuple[bool, str, dict[str, Any] | None]:
        return True, "ok", None

    async def connect(self):  # noqa: D401
        self.connection = object()

    async def disconnect(self):
        self.connection = None

    async def get_schemas(self) -> list[str]:
        return list(self._schemas)

    async def get_tables(self, schema_name: str | None = None) -> list[dict[str, Any]]:
        return list(self._tables)

    async def get_columns(
        self, table_name: str, schema_name: str | None = None
    ) -> list[dict[str, Any]]:
        return [{"column_name": "id", "column_type": "int"}]

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return list(self._sample_rows)

    async def get_row_count(self, table_name: str, schema_name: str | None = None) -> int:
        return len(self._sample_rows)


class FileOnlyConnector(FakeConnector):
    """Pretends to be a file connector — schemas/tables not supported."""

    async def get_schemas(self) -> list[str]:
        raise NotImplementedError

    async def get_tables(self, schema_name=None):
        raise NotImplementedError

    async def discover_files(self, path=None):
        return [{"path": "/data/sales.csv", "size": 1024}]


# ─── validate_config ─────────────────────────────────────────────────────────


class TestValidateConfig:
    def test_missing_required_fields_reported(self):
        c = FakeConnector(cfg={})
        errors = c.validate_config()
        fields = {e["field"] for e in errors}
        # postgres registry schema requires host/port/database/username/password
        assert {"host", "port", "database", "username", "password"} <= fields

    def test_empty_string_treated_as_missing(self):
        c = FakeConnector(
            cfg={
                "host": "",
                "port": 5432,
                "database": "db",
                "username": "u",
                "password": "p",
            }
        )
        errors = c.validate_config()
        assert any(e["field"] == "host" for e in errors)
        assert not any(e["field"] == "username" for e in errors)

    def test_complete_config_valid(self):
        c = FakeConnector(
            cfg={
                "host": "localhost",
                "port": 5432,
                "database": "db",
                "username": "u",
                "password": "p",
            }
        )
        assert c.validate_config() == []

    def test_optional_fields_not_required(self):
        # ssl_mode is optional in the postgres registry schema
        c = FakeConnector(
            cfg={
                "host": "h",
                "port": 1,
                "database": "d",
                "username": "u",
                "password": "p",
            }
        )
        errors = c.validate_config()
        assert not any(e["field"] == "ssl_mode" for e in errors)

    def test_no_connector_type_skips_validation(self):
        class Anon(FakeConnector):
            connector_type = None

        assert Anon().validate_config() == []


# ─── discover_* defaults ─────────────────────────────────────────────────────


class TestDiscoverDefaults:
    @pytest.mark.asyncio
    async def test_discover_schemas_delegates(self):
        c = FakeConnector()
        assert await c.discover_schemas() == ["public", "analytics"]

    @pytest.mark.asyncio
    async def test_discover_tables_delegates(self):
        c = FakeConnector()
        result = await c.discover_tables(schema_name="public")
        assert result[0]["table_name"] == "users"

    @pytest.mark.asyncio
    async def test_discover_files_unsupported_by_default(self):
        c = FakeConnector()
        with pytest.raises(NotImplementedError):
            await c.discover_files()

    @pytest.mark.asyncio
    async def test_discover_assets_aggregates_supported_surfaces(self):
        c = FakeConnector()
        result = await c.discover_assets()
        # DB connector exposes schemas + tables; files raises and is skipped.
        assert "schemas" in result
        assert "tables" in result
        assert "files" not in result

    @pytest.mark.asyncio
    async def test_discover_assets_for_file_connector(self):
        c = FileOnlyConnector()
        result = await c.discover_assets()
        # File connector skips schemas/tables and returns only files.
        assert "schemas" not in result
        assert "tables" not in result
        assert result["files"][0]["path"] == "/data/sales.csv"


# ─── preview_dataset ─────────────────────────────────────────────────────────


class TestPreviewDataset:
    @pytest.mark.asyncio
    async def test_preview_returns_sample_rows(self):
        c = FakeConnector()
        rows = await c.preview_dataset("users", schema_name="public", limit=10)
        assert len(rows) == 2
        assert rows[0]["name"] == "ada"


# ─── Stub methods ────────────────────────────────────────────────────────────


class TestStubMethods:
    def test_register_dataset_raises(self):
        with pytest.raises(NotImplementedError, match="register_dataset"):
            FakeConnector().register_dataset()

    @pytest.mark.asyncio
    async def test_execute_check_raises(self):
        with pytest.raises(NotImplementedError, match="execute_check"):
            await FakeConnector().execute_check()


# ─── normalize_error ─────────────────────────────────────────────────────────


class TestNormalizeError:
    @pytest.mark.parametrize(
        "exc_msg,expected_code",
        [
            ("FATAL: password authentication failed for user 'x'", "CONNECTION_AUTH_FAILED"),
            ("Authentication failed", "CONNECTION_AUTH_FAILED"),
            ("Login failed for user 'x'", "CONNECTION_AUTH_FAILED"),
            ("Permission denied for relation users", "CONNECTION_PERMISSION_DENIED"),
            ("not authorized to access this resource", "CONNECTION_PERMISSION_DENIED"),
            ("connection timed out", "CONNECTION_TIMEOUT"),
            ("Operation timeout after 30s", "CONNECTION_TIMEOUT"),
            ("could not connect to server: Connection refused", "CONNECTION_NETWORK_ERROR"),
            ("could not translate host name 'foo' to address", "CONNECTION_NETWORK_ERROR"),
            ("network is unreachable", "CONNECTION_NETWORK_ERROR"),
            ("SSL handshake failed", "CONNECTION_INVALID_CONFIG"),
            ("Some random failure", "CONNECTION_INVALID_CONFIG"),
        ],
    )
    def test_message_pattern_mapping(self, exc_msg, expected_code):
        c = FakeConnector()
        result = c.normalize_error(RuntimeError(exc_msg))
        assert isinstance(result, NormalizedConnectorError)
        assert result.code == expected_code

    def test_secret_in_config_not_leaked(self):
        c = FakeConnector(cfg={"password": "super-secret-123"})
        result = c.normalize_error(RuntimeError("auth failed"))
        # The credential must never be embedded in the normalized message.
        assert "super-secret-123" not in result.message
        assert "super-secret-123" not in result.to_dict()["message"]

    def test_message_truncated(self):
        c = FakeConnector()
        result = c.normalize_error(RuntimeError("x" * 5000))
        assert len(result.message) == 500

    def test_to_dict_shape(self):
        c = FakeConnector()
        d = c.normalize_error(RuntimeError("auth failed")).to_dict()
        assert set(d.keys()) == {"code", "message"}


# ─── PostgreSQLConnector wiring ──────────────────────────────────────────────


class TestPostgreSQLWiring:
    def test_connector_type_is_set(self):
        from app.services.datasources.connectors.postgresql import (
            PostgreSQLConnector,
        )

        assert PostgreSQLConnector.connector_type == "postgresql"

    def test_postgresql_validate_config_uses_registry(self):
        from app.services.datasources.connectors.postgresql import (
            PostgreSQLConnector,
        )

        c = PostgreSQLConnector({})
        errors = c.validate_config()
        assert any(e["field"] == "host" for e in errors)
