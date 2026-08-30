"""
F133 P02 — Tenant Usage Stats Fix Tests

Test IDs: T02-01 through T02-05

Covers:
  T02-01: DbWorkspaceRegistryClient.get_count returns correct workspace count
  T02-02: DbUserRegistryClient.get_count returns correct user count
  T02-03: DbWorkspaceRegistryClient excludes archived workspaces
  T02-04: get_workspace_registry_client dependency returns DB-backed client
  T02-05: get_user_registry_client dependency returns DB-backed client
"""

from unittest.mock import MagicMock, call, patch

import pytest
from sqlalchemy.engine import Row

# ── T02-01 DbWorkspaceRegistryClient ────────────────────────────────────────


def test_t02_01_db_workspace_registry_client_returns_count():
    """DbWorkspaceRegistryClient.get_count queries control.workspaces and returns count."""
    from app.services.tenants.registry import DbWorkspaceRegistryClient

    mock_row = MagicMock()
    mock_row.__getitem__ = MagicMock(side_effect=lambda i: 3 if i == 0 else None)

    mock_result = MagicMock()
    mock_result.fetchone.return_value = mock_row

    mock_db = MagicMock()
    mock_db.execute.return_value = mock_result

    mock_session_local = MagicMock(return_value=mock_db)

    with patch("app.models.database.SessionLocal", mock_session_local):
        client = DbWorkspaceRegistryClient()
        count = client.get_count("test-tenant-id")

    assert count == 3
    mock_db.execute.assert_called_once()
    call_args = mock_db.execute.call_args
    sql_str = str(call_args[0][0])
    assert "control.workspaces" in sql_str
    mock_db.close.assert_called_once()


# ── T02-02 DbUserRegistryClient ─────────────────────────────────────────────


def test_t02_02_db_user_registry_client_returns_count():
    """DbUserRegistryClient.get_count queries workspace_role_assignments and returns count."""
    from app.services.tenants.registry import DbUserRegistryClient

    mock_row = MagicMock()
    mock_row.__getitem__ = MagicMock(side_effect=lambda i: 5 if i == 0 else None)

    mock_result = MagicMock()
    mock_result.fetchone.return_value = mock_row

    mock_db = MagicMock()
    mock_db.execute.return_value = mock_result

    mock_session_local = MagicMock(return_value=mock_db)

    with patch("app.models.database.SessionLocal", mock_session_local):
        client = DbUserRegistryClient()
        count = client.get_count("test-tenant-id")

    assert count == 5
    mock_db.execute.assert_called_once()
    call_args = mock_db.execute.call_args
    sql_str = str(call_args[0][0])
    assert "workspace_role_assignments" in sql_str
    mock_db.close.assert_called_once()


# ── T02-03 excludes archived workspaces ─────────────────────────────────────


def test_t02_03_workspace_client_excludes_archived():
    """The SQL query for workspaces filters out archived status."""
    import inspect

    from app.services.tenants.registry import DbWorkspaceRegistryClient

    # Read the source to check the filter is present in the SQL string
    src = inspect.getsource(DbWorkspaceRegistryClient.get_count)
    assert "archived" in src, "Workspace query should exclude archived workspaces"


# ── T02-04 get_workspace_registry_client uses DB-backed inner ────────────────


def test_t02_04_get_workspace_registry_client_is_db_backed():
    """get_workspace_registry_client returns a client wrapping DbWorkspaceRegistryClient."""
    from app.services.tenants.registry import (
        CircuitBreakerWrappedClient,
        DbWorkspaceRegistryClient,
        get_workspace_registry_client,
    )

    client = get_workspace_registry_client()
    assert isinstance(client, CircuitBreakerWrappedClient)
    assert isinstance(client._inner, DbWorkspaceRegistryClient)


# ── T02-05 get_user_registry_client uses DB-backed inner ────────────────────


def test_t02_05_get_user_registry_client_is_db_backed():
    """get_user_registry_client returns a client wrapping DbUserRegistryClient."""
    from app.services.tenants.registry import (
        CircuitBreakerWrappedClient,
        DbUserRegistryClient,
        get_user_registry_client,
    )

    client = get_user_registry_client()
    assert isinstance(client, CircuitBreakerWrappedClient)
    assert isinstance(client._inner, DbUserRegistryClient)
