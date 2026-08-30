"""
F072 P03 — Unit tests: SchemaInspector + BaseConnector

Tests refresh_schema, get_schema_metadata, get_preview_data, and base connector utilities.

P03-01 .. P03-15  (15 tests)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

SI_MODULE = "app.services.datasources.schema_inspector"
BASE_MODULE = "app.services.datasources.connectors.base"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_datasource(ds_id=None):
    ds = MagicMock()
    ds.id = ds_id or uuid.uuid4()
    ds.name = "test_ds"
    ds.type = "postgresql"
    ds.connection_config = {"host": "localhost", "password": "encrypted:abc"}
    return ds


def _mock_connector(schemas=None, tables=None, columns=None, sample_rows=None, row_count=100):
    """Build an AsyncMock connector with configurable return values."""
    c = AsyncMock()
    c.get_schemas = AsyncMock(return_value=schemas or ["public"])
    c.get_tables = AsyncMock(
        return_value=tables or [{"table_name": "users", "schema_name": "public"}]
    )
    c.get_columns = AsyncMock(
        return_value=columns
        or [
            {
                "column_name": "id",
                "column_type": "integer",
                "is_nullable": False,
                "is_primary_key": True,
                "default_value": None,
                "metadata": {},
            },
            {
                "column_name": "name",
                "column_type": "text",
                "is_nullable": True,
                "is_primary_key": False,
                "default_value": None,
                "metadata": {},
            },
        ]
    )
    c.get_sample_data = AsyncMock(return_value=sample_rows or [{"id": 1, "name": "Alice"}])
    c.get_row_count = AsyncMock(return_value=row_count)
    c.execute_query = AsyncMock(return_value=sample_rows or [{"id": 1, "name": "Alice"}])
    # Support async context manager
    c.__aenter__ = AsyncMock(return_value=c)
    c.__aexit__ = AsyncMock(return_value=None)
    return c


def _mock_schema_record(
    schema="public",
    table="users",
    col="id",
    col_type="integer",
    nullable=False,
    pk=True,
    refreshed=None,
):
    r = MagicMock()
    r.schema_name = schema
    r.table_name = table
    r.column_name = col
    r.column_type = col_type
    r.is_nullable = nullable
    r.is_primary_key = pk
    r.default_value = None
    r.meta_data = {}
    r.refreshed_at = refreshed or datetime.utcnow()
    return r


# ===================================================================
# REFRESH SCHEMA
# ===================================================================
class TestRefreshSchema:
    @pytest.mark.asyncio
    async def test_upserts_columns(self):
        """P03-01: Introspects connector and creates DataSourceSchema records"""
        ds = _mock_datasource()
        connector = _mock_connector()
        db = MagicMock()
        # No existing records
        db.query.return_value.filter.return_value.first.return_value = None

        with patch(f"{SI_MODULE}.ConnectionManager") as mock_cm:
            mock_cm.get_connector = AsyncMock(return_value=connector)
            from app.services.datasources.schema_inspector import SchemaInspector

            total = await SchemaInspector.refresh_schema(db, ds)

        assert total == 2  # 2 columns from mock
        assert db.add.call_count == 2
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_column_count(self):
        """P03-02: Returns total columns discovered"""
        ds = _mock_datasource()
        columns = [
            {
                "column_name": "a",
                "column_type": "int",
                "is_nullable": False,
                "is_primary_key": False,
            },
            {
                "column_name": "b",
                "column_type": "text",
                "is_nullable": True,
                "is_primary_key": False,
            },
            {
                "column_name": "c",
                "column_type": "date",
                "is_nullable": True,
                "is_primary_key": False,
            },
        ]
        connector = _mock_connector(columns=columns)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with patch(f"{SI_MODULE}.ConnectionManager") as mock_cm:
            mock_cm.get_connector = AsyncMock(return_value=connector)
            from app.services.datasources.schema_inspector import SchemaInspector

            total = await SchemaInspector.refresh_schema(db, ds)

        assert total == 3

    @pytest.mark.asyncio
    async def test_updates_existing(self):
        """P03-03: Existing schema record → updates instead of duplicating"""
        ds = _mock_datasource()
        existing_record = MagicMock()
        connector = _mock_connector(
            columns=[
                {
                    "column_name": "id",
                    "column_type": "bigint",
                    "is_nullable": False,
                    "is_primary_key": True,
                    "metadata": {},
                },
            ]
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing_record

        with patch(f"{SI_MODULE}.ConnectionManager") as mock_cm:
            mock_cm.get_connector = AsyncMock(return_value=connector)
            from app.services.datasources.schema_inspector import SchemaInspector

            await SchemaInspector.refresh_schema(db, ds)

        # Should update existing, not add new
        assert existing_record.column_type == "bigint"
        assert db.add.call_count == 0

    @pytest.mark.asyncio
    async def test_connector_error_propagates(self):
        """P03-04: Connector raises → exception propagated"""
        ds = _mock_datasource()
        db = MagicMock()

        with patch(f"{SI_MODULE}.ConnectionManager") as mock_cm:
            mock_cm.get_connector = AsyncMock(side_effect=Exception("no connection"))
            from app.services.datasources.schema_inspector import SchemaInspector

            with pytest.raises(Exception, match="no connection"):
                await SchemaInspector.refresh_schema(db, ds)


# ===================================================================
# GET SCHEMA METADATA
# ===================================================================
class TestGetSchemaMetadata:
    @pytest.mark.asyncio
    async def test_returns_cached_metadata(self):
        """P03-05: Queries DataSourceSchema → returns structured dict"""
        ds_id = str(uuid.uuid4())
        records = [
            _mock_schema_record("public", "users", "id", "integer", False, True),
            _mock_schema_record("public", "users", "name", "text", True, False),
        ]
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = records

        from app.services.datasources.schema_inspector import SchemaInspector

        result = await SchemaInspector.get_schema_metadata(db, ds_id)

        assert result["data_source_id"] == ds_id
        assert len(result["tables"]) == 1
        assert len(result["tables"][0]["columns"]) == 2

    @pytest.mark.asyncio
    async def test_empty_when_no_records(self):
        """P03-06: No DataSourceSchema rows → empty tables list"""
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        from app.services.datasources.schema_inspector import SchemaInspector

        result = await SchemaInspector.get_schema_metadata(db, "ds-1")

        assert result["tables"] == []
        assert result["refreshed_at"] is None

    @pytest.mark.asyncio
    async def test_groups_by_table(self):
        """P03-07: Multiple columns same table → grouped under single table entry"""
        records = [
            _mock_schema_record("public", "orders", "id"),
            _mock_schema_record("public", "orders", "amount"),
            _mock_schema_record("public", "items", "id"),
        ]
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = records

        from app.services.datasources.schema_inspector import SchemaInspector

        result = await SchemaInspector.get_schema_metadata(db, "ds-1")

        assert len(result["tables"]) == 2  # orders + items
        orders = [t for t in result["tables"] if t["table_name"] == "orders"][0]
        assert len(orders["columns"]) == 2


# ===================================================================
# GET PREVIEW DATA
# ===================================================================
class TestGetPreviewData:
    @pytest.mark.asyncio
    async def test_returns_sample_rows(self):
        """P03-08: Returns rows from connector"""
        ds = _mock_datasource()
        connector = _mock_connector(sample_rows=[{"id": 1}, {"id": 2}])

        with patch(f"{SI_MODULE}.ConnectionManager") as mock_cm:
            mock_cm.get_connector = AsyncMock(return_value=connector)
            from app.services.datasources.schema_inspector import SchemaInspector

            result = await SchemaInspector.get_preview_data(ds, "public", "users", 50)

        assert len(result["rows"]) == 2
        assert result["table_name"] == "users"

    @pytest.mark.asyncio
    async def test_includes_row_count(self):
        """P03-09: total_rows field populated from get_row_count"""
        ds = _mock_datasource()
        connector = _mock_connector(row_count=500)

        with patch(f"{SI_MODULE}.ConnectionManager") as mock_cm:
            mock_cm.get_connector = AsyncMock(return_value=connector)
            from app.services.datasources.schema_inspector import SchemaInspector

            result = await SchemaInspector.get_preview_data(ds, "public", "users")

        assert result["total_rows"] == 500

    @pytest.mark.asyncio
    async def test_default_limit(self):
        """P03-10: No limit param → defaults to 100"""
        ds = _mock_datasource()
        connector = _mock_connector()

        with patch(f"{SI_MODULE}.ConnectionManager") as mock_cm:
            mock_cm.get_connector = AsyncMock(return_value=connector)
            from app.services.datasources.schema_inspector import SchemaInspector

            await SchemaInspector.get_preview_data(ds, "public", "users")

        connector.get_sample_data.assert_called_once_with("users", "public", 100)

    @pytest.mark.asyncio
    async def test_schema_defaults_none(self):
        """P03-11: schema_name=None → passed to connector"""
        ds = _mock_datasource()
        connector = _mock_connector()

        with patch(f"{SI_MODULE}.ConnectionManager") as mock_cm:
            mock_cm.get_connector = AsyncMock(return_value=connector)
            from app.services.datasources.schema_inspector import SchemaInspector

            await SchemaInspector.get_preview_data(ds, None, "users")

        connector.get_sample_data.assert_called_once_with("users", None, 100)


# ===================================================================
# BASE CONNECTOR
# ===================================================================
class TestBaseConnector:
    def test_get_sample_data_builds_query(self):
        """P03-12: Default impl builds SELECT * FROM schema.table LIMIT N"""
        from app.services.datasources.connectors.base import BaseConnector

        # Create a concrete subclass for testing
        class StubConnector(BaseConnector):
            async def test_connection(self):
                pass

            async def connect(self):
                pass

            async def disconnect(self):
                pass

            async def get_schemas(self):
                return []

            async def get_tables(self, schema_name=None):
                return []

            async def get_columns(self, table_name, schema_name=None):
                return []

            async def execute_query(self, query, params=None):
                self.last_query = query
                return []

            async def get_row_count(self, table_name, schema_name=None):
                return 0

        import asyncio

        c = StubConnector({"host": "localhost"})
        asyncio.get_event_loop().run_until_complete(c.get_sample_data("users", "public", 10))
        assert '"public"."users"' in c.last_query
        assert "LIMIT 10" in c.last_query

    @pytest.mark.asyncio
    async def test_async_context_manager_enter(self):
        """P03-13: __aenter__ calls connect()"""
        from app.services.datasources.connectors.base import BaseConnector

        class StubConnector(BaseConnector):
            connected = False

            async def test_connection(self):
                pass

            async def connect(self):
                self.connected = True

            async def disconnect(self):
                self.connected = False

            async def get_schemas(self):
                return []

            async def get_tables(self, schema_name=None):
                return []

            async def get_columns(self, table_name, schema_name=None):
                return []

            async def execute_query(self, query, params=None):
                return []

            async def get_row_count(self, table_name, schema_name=None):
                return 0

        c = StubConnector({})
        async with c as conn:
            assert conn.connected is True

    @pytest.mark.asyncio
    async def test_async_context_manager_exit(self):
        """P03-14: __aexit__ calls disconnect()"""
        from app.services.datasources.connectors.base import BaseConnector

        class StubConnector(BaseConnector):
            connected = False

            async def test_connection(self):
                pass

            async def connect(self):
                self.connected = True

            async def disconnect(self):
                self.connected = False

            async def get_schemas(self):
                return []

            async def get_tables(self, schema_name=None):
                return []

            async def get_columns(self, table_name, schema_name=None):
                return []

            async def execute_query(self, query, params=None):
                return []

            async def get_row_count(self, table_name, schema_name=None):
                return 0

        c = StubConnector({})
        async with c:
            pass
        assert c.connected is False

    def test_abstract_methods(self):
        """P03-15: Cannot instantiate BaseConnector directly"""
        from app.services.datasources.connectors.base import BaseConnector

        with pytest.raises(TypeError):
            BaseConnector({})
