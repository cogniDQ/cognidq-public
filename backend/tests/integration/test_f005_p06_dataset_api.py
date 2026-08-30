"""
F005 Packet 6 — Dataset CRUD and Lifecycle API tests
======================================================

Endpoints:
  POST   /api/v1/workspaces/{workspace_id}/datasets
  GET    /api/v1/workspaces/{workspace_id}/datasets
  GET    /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}
  PATCH  /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}
  POST   /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/activate
  POST   /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/deactivate
  POST   /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/reactivate
  POST   /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/archive
  GET    /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/audit-logs

Run inside Docker:
    docker-compose exec backend python -m pytest \
        tests/integration/test_f005_p06_dataset_api.py -v
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
import pytest
from fastapi.testclient import TestClient
from jose import jwt

psycopg2.extras.register_uuid()

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@db:5432/dataquality_db",
)

BASE_URL = "/api/v1/workspaces/{workspace_id}/datasets"


def _get_settings():
    from app.core.config import settings

    return settings


# ─────────────────────────────────────────────────────────────────────────────
# Module-scoped fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def test_tenant_id() -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    tenant_id = uuid.uuid4()
    actor = uuid.uuid4()
    slug = f"f005p06-tenant-{str(tenant_id)[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.tenants (
                tenant_id, tenant_name, tenant_slug,
                status, region, plan,
                created_by, updated_by, version,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, 'active', 'eu-west', 'starter',
                %s, %s, 0, NOW(), NOW()
            )
            """,
            (tenant_id, f"F005P06 Tenant {str(tenant_id)[:8]}", slug, actor, actor),
        )
    conn.close()
    return tenant_id


@pytest.fixture(scope="module")
def test_workspace_id(test_tenant_id: uuid.UUID) -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = "F005P06 Test Workspace"
    slug = f"f005p06-ws-{str(wid)[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.workspaces (
                workspace_id, tenant_id, workspace_name, workspace_name_lower,
                workspace_slug, description, default_timezone, status, status_reason,
                created_at, updated_at, created_by, updated_by, version
            ) VALUES (
                %s, %s, %s, %s, %s, NULL, 'UTC', 'active', NULL,
                NOW(), NOW(), %s, %s, 0
            )
            """,
            (wid, test_tenant_id, name, name.lower(), slug, actor, actor),
        )
    conn.close()
    return wid


@pytest.fixture(scope="module")
def active_data_source_id(test_workspace_id: uuid.UUID, test_tenant_id: uuid.UUID) -> uuid.UUID:
    """Create an active data source for dataset tests."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    ds_id = uuid.uuid4()
    actor = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.data_sources (
                data_source_id, workspace_id, tenant_id,
                source_name, source_type, connection_mode, environment,
                status, last_test_status,
                created_at, updated_at, created_by, updated_by
            ) VALUES (
                %s, %s, %s,
                %s, 'postgresql', 'direct', 'staging',
                'active', 'untested',
                NOW(), NOW(), %s, %s
            )
            """,
            (
                ds_id,
                test_workspace_id,
                test_tenant_id,
                f"f005p06-ds-{str(ds_id)[:8]}",
                actor,
                actor,
            ),
        )
    conn.close()
    return ds_id


@pytest.fixture(scope="module")
def archived_data_source_id(test_workspace_id: uuid.UUID, test_tenant_id: uuid.UUID) -> uuid.UUID:
    """Create an archived data source."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    ds_id = uuid.uuid4()
    actor = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.data_sources (
                data_source_id, workspace_id, tenant_id,
                source_name, source_type, connection_mode, environment,
                status, last_test_status,
                created_at, updated_at, created_by, updated_by,
                archived_at, archived_by
            ) VALUES (
                %s, %s, %s,
                %s, 'postgresql', 'direct', 'staging',
                'archived', 'untested',
                NOW(), NOW(), %s, %s,
                NOW(), %s
            )
            """,
            (
                ds_id,
                test_workspace_id,
                test_tenant_id,
                f"f005p06-archived-ds-{str(ds_id)[:8]}",
                actor,
                actor,
                actor,
            ),
        )
    conn.close()
    return ds_id


@pytest.fixture(scope="module")
def other_tenant_id() -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    tenant_id = uuid.uuid4()
    actor = uuid.uuid4()
    slug = f"f005p06-other-{str(tenant_id)[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.tenants (
                tenant_id, tenant_name, tenant_slug,
                status, region, plan,
                created_by, updated_by, version,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, 'active', 'eu-west', 'starter',
                %s, %s, 0, NOW(), NOW()
            )
            """,
            (tenant_id, f"F005P06 Other Tenant {str(tenant_id)[:8]}", slug, actor, actor),
        )
    conn.close()
    return tenant_id


@pytest.fixture(scope="module")
def other_workspace_id(other_tenant_id: uuid.UUID) -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = "F005P06 Other Workspace"
    slug = f"f005p06-other-ws-{str(wid)[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.workspaces (
                workspace_id, tenant_id, workspace_name, workspace_name_lower,
                workspace_slug, description, default_timezone, status, status_reason,
                created_at, updated_at, created_by, updated_by, version
            ) VALUES (
                %s, %s, %s, %s, %s, NULL, 'UTC', 'active', NULL,
                NOW(), NOW(), %s, %s, 0
            )
            """,
            (wid, other_tenant_id, name, name.lower(), slug, actor, actor),
        )
    conn.close()
    return wid


# ─────────────────────────────────────────────────────────────────────────────
# Token helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_token(
    tenant_id: uuid.UUID,
    role: str,
    actor_id: uuid.UUID | None = None,
) -> str:
    s = _get_settings()
    payload = {
        "actor_id": str(actor_id or uuid.uuid4()),
        "actor_role": role,
        "tenant_id": str(tenant_id),
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module")
def admin_token(test_tenant_id: uuid.UUID) -> str:
    return _make_token(test_tenant_id, "workspace_administrator")


@pytest.fixture(scope="module")
def steward_token(test_tenant_id: uuid.UUID) -> str:
    return _make_token(test_tenant_id, "workspace_steward")


@pytest.fixture(scope="module")
def engineer_token(test_tenant_id: uuid.UUID) -> str:
    return _make_token(test_tenant_id, "data_engineer")


@pytest.fixture(scope="module")
def analyst_token(test_tenant_id: uuid.UUID) -> str:
    return _make_token(test_tenant_id, "business_analyst")


@pytest.fixture(scope="module")
def viewer_token(test_tenant_id: uuid.UUID) -> str:
    return _make_token(test_tenant_id, "workspace_viewer")


@pytest.fixture(scope="module")
def other_tenant_token(other_tenant_id: uuid.UUID) -> str:
    return _make_token(other_tenant_id, "workspace_steward")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# URL helpers
# ─────────────────────────────────────────────────────────────────────────────


def _url(workspace_id: uuid.UUID) -> str:
    return BASE_URL.format(workspace_id=workspace_id)


def _detail_url(workspace_id: uuid.UUID, dataset_id: str) -> str:
    return f"{_url(workspace_id)}/{dataset_id}"


def _action_url(workspace_id: uuid.UUID, dataset_id: str, action: str) -> str:
    return f"{_url(workspace_id)}/{dataset_id}/{action}"


def _audit_url(workspace_id: uuid.UUID, dataset_id: str) -> str:
    return f"{_url(workspace_id)}/{dataset_id}/audit-logs"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _create_body(
    data_source_id: uuid.UUID,
    name: str | None = None,
    dataset_type: str = "table",
    physical_id: str | None = None,
) -> dict:
    return {
        "data_source_id": str(data_source_id),
        "dataset_name": name or f"ds-{str(uuid.uuid4())[:8]}",
        "dataset_type": dataset_type,
        "physical_identifier": physical_id or f"schema.tbl_{str(uuid.uuid4())[:8]}",
        "schema_name": "public",
        "description": "Test dataset",
        "business_domain": "finance",
        "criticality": "low",
    }


def _create_dataset(
    client: TestClient,
    workspace_id: uuid.UUID,
    token: str,
    data_source_id: uuid.UUID,
    name: str | None = None,
    dataset_type: str = "table",
    physical_id: str | None = None,
) -> dict:
    body = _create_body(
        data_source_id, name=name, dataset_type=dataset_type, physical_id=physical_id
    )
    resp = client.post(_url(workspace_id), json=body, headers=_auth(token))
    assert resp.status_code == 201, f"Setup create failed: {resp.text}"
    return resp.json()


def _add_field_direct(dataset_id: uuid.UUID, field_name: str = "col1") -> None:
    """Insert a field directly via SQL — bypasses API."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.dataset_fields (
                field_id, dataset_id, field_name, data_type,
                ordinal_position, nullable, sensitivity_classification,
                is_key_candidate, created_at, updated_at
            ) VALUES (%s, %s, %s, 'varchar', 1, true, 'internal', false, NOW(), NOW())
            """,
            (uuid.uuid4(), dataset_id, field_name),
        )
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def cleanup(
    test_workspace_id: uuid.UUID,
    test_tenant_id: uuid.UUID,
    other_workspace_id: uuid.UUID,
    other_tenant_id: uuid.UUID,
):
    yield
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        # Delete fields → datasets → data sources → audit logs → workspaces → tenants
        for ws in (test_workspace_id, other_workspace_id):
            cur.execute(
                """
                DELETE FROM control.dataset_fields
                WHERE dataset_id IN (
                    SELECT dataset_id FROM control.datasets WHERE workspace_id = %s
                )
                """,
                (ws,),
            )
            cur.execute("DELETE FROM control.datasets WHERE workspace_id = %s", (ws,))
            cur.execute("DELETE FROM control.data_sources WHERE workspace_id = %s", (ws,))
            cur.execute("DELETE FROM control.workspace_audit_logs WHERE workspace_id = %s", (ws,))
            cur.execute("DELETE FROM control.workspaces WHERE workspace_id = %s", (ws,))
        for tid in (test_tenant_id, other_tenant_id):
            cur.execute("DELETE FROM control.tenants WHERE tenant_id = %s", (tid,))
    conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# CREATE TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestCreateDataset:
    def test_create_dataset_201(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """POST returns 201 with draft status."""
        body = _create_body(active_data_source_id)
        resp = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "draft"
        assert data["dataset_id"] is not None
        assert data["dataset_name"] == body["dataset_name"]
        assert data["field_count"] == 0

    def test_create_dataset_archived_source_409(
        self,
        client,
        test_workspace_id,
        steward_token,
        archived_data_source_id,
    ):
        """POST with archived source → 409."""
        body = _create_body(archived_data_source_id)
        resp = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
        assert resp.status_code == 409

    def test_create_dataset_duplicate_name_409(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """POST duplicate name → 409."""
        name = f"dup-name-{str(uuid.uuid4())[:8]}"
        _create_dataset(client, test_workspace_id, steward_token, active_data_source_id, name=name)
        body = _create_body(active_data_source_id, name=name)
        resp = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "DUPLICATE_DATASET_NAME"

    def test_create_dataset_duplicate_physical_id_409(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """POST duplicate physical_identifier → 409."""
        phys = f"schema.dup_tbl_{str(uuid.uuid4())[:8]}"
        _create_dataset(
            client, test_workspace_id, steward_token, active_data_source_id, physical_id=phys
        )
        body = _create_body(active_data_source_id, physical_id=phys)
        resp = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "DUPLICATE_PHYSICAL_IDENTIFIER"

    def test_create_dataset_validation_400(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """POST missing required fields → 400."""
        body = {
            "data_source_id": str(active_data_source_id),
            "dataset_name": "ab",  # too short
            "dataset_type": "table",
            "physical_identifier": "",  # empty
        }
        resp = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_physical_id_archived_ok_201(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """POST same physical_id as archived dataset → 201."""
        phys = f"schema.arch_tbl_{str(uuid.uuid4())[:8]}"
        ds = _create_dataset(
            client, test_workspace_id, steward_token, active_data_source_id, physical_id=phys
        )
        # Add a field and activate then archive via direct SQL
        ds_id = uuid.UUID(ds["dataset_id"])
        _add_field_direct(ds_id)
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE control.datasets SET status='active', activated_at=NOW() WHERE dataset_id=%s",
                (ds_id,),
            )
            cur.execute(
                "UPDATE control.datasets SET status='archived', archived_at=NOW(), archived_by=%s WHERE dataset_id=%s",
                (uuid.uuid4(), ds_id),
            )
        conn.close()

        # Now create again with same physical_id
        body = _create_body(active_data_source_id, physical_id=phys)
        resp = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
        assert resp.status_code == 201


# ═════════════════════════════════════════════════════════════════════════════
# LIST TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestListDatasets:
    def test_list_datasets_200(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """GET returns paginated list."""
        _create_dataset(client, test_workspace_id, steward_token, active_data_source_id)
        resp = client.get(_url(test_workspace_id), headers=_auth(steward_token))
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert data["total"] >= 1

    def test_list_datasets_filter_status(
        self,
        client,
        test_workspace_id,
        steward_token,
    ):
        """GET with status=archived filter."""
        resp = client.get(
            _url(test_workspace_id),
            params={"status": "archived"},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["status"] == "archived"

    def test_list_datasets_filter_data_source(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """GET with data_source_id filter."""
        resp = client.get(
            _url(test_workspace_id),
            params={"data_source_id": str(active_data_source_id)},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["data_source_id"] == str(active_data_source_id)

    def test_list_datasets_filter_criticality(
        self,
        client,
        test_workspace_id,
        steward_token,
    ):
        """GET with criticality filter."""
        resp = client.get(
            _url(test_workspace_id),
            params={"criticality": "low"},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["criticality"] == "low"

    def test_list_datasets_search(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """GET with search query matches name."""
        unique = f"searchable-{str(uuid.uuid4())[:8]}"
        _create_dataset(
            client, test_workspace_id, steward_token, active_data_source_id, name=unique
        )
        resp = client.get(
            _url(test_workspace_id),
            params={"search": unique},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1
        assert any(unique in item["dataset_name"] for item in resp.json()["items"])

    def test_list_datasets_sort(
        self,
        client,
        test_workspace_id,
        steward_token,
    ):
        """GET with sort_by=dataset_name works."""
        resp = client.get(
            _url(test_workspace_id),
            params={"sort_by": "dataset_name", "sort_dir": "asc"},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        names = [item["dataset_name"] for item in resp.json()["items"]]
        assert names == sorted(names, key=str.lower)

    def test_list_datasets_pagination(
        self,
        client,
        test_workspace_id,
        steward_token,
    ):
        """GET with page_size=1 has correct pagination."""
        resp = client.get(
            _url(test_workspace_id),
            params={"page": 1, "page_size": 1},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 1
        assert data["page"] == 1
        assert data["page_size"] == 1

    def test_list_cross_workspace_isolation(
        self,
        client,
        test_workspace_id,
        other_workspace_id,
        other_tenant_token,
    ):
        """List from other workspace returns only that workspace's datasets."""
        resp = client.get(
            _url(other_workspace_id),
            headers=_auth(other_tenant_token),
        )
        assert resp.status_code == 200
        # Other workspace has no datasets
        assert resp.json()["total"] == 0


# ═════════════════════════════════════════════════════════════════════════════
# GET DETAIL TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestGetDataset:
    def test_get_dataset_200(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """GET detail returns dataset."""
        ds = _create_dataset(client, test_workspace_id, steward_token, active_data_source_id)
        resp = client.get(
            _detail_url(test_workspace_id, ds["dataset_id"]),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["dataset_id"] == ds["dataset_id"]
        assert "fields" in data

    def test_get_dataset_404(
        self,
        client,
        test_workspace_id,
        steward_token,
    ):
        """GET non-existent → 404."""
        resp = client.get(
            _detail_url(test_workspace_id, str(uuid.uuid4())),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 404

    def test_get_dataset_fields_ordered(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """Fields ordered by ordinal_position."""
        ds = _create_dataset(client, test_workspace_id, steward_token, active_data_source_id)
        ds_id = uuid.UUID(ds["dataset_id"])
        # Add two fields with explicit ordinals
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO control.dataset_fields
                    (field_id, dataset_id, field_name, data_type, ordinal_position,
                     nullable, sensitivity_classification, is_key_candidate, created_at, updated_at)
                VALUES (%s, %s, 'z_field', 'int', 2, true, 'internal', false, NOW(), NOW()),
                       (%s, %s, 'a_field', 'varchar', 1, true, 'internal', false, NOW(), NOW())
                """,
                (uuid.uuid4(), ds_id, uuid.uuid4(), ds_id),
            )
        conn.close()

        resp = client.get(
            _detail_url(test_workspace_id, ds["dataset_id"]),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        fields = resp.json()["fields"]
        assert len(fields) == 2
        assert fields[0]["field_name"] == "a_field"
        assert fields[1]["field_name"] == "z_field"
        assert fields[0]["ordinal_position"] < fields[1]["ordinal_position"]


# ═════════════════════════════════════════════════════════════════════════════
# UPDATE TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestUpdateDataset:
    def test_update_dataset_200(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """PATCH updates allowed fields."""
        ds = _create_dataset(client, test_workspace_id, steward_token, active_data_source_id)
        resp = client.patch(
            _detail_url(test_workspace_id, ds["dataset_id"]),
            json={"description": "Updated desc", "business_domain": "marketing"},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Updated desc"
        assert data["business_domain"] == "marketing"

    def test_update_dataset_immutable_400(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """PATCH dataset_type → 400 IMMUTABLE_FIELD."""
        ds = _create_dataset(client, test_workspace_id, steward_token, active_data_source_id)
        resp = client.patch(
            _detail_url(test_workspace_id, ds["dataset_id"]),
            json={"dataset_type": "view"},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "IMMUTABLE_FIELD"

    def test_update_dataset_name_conflict_409(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """PATCH name to duplicate → 409."""
        name_a = f"conflict-a-{str(uuid.uuid4())[:8]}"
        name_b = f"conflict-b-{str(uuid.uuid4())[:8]}"
        _create_dataset(
            client, test_workspace_id, steward_token, active_data_source_id, name=name_a
        )
        ds_b = _create_dataset(
            client, test_workspace_id, steward_token, active_data_source_id, name=name_b
        )
        resp = client.patch(
            _detail_url(test_workspace_id, ds_b["dataset_id"]),
            json={"dataset_name": name_a},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "DUPLICATE_DATASET_NAME"


# ═════════════════════════════════════════════════════════════════════════════
# LIFECYCLE TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestActivateDataset:
    def test_activate_200(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """POST activate with fields → 200 active."""
        ds = _create_dataset(client, test_workspace_id, steward_token, active_data_source_id)
        _add_field_direct(uuid.UUID(ds["dataset_id"]))
        resp = client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "activate"),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"
        assert resp.json()["activated_at"] is not None

    def test_activate_no_fields_409(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """POST activate no fields → 409."""
        ds = _create_dataset(client, test_workspace_id, steward_token, active_data_source_id)
        resp = client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "activate"),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "NO_FIELDS"

    def test_activate_invalid_status_409(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """POST activate on active → 409."""
        ds = _create_dataset(client, test_workspace_id, steward_token, active_data_source_id)
        _add_field_direct(uuid.UUID(ds["dataset_id"]))
        client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "activate"),
            headers=_auth(steward_token),
        )
        resp = client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "activate"),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


class TestDeactivateDataset:
    def test_deactivate_200(
        self,
        client,
        test_workspace_id,
        admin_token,
        active_data_source_id,
    ):
        """POST deactivate active → 200 inactive."""
        ds = _create_dataset(client, test_workspace_id, admin_token, active_data_source_id)
        _add_field_direct(uuid.UUID(ds["dataset_id"]))
        client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "activate"),
            headers=_auth(admin_token),
        )
        resp = client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "deactivate"),
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "inactive"

    def test_deactivate_invalid_status_409(
        self,
        client,
        test_workspace_id,
        admin_token,
        active_data_source_id,
    ):
        """POST deactivate on draft → 409."""
        ds = _create_dataset(client, test_workspace_id, admin_token, active_data_source_id)
        resp = client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "deactivate"),
            headers=_auth(admin_token),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


class TestReactivateDataset:
    def test_reactivate_200(
        self,
        client,
        test_workspace_id,
        admin_token,
        active_data_source_id,
    ):
        """POST reactivate inactive → 200 active."""
        ds = _create_dataset(client, test_workspace_id, admin_token, active_data_source_id)
        _add_field_direct(uuid.UUID(ds["dataset_id"]))
        client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "activate"), headers=_auth(admin_token)
        )
        client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "deactivate"),
            headers=_auth(admin_token),
        )
        resp = client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "reactivate"),
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_reactivate_invalid_status_409(
        self,
        client,
        test_workspace_id,
        admin_token,
        active_data_source_id,
    ):
        """POST reactivate on active → 409."""
        ds = _create_dataset(client, test_workspace_id, admin_token, active_data_source_id)
        _add_field_direct(uuid.UUID(ds["dataset_id"]))
        client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "activate"), headers=_auth(admin_token)
        )
        resp = client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "reactivate"),
            headers=_auth(admin_token),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


class TestArchiveDataset:
    def test_archive_admin_200(
        self,
        client,
        test_workspace_id,
        admin_token,
        active_data_source_id,
    ):
        """POST archive with admin token → 200 archived."""
        ds = _create_dataset(client, test_workspace_id, admin_token, active_data_source_id)
        _add_field_direct(uuid.UUID(ds["dataset_id"]))
        client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "activate"), headers=_auth(admin_token)
        )
        resp = client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "archive"),
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "archived"
        assert data["archived_at"] is not None
        assert data["archived_by"] is not None

    def test_archive_non_admin_403(
        self,
        client,
        test_workspace_id,
        engineer_token,
        active_data_source_id,
        admin_token,
    ):
        """POST archive with engineer → 403."""
        ds = _create_dataset(client, test_workspace_id, admin_token, active_data_source_id)
        _add_field_direct(uuid.UUID(ds["dataset_id"]))
        client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "activate"), headers=_auth(admin_token)
        )
        resp = client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "archive"),
            headers=_auth(engineer_token),
        )
        assert resp.status_code == 403

    def test_archive_invalid_status_409(
        self,
        client,
        test_workspace_id,
        admin_token,
        active_data_source_id,
    ):
        """POST archive on draft → 409."""
        ds = _create_dataset(client, test_workspace_id, admin_token, active_data_source_id)
        resp = client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "archive"),
            headers=_auth(admin_token),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


# ═════════════════════════════════════════════════════════════════════════════
# RBAC TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestRBAC:
    def test_business_analyst_read_only(
        self,
        client,
        test_workspace_id,
        analyst_token,
        steward_token,
        active_data_source_id,
    ):
        """Analyst can GET but not POST."""
        # Read — should succeed
        resp = client.get(_url(test_workspace_id), headers=_auth(analyst_token))
        assert resp.status_code == 200

        # Create — should fail
        body = _create_body(active_data_source_id)
        resp = client.post(_url(test_workspace_id), json=body, headers=_auth(analyst_token))
        assert resp.status_code == 403

    def test_data_steward_full_access(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """Steward can CRUD + activate."""
        ds = _create_dataset(client, test_workspace_id, steward_token, active_data_source_id)
        # Read
        resp = client.get(
            _detail_url(test_workspace_id, ds["dataset_id"]), headers=_auth(steward_token)
        )
        assert resp.status_code == 200
        # Update
        resp = client.patch(
            _detail_url(test_workspace_id, ds["dataset_id"]),
            json={"description": "Steward updated"},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        # Activate
        _add_field_direct(uuid.UUID(ds["dataset_id"]))
        resp = client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "activate"),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200

    def test_deactivate_pause_roles(
        self,
        client,
        test_workspace_id,
        engineer_token,
        analyst_token,
        admin_token,
        active_data_source_id,
    ):
        """Engineer can deactivate, analyst cannot."""
        # Engineer can deactivate (pause role)
        ds = _create_dataset(client, test_workspace_id, admin_token, active_data_source_id)
        _add_field_direct(uuid.UUID(ds["dataset_id"]))
        client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "activate"), headers=_auth(admin_token)
        )
        resp = client.post(
            _action_url(test_workspace_id, ds["dataset_id"], "deactivate"),
            headers=_auth(engineer_token),
        )
        assert resp.status_code == 200

        # Analyst cannot deactivate
        ds2 = _create_dataset(client, test_workspace_id, admin_token, active_data_source_id)
        _add_field_direct(uuid.UUID(ds2["dataset_id"]))
        client.post(
            _action_url(test_workspace_id, ds2["dataset_id"], "activate"),
            headers=_auth(admin_token),
        )
        resp = client.post(
            _action_url(test_workspace_id, ds2["dataset_id"], "deactivate"),
            headers=_auth(analyst_token),
        )
        assert resp.status_code == 403

    def test_cross_workspace_403(
        self,
        client,
        test_workspace_id,
        other_tenant_token,
    ):
        """Request with other tenant's token → 404 (workspace not found context)."""
        body = _create_body(uuid.uuid4())
        resp = client.post(_url(test_workspace_id), json=body, headers=_auth(other_tenant_token))
        # The service sees no matching data source → 404 or the workspace check fails
        assert resp.status_code in (403, 404)


# ═════════════════════════════════════════════════════════════════════════════
# AUDIT LOG TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestAuditLogs:
    def test_audit_logs_200(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """GET audit logs for dataset."""
        ds = _create_dataset(client, test_workspace_id, steward_token, active_data_source_id)
        resp = client.get(
            _audit_url(test_workspace_id, ds["dataset_id"]),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        # Should have at least the create event
        assert data["total"] >= 1
        assert any(item["action_type"] == "dataset_created" for item in data["items"])

    def test_audit_logs_filter(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """GET audit logs with action_type filter."""
        ds = _create_dataset(client, test_workspace_id, steward_token, active_data_source_id)
        # Also update to create another event
        client.patch(
            _detail_url(test_workspace_id, ds["dataset_id"]),
            json={"description": "audit filter test"},
            headers=_auth(steward_token),
        )
        resp = client.get(
            _audit_url(test_workspace_id, ds["dataset_id"]),
            params={"action_type": "dataset_created"},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["action_type"] == "dataset_created"


# ═════════════════════════════════════════════════════════════════════════════
# METRICS TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestMetrics:
    def test_create_increments_counter(
        self,
        client,
        test_workspace_id,
        steward_token,
        active_data_source_id,
    ):
        """Prometheus counter incremented on create."""
        from prometheus_client import REGISTRY

        # Get baseline
        def _get_val():
            for metric in REGISTRY.collect():
                if metric.name == "dataset_create_count":
                    for sample in metric.samples:
                        if (
                            sample.name == "dataset_create_count_total"
                            and sample.labels.get("workspace_id") == str(test_workspace_id)
                            and sample.labels.get("result") == "success"
                        ):
                            return sample.value
            return 0.0

        before = _get_val()
        _create_dataset(client, test_workspace_id, steward_token, active_data_source_id)
        after = _get_val()
        assert after > before
