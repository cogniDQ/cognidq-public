"""
F072 P02 — Unit tests: PostgreSQLConnector

Tests init, test_connection, connect, disconnect, schema introspection, queries.

P02-01 .. P02-15  (15 tests)
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

PG_MODULE = "app.services.datasources.connectors.postgresql"


def _config():
    return {
        "host": "localhost",
        "port": 5432,
        "database": "testdb",
        "username": "user",
        "password": "pass",
        "ssl_mode": "require",
    }


def _connector(config=None):
    with patch(f"{PG_MODULE}.psycopg2"):
        from app.services.datasources.connectors.postgresql import PostgreSQLConnector

        return PostgreSQLConnector(config or _config())


# ===================================================================
# INIT
# ===================================================================
class TestPostgresInit:
    def test_stores_config(self):
        """P02-01"""
        c = _connector()
        assert c.connection_config["host"] == "localhost"
        assert c.connection is None
        assert c.cursor is None


# ===================================================================
# TEST CONNECTION
# ===================================================================
class TestTestConnection:
    @pytest.mark.asyncio
    async def test_success(self):
        """P02-02: psycopg2.connect succeeds → (True, msg, {version, database})"""
        with patch(f"{PG_MODULE}.psycopg2") as mock_pg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = ["PostgreSQL 15.2"]
            mock_conn.cursor.return_value = mock_cursor
            mock_pg.connect.return_value = mock_conn

            from app.services.datasources.connectors.postgresql import PostgreSQLConnector

            c = PostgreSQLConnector(_config())
            success, msg, details = await c.test_connection()

            assert success is True
            assert "successful" in msg.lower()
            assert details["version"] == "PostgreSQL 15.2"
            assert details["database"] == "testdb"

    @pytest.mark.asyncio
    async def test_failure(self):
        """P02-03: psycopg2.connect raises → (False, error_str, None)"""
        with patch(f"{PG_MODULE}.psycopg2") as mock_pg:
            mock_pg.connect.side_effect = Exception("connection refused")

            from app.services.datasources.connectors.postgresql import PostgreSQLConnector

            c = PostgreSQLConnector(_config())
            success, msg, details = await c.test_connection()

            assert success is False
            assert "connection refused" in msg
            assert details is None


# ===================================================================
# CONNECT / DISCONNECT
# ===================================================================
class TestConnect:
    @pytest.mark.asyncio
    async def test_creates_connection(self):
        """P02-04: psycopg2.connect called with host/port/dbname/user/password"""
        with patch(f"{PG_MODULE}.psycopg2") as mock_pg:
            from app.services.datasources.connectors.postgresql import PostgreSQLConnector

            c = PostgreSQLConnector(_config())
            await c.connect()

            mock_pg.connect.assert_called_once_with(
                host="localhost",
                port=5432,
                database="testdb",
                user="user",
                password="pass",
                sslmode="require",
            )

    @pytest.mark.asyncio
    async def test_ssl_mode(self):
        """P02-05: sslmode parameter forwarded"""
        with patch(f"{PG_MODULE}.psycopg2") as mock_pg:
            from app.services.datasources.connectors.postgresql import PostgreSQLConnector

            cfg = _config()
            cfg["ssl_mode"] = "disable"
            c = PostgreSQLConnector(cfg)
            await c.connect()

            call_kwargs = mock_pg.connect.call_args
            assert (
                call_kwargs.kwargs.get("sslmode") == "disable"
                or (call_kwargs[1] if len(call_kwargs) > 1 else {}).get("sslmode") == "disable"
            )


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_closes_cursor_and_connection(self):
        """P02-06: cursor.close() and connection.close() called"""
        c = _connector()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        c.connection = mock_conn
        c.cursor = mock_cur
        await c.disconnect()
        mock_cur.close.assert_called_once()
        mock_conn.close.assert_called_once()


# ===================================================================
# SCHEMA INTROSPECTION
# ===================================================================
class TestGetSchemas:
    @pytest.mark.asyncio
    async def test_excludes_system(self):
        """P02-07: Returns user schemas, excludes pg system schemas"""
        c = _connector()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("public",), ("app",)]
        c.connection = MagicMock()
        c.connection.cursor.return_value = mock_cursor

        schemas = await c.get_schemas()
        assert schemas == ["public", "app"]
        # Verify the query excludes system schemas
        query_arg = mock_cursor.execute.call_args[0][0]
        assert "pg_catalog" in query_arg
        assert "information_schema" in query_arg


class TestGetTables:
    @pytest.mark.asyncio
    async def test_returns_table_list(self):
        """P02-08: Returns list of {schema_name, table_name} dicts"""
        c = _connector()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"table_schema": "public", "table_name": "users"},
        ]
        mock_count_cursor = MagicMock()
        mock_count_cursor.fetchone.return_value = [42]
        c.connection = MagicMock()
        c.connection.cursor.side_effect = [mock_cursor, mock_count_cursor]

        tables = await c.get_tables("public")
        assert len(tables) == 1
        assert tables[0]["table_name"] == "users"

    @pytest.mark.asyncio
    async def test_defaults_to_public(self):
        """P02-09: schema_name=None → queries public schema"""
        c = _connector()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        c.connection = MagicMock()
        c.connection.cursor.return_value = mock_cursor

        await c.get_tables(None)
        # Second arg to execute should be ('public',)
        execute_args = mock_cursor.execute.call_args[0]
        assert execute_args[1] == ("public",)


# ===================================================================
# COLUMNS
# ===================================================================
class TestGetColumns:
    @pytest.mark.asyncio
    async def test_returns_column_metadata(self):
        """P02-10: Includes column_name, column_type, is_nullable, is_primary_key"""
        c = _connector()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "column_name": "id",
                "data_type": "integer",
                "is_nullable": "NO",
                "column_default": None,
                "character_maximum_length": None,
                "numeric_precision": 32,
                "numeric_scale": 0,
                "is_primary_key": True,
            }
        ]
        c.connection = MagicMock()
        c.connection.cursor.return_value = mock_cursor

        cols = await c.get_columns("users", "public")
        assert cols[0]["column_name"] == "id"
        assert cols[0]["column_type"] == "integer"
        assert cols[0]["is_nullable"] is False
        assert cols[0]["is_primary_key"] is True

    @pytest.mark.asyncio
    async def test_primary_key_detection(self):
        """P02-11: Primary key columns flagged correctly"""
        c = _connector()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "column_name": "id",
                "data_type": "int",
                "is_nullable": "NO",
                "column_default": None,
                "character_maximum_length": None,
                "numeric_precision": None,
                "numeric_scale": None,
                "is_primary_key": True,
            },
            {
                "column_name": "name",
                "data_type": "text",
                "is_nullable": "YES",
                "column_default": None,
                "character_maximum_length": None,
                "numeric_precision": None,
                "numeric_scale": None,
                "is_primary_key": False,
            },
        ]
        c.connection = MagicMock()
        c.connection.cursor.return_value = mock_cursor

        cols = await c.get_columns("users")
        assert cols[0]["is_primary_key"] is True
        assert cols[1]["is_primary_key"] is False


# ===================================================================
# EXECUTE QUERY / ROW COUNT / SAMPLE DATA
# ===================================================================
class TestExecuteQuery:
    @pytest.mark.asyncio
    async def test_returns_dicts(self):
        """P02-12: RealDictCursor rows returned as list of dicts"""
        c = _connector()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "Alice"}]
        c.connection = MagicMock()
        c.connection.cursor.return_value = mock_cursor

        results = await c.execute_query("SELECT * FROM users")
        assert results == [{"id": 1, "name": "Alice"}]

    @pytest.mark.asyncio
    async def test_no_results(self):
        """P02-13: Query with no rows → empty list"""
        c = _connector()
        mock_cursor = MagicMock()
        mock_cursor.description = None  # no results
        c.connection = MagicMock()
        c.connection.cursor.return_value = mock_cursor

        results = await c.execute_query("DELETE FROM users WHERE 1=0")
        assert results == []


class TestGetRowCount:
    @pytest.mark.asyncio
    async def test_returns_count(self):
        """P02-14: COUNT(*) result extracted"""
        c = _connector()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [1000]
        c.connection = MagicMock()
        c.connection.cursor.return_value = mock_cursor

        count = await c.get_row_count("users", "public")
        assert count == 1000


class TestGetSampleData:
    @pytest.mark.asyncio
    async def test_builds_limit_query(self):
        """P02-15: Calls execute_query with LIMIT clause"""
        c = _connector()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [{"id": 1}]
        c.connection = MagicMock()
        c.connection.cursor.return_value = mock_cursor

        await c.get_sample_data("users", "public", limit=10)
        query_arg = mock_cursor.execute.call_args[0][0]
        assert "LIMIT" in query_arg or "limit" in query_arg.lower()
