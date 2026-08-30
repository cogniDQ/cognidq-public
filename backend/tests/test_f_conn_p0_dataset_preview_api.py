"""Tests for the dataset preview endpoint
(GET /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/preview).

These tests bypass the database and connector pool by overriding the
FastAPI dependencies and patching the module-level service / manager
singletons. The goal is to validate the endpoint's contract — request
validation, error mapping, RBAC plumbing, and the row-truncation /
response shape — independently of any live infrastructure.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.api.v1.dependencies.dataset_auth import (
    DatasetActorContext,
    verify_dataset_read_actor,
)
from app.api.v1.endpoints import datasets as datasets_endpoint
from app.models.database import get_db
from app.services.datasets.errors import (
    DatasetAPIError,
    DatasetNotFoundError,
    dataset_api_error_handler,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Build an app exposing only the datasets router so that this test does
# not trigger the heavy ``app.main`` import chain (which requires pyspark).
app = FastAPI()
app.include_router(datasets_endpoint.router, prefix="/api/v1")
app.add_exception_handler(DatasetAPIError, dataset_api_error_handler)


# ─── helpers ────────────────────────────────────────────────────────────

WORKSPACE_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()
DATASET_ID = uuid.uuid4()
DATA_SOURCE_ID = uuid.uuid4()
ACTOR_ID = uuid.uuid4()


def _fake_actor() -> DatasetActorContext:
    return DatasetActorContext(
        actor_id=ACTOR_ID,
        actor_role="workspace_administrator",
        tenant_id=TENANT_ID,
    )


def _fake_dataset(
    *,
    schema_name: str | None = "public",
    physical_identifier: str = "orders",
):
    """Return a dataset stub with just the attributes the endpoint reads."""
    return MagicMock(
        dataset_id=DATASET_ID,
        workspace_id=WORKSPACE_ID,
        tenant_id=TENANT_ID,
        data_source_id=DATA_SOURCE_ID,
        schema_name=schema_name,
        physical_identifier=physical_identifier,
        dataset_name="orders",
        dataset_type="table",
    )


def _fake_data_source(*, status_value: str = "active", source_type: str = "postgresql"):
    ds = MagicMock()
    ds.id = DATA_SOURCE_ID
    ds.workspace_id = WORKSPACE_ID
    ds.type = source_type
    ds.status = status_value
    ds.connection_config = {"host": "h"}
    return ds


def _stub_db_with_data_source(data_source) -> MagicMock:
    """Build a Session-shaped mock whose query(...).filter(...).first()
    returns the provided data source (or None)."""
    db = MagicMock()
    chain = db.query.return_value.filter.return_value
    chain.first.return_value = data_source
    return db


class _FakeConnector:
    """Minimal async-context-manager connector for the preview endpoint."""

    def __init__(self, rows: list[dict[str, Any]]):
        self.preview_dataset = AsyncMock(return_value=rows)
        self.normalize_error = MagicMock(
            return_value={"code": "DATASET_PREVIEW_FAILED", "message": "boom"}
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _async_connector(rows: list[dict[str, Any]]) -> _FakeConnector:
    return _FakeConnector(rows)


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def _override_auth_and_db():
    """Bypass JWT auth and DB session for every test in this module."""
    db_mock = MagicMock()
    app.dependency_overrides[verify_dataset_read_actor] = lambda: _fake_actor()
    app.dependency_overrides[get_db] = lambda: db_mock
    yield db_mock
    app.dependency_overrides.pop(verify_dataset_read_actor, None)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def _patch_service_and_manager(monkeypatch, _override_auth_and_db):
    """Patch the singleton DatasetService + ConnectionManager.

    Each test customises the returned values via the module-level holders
    on the ``state`` fixture rather than re-monkeypatching.
    """

    state = {
        "dataset": _fake_dataset(),
        "data_source": _fake_data_source(),
        "connector": _async_connector([{"id": 1, "name": "Alice"}]),
        "get_dataset_exc": None,
    }

    # Override the DB execute path so _resolve_connector_config returns the
    # right (source_type, status, cred_ref, payload) tuple for the raw SQL query.
    db_mock = _override_auth_and_db

    def _fake_execute(stmt, params=None, **kw):
        result = MagicMock()
        ds = state["data_source"]
        if ds is None:
            result.fetchone.return_value = None
        else:
            # Matches the SELECT row in _resolve_connector_config:
            # source_type, status, credential_reference, encrypted_payload
            result.fetchone.return_value = (ds.type, ds.status, None, None)
        return result

    db_mock.execute.side_effect = _fake_execute

    def _fake_get_dataset(db, *, workspace_id, dataset_id):
        if state["get_dataset_exc"] is not None:
            raise state["get_dataset_exc"]
        return state["dataset"]

    monkeypatch.setattr(datasets_endpoint._service, "get_dataset", _fake_get_dataset)

    async def _fake_get_connector(source_type, connection_config):
        return state["connector"]

    monkeypatch.setattr(
        datasets_endpoint.ConnectionManager,
        "get_connector",
        AsyncMock(side_effect=_fake_get_connector),
    )

    return state


# ─── tests ──────────────────────────────────────────────────────────────


def _url(workspace_id=WORKSPACE_ID, dataset_id=DATASET_ID, **q) -> str:
    qs = ("?" + "&".join(f"{k}={v}" for k, v in q.items())) if q else ""
    return f"/api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/preview{qs}"


class TestDatasetPreviewEndpoint:
    def test_returns_200_with_rows(self, client, _patch_service_and_manager):
        resp = client.get(_url(limit=10))
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["dataset_id"] == str(DATASET_ID)
        assert body["schema_name"] == "public"
        assert body["table_name"] == "orders"
        assert body["row_limit"] == 10
        assert body["row_count"] == 1
        assert body["columns"] == ["id", "name"]
        assert body["rows"] == [{"id": 1, "name": "Alice"}]
        assert body["truncated_columns"] == []

    def test_invokes_connector_with_dataset_metadata(self, client, _patch_service_and_manager):
        client.get(_url(limit=42))

        connector = _patch_service_and_manager["connector"]
        connector.preview_dataset.assert_awaited_once_with(
            table_name="orders",
            schema_name="public",
            limit=42,
        )

    def test_default_limit_is_100(self, client, _patch_service_and_manager):
        resp = client.get(_url())
        assert resp.status_code == 200
        assert resp.json()["row_limit"] == 100

    @pytest.mark.parametrize("bad_limit", [0, -1, 1001, 10_000])
    def test_rejects_out_of_range_limit(self, client, _patch_service_and_manager, bad_limit):
        resp = client.get(_url(limit=bad_limit))
        # FastAPI's Query(ge=1, le=1000) returns 422 for invalid values.
        assert resp.status_code == 422, resp.text

    def test_dataset_not_found_returns_404(self, client, _patch_service_and_manager):
        _patch_service_and_manager["get_dataset_exc"] = DatasetNotFoundError("missing")
        resp = client.get(_url())
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "DATASET_NOT_FOUND"

    def test_data_source_missing_returns_404(self, client, _patch_service_and_manager):
        _patch_service_and_manager["data_source"] = None
        resp = client.get(_url())
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "DATA_SOURCE_NOT_FOUND"

    def test_inactive_data_source_returns_409(self, client, _patch_service_and_manager):
        _patch_service_and_manager["data_source"] = _fake_data_source(status_value="archived")
        resp = client.get(_url())
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "DATA_SOURCE_NOT_ACTIVE"

    def test_invalid_identifier_returns_400(self, client, _patch_service_and_manager):
        connector = _patch_service_and_manager["connector"]
        connector.preview_dataset = AsyncMock(
            side_effect=ValueError("Invalid table_name: 'bad; DROP'")
        )

        resp = client.get(_url())
        assert resp.status_code == 400
        body = resp.json()["error"]
        assert body["code"] == "DATASET_PREVIEW_INVALID"
        assert "table_name" in body["message"]

    def test_connector_failure_returns_502_with_normalized_code(
        self, client, _patch_service_and_manager
    ):
        connector = _patch_service_and_manager["connector"]
        connector.preview_dataset = AsyncMock(side_effect=RuntimeError("connection refused"))
        connector.normalize_error = MagicMock(
            return_value={"code": "NETWORK_ERROR", "message": "down"}
        )

        resp = client.get(_url())
        assert resp.status_code == 502
        body = resp.json()["error"]
        assert body["code"] == "NETWORK_ERROR"
        assert body["message"] == "down"

    def test_oversized_cells_are_truncated(self, client, _patch_service_and_manager):
        big = "x" * (datasets_endpoint.DATASET_PREVIEW_MAX_CELL_BYTES + 100)
        _patch_service_and_manager["connector"] = _async_connector(
            [{"id": 1, "blob": big, "name": "ok"}]
        )

        resp = client.get(_url())
        assert resp.status_code == 200
        body = resp.json()

        assert body["truncated_columns"] == ["blob"]
        cell = body["rows"][0]["blob"]
        assert cell.endswith("…[truncated]")
        # The trimmed value must be smaller than the original payload.
        assert len(cell.encode("utf-8")) <= (datasets_endpoint.DATASET_PREVIEW_MAX_CELL_BYTES + 50)
        # Untouched columns survive unchanged.
        assert body["rows"][0]["name"] == "ok"

    def test_handles_non_json_native_values(self, client, _patch_service_and_manager):
        """datetime / UUID values should pass through jsonable_encoder."""
        rid = uuid.uuid4()
        when = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        _patch_service_and_manager["connector"] = _async_connector(
            [{"id": rid, "created_at": when}]
        )

        resp = client.get(_url())
        assert resp.status_code == 200, resp.text
        row = resp.json()["rows"][0]
        assert row["id"] == str(rid)
        assert row["created_at"].startswith("2026-01-01T12:00:00")

    def test_empty_result_returns_empty_columns(self, client, _patch_service_and_manager):
        _patch_service_and_manager["connector"] = _async_connector([])
        resp = client.get(_url())
        assert resp.status_code == 200
        body = resp.json()
        assert body["rows"] == []
        assert body["columns"] == []
        assert body["row_count"] == 0
