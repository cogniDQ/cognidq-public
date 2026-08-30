"""PostgreSQL connector implementation."""

import logging
import re
from typing import Any

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from app.services.datasources.connectors.base import BaseConnector

logger = logging.getLogger(__name__)


#: Hard cap on rows returned by any preview call (product spec §17.4).
PREVIEW_ROW_HARD_CAP: int = 2_000_000

#: Regular SQL identifier — letters / digits / underscore, not starting with a
#: digit. ``preview_dataset`` rejects anything else to keep the controlled
#: query template safe even if quoting were ever bypassed.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(value: str, field: str) -> str:
    if not value or not _IDENT_RE.match(value):
        raise ValueError(f"Invalid {field}: {value!r}")
    return value


class PostgreSQLConnector(BaseConnector):
    """PostgreSQL database connector using psycopg2."""

    connector_type = "postgresql"

    def __init__(self, connection_config: dict[str, Any]):
        """
        Initialize PostgreSQL connector.

        Expected connection_config:
        {
            "host": str,
            "port": int,
            "database": str,
            "username": str,
            "password": str,
            "ssl_mode": str (optional, default: "prefer")
        }
        """
        super().__init__(connection_config)
        self.connection = None
        self.cursor = None

    async def test_connection(self) -> tuple[bool, str, dict[str, Any] | None]:
        """Test PostgreSQL connection."""
        try:
            await self.connect()

            # Test query
            cursor = self.connection.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            cursor.close()

            await self.disconnect()

            return (
                True,
                "Connection successful",
                {"version": version, "database": self.connection_config.get("database")},
            )
        except Exception as e:
            logger.error(f"PostgreSQL connection test failed: {e}")
            return False, f"Connection failed: {str(e)}", None

    async def connect(self):
        """Establish connection to PostgreSQL."""
        try:
            self.connection = psycopg2.connect(
                host=self.connection_config.get("host"),
                port=self.connection_config.get("port", 5432),
                database=self.connection_config.get("database"),
                user=self.connection_config.get("username"),
                password=self.connection_config.get("password"),
                sslmode=self.connection_config.get("ssl_mode", "prefer"),
            )
            logger.info(f"Connected to PostgreSQL: {self.connection_config.get('host')}")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    async def disconnect(self):
        """Close PostgreSQL connection."""
        if self.cursor:
            self.cursor.close()
            self.cursor = None
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Disconnected from PostgreSQL")

    async def get_schemas(self) -> list[str]:
        """Get list of schemas in the database."""
        query = """
            SELECT schema_name 
            FROM information_schema.schemata 
            WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
            ORDER BY schema_name
        """
        cursor = self.connection.cursor()
        cursor.execute(query)
        schemas = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return schemas

    async def get_tables(self, schema_name: str | None = None) -> list[dict[str, Any]]:
        """Get list of tables in a schema."""
        schema_filter = schema_name if schema_name else "public"

        query = """
            SELECT 
                table_schema,
                table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
                AND table_schema = %s
            ORDER BY table_name
        """

        cursor = self.connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, (schema_filter,))
        tables = []

        for row in cursor.fetchall():
            table_info = {"schema_name": row["table_schema"], "table_name": row["table_name"]}

            # Optionally get row count (can be slow for large tables)
            try:
                count_query = f'SELECT COUNT(*) FROM "{row["table_schema"]}"."{row["table_name"]}"'
                count_cursor = self.connection.cursor()
                count_cursor.execute(count_query)
                table_info["row_count"] = count_cursor.fetchone()[0]
                count_cursor.close()
            except Exception as e:
                logger.warning(f"Could not get row count for {row['table_name']}: {e}")
                table_info["row_count"] = None

            tables.append(table_info)

        cursor.close()
        return tables

    async def get_columns(
        self, table_name: str, schema_name: str | None = None
    ) -> list[dict[str, Any]]:
        """Get column metadata for a table."""
        schema_filter = schema_name if schema_name else "public"

        query = """
            SELECT 
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.column_default,
                c.character_maximum_length,
                c.numeric_precision,
                c.numeric_scale,
                CASE 
                    WHEN pk.column_name IS NOT NULL THEN TRUE 
                    ELSE FALSE 
                END as is_primary_key
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT ku.table_schema, ku.table_name, ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                    ON tc.constraint_name = ku.constraint_name
                    AND tc.table_schema = ku.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
            ) pk ON c.table_schema = pk.table_schema 
                AND c.table_name = pk.table_name 
                AND c.column_name = pk.column_name
            WHERE c.table_schema = %s
                AND c.table_name = %s
            ORDER BY c.ordinal_position
        """

        cursor = self.connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, (schema_filter, table_name))

        columns = []
        for row in cursor.fetchall():
            metadata = {}
            if row["character_maximum_length"]:
                metadata["max_length"] = row["character_maximum_length"]
            if row["numeric_precision"]:
                metadata["precision"] = row["numeric_precision"]
            if row["numeric_scale"]:
                metadata["scale"] = row["numeric_scale"]

            columns.append(
                {
                    "column_name": row["column_name"],
                    "column_type": row["data_type"],
                    "is_nullable": row["is_nullable"] == "YES",
                    "is_primary_key": row["is_primary_key"],
                    "default_value": row["column_default"],
                    "metadata": metadata,
                }
            )

        cursor.close()
        return columns

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a SQL query and return results as list of dicts."""
        cursor = self.connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, params)

        results = []
        if cursor.description:  # Query returned results
            results = [dict(row) for row in cursor.fetchall()]

        cursor.close()
        return results

    async def get_row_count(self, table_name: str, schema_name: str | None = None) -> int:
        """Get row count for a table."""
        schema_filter = schema_name if schema_name else "public"
        query = f'SELECT COUNT(*) FROM "{schema_filter}"."{table_name}"'

        cursor = self.connection.cursor()
        cursor.execute(query)
        count = cursor.fetchone()[0]
        cursor.close()

        return count

    # ─── Spec §17.4 controlled preview ───────────────────────────────────────

    async def preview_dataset(
        self,
        table_name: str,
        schema_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return up to ``limit`` rows using a controlled SQL template.

        - ``schema_name`` and ``table_name`` are validated against
          :data:`_IDENT_RE`; arbitrary SQL is rejected with ``ValueError``.
        - The query is composed with :class:`psycopg2.sql.Identifier`, so even
          the validated identifiers are properly quoted.
        - ``limit`` is capped at :data:`PREVIEW_ROW_HARD_CAP` and bound as a
          parameter — never interpolated into the SQL string.
        - Negative or zero limits short-circuit to ``[]`` without a query.
        """
        capped = min(max(0, int(limit)), PREVIEW_ROW_HARD_CAP)
        if capped == 0:
            return []

        schema = _validate_identifier(schema_name or "public", "schema_name")
        table = _validate_identifier(table_name, "table_name")

        query = sql.SQL("SELECT * FROM {}.{} LIMIT %s").format(
            sql.Identifier(schema),
            sql.Identifier(table),
        )

        cursor = self.connection.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute(query, (capped,))
            rows = cursor.fetchall() if cursor.description else []
        finally:
            cursor.close()
        return [dict(r) for r in rows]
