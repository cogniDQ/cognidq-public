"""Tests for PostgreSQLConnector.preview_dataset (spec §17.4).

Covers identifier validation, parameterized LIMIT, and the
PREVIEW_ROW_HARD_CAP enforcement. The DB layer is mocked because these
are pure SQL-construction tests — integration with a real database is
already covered by tests/test_f_conn_core_lifecycle.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app.services.datasources.connectors.postgresql import (
    PREVIEW_ROW_HARD_CAP,
    PostgreSQLConnector,
    _validate_identifier,
)
from psycopg2 import sql


def _connector_with_cursor(rows):
    """Return (connector, cursor_mock) wired with canned rows."""
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    cursor.description = [("col",)]  # truthy so fetchall is invoked

    connection = MagicMock()
    connection.cursor.return_value = cursor

    connector = PostgreSQLConnector(
        {
            "host": "h",
            "port": 5432,
            "database": "d",
            "username": "u",
            "password": "p",
        }
    )
    connector.connection = connection
    return connector, cursor


# ─── identifier validation ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    ["public", "orders", "_audit", "tbl_2024", "A1"],
)
def test_validate_identifier_accepts_valid(value):
    assert _validate_identifier(value, "x") == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "1bad",  # leading digit
        "drop table x",  # spaces
        "users;DROP",  # semicolon
        'a"b',  # quote
        "a-b",  # dash
        "schema.table",  # dot
        "a/b",  # slash
        "../etc",  # path traversal-ish
    ],
)
def test_validate_identifier_rejects_unsafe(value):
    with pytest.raises(ValueError):
        _validate_identifier(value, "schema_name")


# ─── preview_dataset ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preview_dataset_rejects_unsafe_schema():
    connector, _ = _connector_with_cursor([])
    with pytest.raises(ValueError):
        await connector.preview_dataset("orders", schema_name="public; DROP")


@pytest.mark.asyncio
async def test_preview_dataset_rejects_unsafe_table():
    connector, _ = _connector_with_cursor([])
    with pytest.raises(ValueError):
        await connector.preview_dataset('orders"; --', schema_name="public")


@pytest.mark.asyncio
async def test_preview_dataset_rejects_traversal_table():
    connector, _ = _connector_with_cursor([])
    with pytest.raises(ValueError):
        await connector.preview_dataset("../etc", schema_name="public")


@pytest.mark.asyncio
async def test_preview_dataset_zero_limit_short_circuits():
    connector, cursor = _connector_with_cursor([])
    rows = await connector.preview_dataset("orders", limit=0)
    assert rows == []
    cursor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_preview_dataset_negative_limit_short_circuits():
    connector, cursor = _connector_with_cursor([])
    rows = await connector.preview_dataset("orders", limit=-5)
    assert rows == []
    cursor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_preview_dataset_clamps_to_hard_cap():
    connector, cursor = _connector_with_cursor([])
    await connector.preview_dataset("orders", limit=PREVIEW_ROW_HARD_CAP * 10)

    cursor.execute.assert_called_once()
    _, params = cursor.execute.call_args.args
    assert params == (PREVIEW_ROW_HARD_CAP,)


def _identifiers(composed):
    return [part.strings[0] for part in composed.seq if isinstance(part, sql.Identifier)]


def _sql_literals(composed):
    return "".join(part.string for part in composed.seq if isinstance(part, sql.SQL))


@pytest.mark.asyncio
async def test_preview_dataset_uses_parameterized_limit():
    connector, cursor = _connector_with_cursor([{"id": 1}])
    await connector.preview_dataset("orders", schema_name="sales", limit=25)

    query, params = cursor.execute.call_args.args
    assert isinstance(query, sql.Composed)
    assert params == (25,)
    literals = _sql_literals(query)
    # LIMIT must be parameterized — the integer must not appear in the SQL.
    assert "%s" in literals
    assert "25" not in literals
    assert _identifiers(query) == ["sales", "orders"]


@pytest.mark.asyncio
async def test_preview_dataset_returns_dict_rows():
    canned = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    connector, _ = _connector_with_cursor(canned)
    result = await connector.preview_dataset("orders", limit=10)
    assert result == canned


@pytest.mark.asyncio
async def test_preview_dataset_defaults_schema_to_public():
    connector, cursor = _connector_with_cursor([])
    await connector.preview_dataset("orders", limit=5)
    query, _ = cursor.execute.call_args.args
    assert _identifiers(query) == ["public", "orders"]


@pytest.mark.asyncio
async def test_preview_dataset_closes_cursor_on_error():
    connector, cursor = _connector_with_cursor([])
    cursor.execute.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        await connector.preview_dataset("orders", limit=10)
    cursor.close.assert_called_once()
