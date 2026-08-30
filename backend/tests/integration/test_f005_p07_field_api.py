"""
F005 Packet 7 — Field CRUD and Bulk Import API tests
======================================================

Endpoints:
  POST   /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/fields
  GET    /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/fields
  PATCH  /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/fields/{field_id}
  DELETE /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/fields/{field_id}
  POST   /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/fields/bulk-import

Run inside Docker:
    docker-compose exec backend python -m pytest \
        tests/integration/test_f005_p07_field_api.py -v
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

BASE_URL = "/api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/fields"


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
    slug = f"f005p07-tenant-{str(tenant_id)[:8]}"
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
            (tenant_id, f"F005P07 Tenant {str(tenant_id)[:8]}", slug, actor, actor),
        )
    conn.close()
    return tenant_id


@pytest.fixture(scope="module")
def test_workspace_id(test_tenant_id: uuid.UUID) -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = "F005P07 Test Workspace"
    slug = f"f005p07-ws-{str(wid)[:8]}"
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
                f"f005p07-ds-{str(ds_id)[:8]}",
                actor,
                actor,
            ),
        )
    conn.close()
    return ds_id


@pytest.fixture(scope="module")
def test_dataset_id(
    test_workspace_id: uuid.UUID,
    test_tenant_id: uuid.UUID,
    active_data_source_id: uuid.UUID,
) -> uuid.UUID:
    """Create a draft dataset for field tests."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    ds_id = uuid.uuid4()
    actor = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.datasets (
                dataset_id, workspace_id, tenant_id, data_source_id,
                dataset_name,
                dataset_type, physical_identifier, criticality, status,
                created_at, updated_at, created_by, updated_by
            ) VALUES (
                %s, %s, %s, %s,
                %s,
                'table', %s, 'low', 'draft',
                NOW(), NOW(), %s, %s
            )
            """,
            (
                ds_id,
                test_workspace_id,
                test_tenant_id,
                active_data_source_id,
                f"P07 Test Dataset {str(ds_id)[:8]}",
                f"test_table_p07_{str(ds_id)[:8]}",
                actor,
                actor,
            ),
        )
    conn.close()
    return ds_id


@pytest.fixture(scope="module")
def archived_dataset_id(
    test_workspace_id: uuid.UUID,
    test_tenant_id: uuid.UUID,
    active_data_source_id: uuid.UUID,
) -> uuid.UUID:
    """Create an archived dataset to test rejection of field modifications."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    ds_id = uuid.uuid4()
    actor = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.datasets (
                dataset_id, workspace_id, tenant_id, data_source_id,
                dataset_name,
                dataset_type, physical_identifier, criticality, status,
                created_at, updated_at, created_by, updated_by,
                archived_at, archived_by
            ) VALUES (
                %s, %s, %s, %s,
                %s,
                'table', %s, 'low', 'archived',
                NOW(), NOW(), %s, %s,
                NOW(), %s
            )
            """,
            (
                ds_id,
                test_workspace_id,
                test_tenant_id,
                active_data_source_id,
                f"P07 Archived Dataset {str(ds_id)[:8]}",
                f"archived_table_p07_{str(ds_id)[:8]}",
                actor,
                actor,
                actor,
            ),
        )
    conn.close()
    return ds_id


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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _url(workspace_id: uuid.UUID, dataset_id: uuid.UUID) -> str:
    return BASE_URL.format(workspace_id=workspace_id, dataset_id=dataset_id)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _add_field_via_api(client, url_base: str, token: str, name: str = "col1") -> dict:
    """Convenience: create a field via the API and return the response JSON."""
    r = client.post(
        url_base,
        json={"field_name": name, "data_type": "varchar"},
        headers=_auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _cleanup_fields(dataset_id: uuid.UUID) -> None:
    """Remove all fields for a dataset directly in the DB."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM control.dataset_fields WHERE dataset_id = %s",
            (dataset_id,),
        )
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Tests — Add Field (POST /{dataset_id}/fields)
# ─────────────────────────────────────────────────────────────────────────────


class TestAddField:
    def test_add_field_201(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
        test_tenant_id,
    ):
        url = _url(test_workspace_id, test_dataset_id)
        _cleanup_fields(test_dataset_id)
        r = client.post(
            url,
            json={
                "field_name": "customer_id",
                "data_type": "integer",
                "nullable": False,
                "business_definition": "Primary customer identifier",
                "sensitivity_classification": "internal",
                "is_key_candidate": True,
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["field_name"] == "customer_id"
        assert body["data_type"] == "integer"
        assert body["nullable"] is False
        assert body["is_key_candidate"] is True
        assert body["ordinal_position"] == 1
        assert "field_id" in body

    def test_add_field_duplicate_name_409(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        url = _url(test_workspace_id, test_dataset_id)
        # First add succeeds (or already exists from previous test)
        client.post(
            url,
            json={"field_name": "dup_field", "data_type": "varchar"},
            headers=_auth(admin_token),
        )
        # Second with same name should fail
        r = client.post(
            url, json={"field_name": "dup_field", "data_type": "text"}, headers=_auth(admin_token)
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "DUPLICATE_FIELD_NAME"

    def test_add_field_case_insensitive_duplicate_409(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        url = _url(test_workspace_id, test_dataset_id)
        client.post(
            url,
            json={"field_name": "CaseField", "data_type": "varchar"},
            headers=_auth(admin_token),
        )
        r = client.post(
            url, json={"field_name": "casefield", "data_type": "text"}, headers=_auth(admin_token)
        )
        assert r.status_code == 409

    def test_add_field_archived_dataset_409(
        self,
        client,
        test_workspace_id,
        archived_dataset_id,
        admin_token,
    ):
        url = _url(test_workspace_id, archived_dataset_id)
        r = client.post(
            url, json={"field_name": "col1", "data_type": "varchar"}, headers=_auth(admin_token)
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "DATASET_ARCHIVED"

    def test_add_field_nonexistent_dataset_404(
        self,
        client,
        test_workspace_id,
        admin_token,
    ):
        url = _url(test_workspace_id, uuid.uuid4())
        r = client.post(
            url, json={"field_name": "col1", "data_type": "varchar"}, headers=_auth(admin_token)
        )
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "DATASET_NOT_FOUND"

    def test_add_field_validation_400(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        url = _url(test_workspace_id, test_dataset_id)
        r = client.post(
            url, json={"field_name": "", "data_type": "varchar"}, headers=_auth(admin_token)
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_add_field_403_analyst(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        analyst_token,
    ):
        url = _url(test_workspace_id, test_dataset_id)
        r = client.post(
            url,
            json={"field_name": "analyst_col", "data_type": "varchar"},
            headers=_auth(analyst_token),
        )
        assert r.status_code == 403

    def test_add_field_ordinal_increments(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        _cleanup_fields(test_dataset_id)
        url = _url(test_workspace_id, test_dataset_id)
        r1 = client.post(
            url, json={"field_name": "col_a", "data_type": "varchar"}, headers=_auth(admin_token)
        )
        r2 = client.post(
            url, json={"field_name": "col_b", "data_type": "integer"}, headers=_auth(admin_token)
        )
        assert r1.json()["ordinal_position"] == 1
        assert r2.json()["ordinal_position"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# Tests — List Fields (GET /{dataset_id}/fields)
# ─────────────────────────────────────────────────────────────────────────────


class TestListFields:
    def test_list_fields_200(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        analyst_token,
        admin_token,
    ):
        _cleanup_fields(test_dataset_id)
        url = _url(test_workspace_id, test_dataset_id)
        client.post(
            url,
            json={"field_name": "first_col", "data_type": "varchar"},
            headers=_auth(admin_token),
        )
        client.post(
            url,
            json={"field_name": "second_col", "data_type": "integer"},
            headers=_auth(admin_token),
        )
        r = client.get(url, headers=_auth(analyst_token))
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        assert len(body) == 2
        # Ordered by ordinal_position
        assert body[0]["ordinal_position"] <= body[1]["ordinal_position"]

    def test_list_fields_empty_200(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        analyst_token,
    ):
        _cleanup_fields(test_dataset_id)
        url = _url(test_workspace_id, test_dataset_id)
        r = client.get(url, headers=_auth(analyst_token))
        assert r.status_code == 200
        assert r.json() == []

    def test_list_fields_nonexistent_dataset_404(
        self,
        client,
        test_workspace_id,
        analyst_token,
    ):
        url = _url(test_workspace_id, uuid.uuid4())
        r = client.get(url, headers=_auth(analyst_token))
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Tests — Update Field (PATCH /{dataset_id}/fields/{field_id})
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateField:
    def test_update_field_200(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        _cleanup_fields(test_dataset_id)
        url_base = _url(test_workspace_id, test_dataset_id)
        field = _add_field_via_api(client, url_base, admin_token, "upd_col")
        field_id = field["field_id"]
        r = client.patch(
            f"{url_base}/{field_id}",
            json={"data_type": "bigint", "nullable": False},
            headers=_auth(admin_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["data_type"] == "bigint"
        assert body["nullable"] is False
        assert body["field_name"] == "upd_col"

    def test_update_field_immutable_name_400(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        _cleanup_fields(test_dataset_id)
        url_base = _url(test_workspace_id, test_dataset_id)
        field = _add_field_via_api(client, url_base, admin_token, "immutable_col")
        field_id = field["field_id"]
        r = client.patch(
            f"{url_base}/{field_id}",
            json={"field_name": "new_name"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "IMMUTABLE_FIELD"

    def test_update_field_not_found_404(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        url_base = _url(test_workspace_id, test_dataset_id)
        r = client.patch(
            f"{url_base}/{uuid.uuid4()}",
            json={"data_type": "text"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 404

    def test_update_field_dataset_not_found_404(
        self,
        client,
        test_workspace_id,
        admin_token,
    ):
        url_base = _url(test_workspace_id, uuid.uuid4())
        r = client.patch(
            f"{url_base}/{uuid.uuid4()}",
            json={"data_type": "text"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Tests — Delete Field (DELETE /{dataset_id}/fields/{field_id})
# ─────────────────────────────────────────────────────────────────────────────


class TestDeleteField:
    def test_delete_field_204(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        _cleanup_fields(test_dataset_id)
        url_base = _url(test_workspace_id, test_dataset_id)
        field = _add_field_via_api(client, url_base, admin_token, "del_col")
        field_id = field["field_id"]
        r = client.delete(f"{url_base}/{field_id}", headers=_auth(admin_token))
        assert r.status_code == 204
        # Verify removed from list
        list_r = client.get(url_base, headers=_auth(admin_token))
        field_ids = [f["field_id"] for f in list_r.json()]
        assert field_id not in field_ids

    def test_delete_field_not_found_404(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        url_base = _url(test_workspace_id, test_dataset_id)
        r = client.delete(f"{url_base}/{uuid.uuid4()}", headers=_auth(admin_token))
        assert r.status_code == 404

    def test_delete_field_archived_dataset_409(
        self,
        client,
        test_workspace_id,
        archived_dataset_id,
        admin_token,
    ):
        """Archived datasets reject field deletions."""
        url_base = _url(test_workspace_id, archived_dataset_id)
        r = client.delete(f"{url_base}/{uuid.uuid4()}", headers=_auth(admin_token))
        # Archived dataset → 409; field doesn't exist → but dataset check comes first
        assert r.status_code == 409

    def test_delete_field_403_analyst(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        analyst_token,
        admin_token,
    ):
        _cleanup_fields(test_dataset_id)
        url_base = _url(test_workspace_id, test_dataset_id)
        field = _add_field_via_api(client, url_base, admin_token, "analyst_del_col")
        r = client.delete(f"{url_base}/{field['field_id']}", headers=_auth(analyst_token))
        assert r.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Tests — Bulk Import (POST /{dataset_id}/fields/bulk-import)
# ─────────────────────────────────────────────────────────────────────────────


class TestBulkImportFields:
    def test_bulk_import_append_200(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        _cleanup_fields(test_dataset_id)
        url_base = _url(test_workspace_id, test_dataset_id)
        r = client.post(
            f"{url_base}/bulk-import",
            json={
                "mode": "append",
                "fields": [
                    {"field_name": "col1", "data_type": "varchar"},
                    {"field_name": "col2", "data_type": "integer", "nullable": False},
                    {"field_name": "col3", "data_type": "timestamp"},
                ],
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["imported_count"] == 3
        assert body["mode"] == "append"
        assert len(body["fields"]) == 3
        # Ordered by ordinal_position
        positions = [f["ordinal_position"] for f in body["fields"]]
        assert positions == sorted(positions)

    def test_bulk_import_replace_200(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        url_base = _url(test_workspace_id, test_dataset_id)
        # First ensure there are existing fields
        client.post(
            f"{url_base}/bulk-import",
            json={"mode": "append", "fields": [{"field_name": "old_col", "data_type": "varchar"}]},
            headers=_auth(admin_token),
        )
        r = client.post(
            f"{url_base}/bulk-import",
            json={
                "mode": "replace",
                "fields": [
                    {"field_name": "new_col_a", "data_type": "bigint"},
                    {"field_name": "new_col_b", "data_type": "text"},
                ],
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["imported_count"] == 2
        assert body["mode"] == "replace"
        assert len(body["fields"]) == 2
        names = {f["field_name"] for f in body["fields"]}
        assert names == {"new_col_a", "new_col_b"}

    def test_bulk_import_append_collision_409(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        _cleanup_fields(test_dataset_id)
        url_base = _url(test_workspace_id, test_dataset_id)
        client.post(
            url_base,
            json={"field_name": "existing_col", "data_type": "varchar"},
            headers=_auth(admin_token),
        )
        r = client.post(
            f"{url_base}/bulk-import",
            json={
                "mode": "append",
                "fields": [{"field_name": "existing_col", "data_type": "integer"}],
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "FIELD_NAME_COLLISION"

    def test_bulk_import_archived_dataset_409(
        self,
        client,
        test_workspace_id,
        archived_dataset_id,
        admin_token,
    ):
        url_base = _url(test_workspace_id, archived_dataset_id)
        r = client.post(
            f"{url_base}/bulk-import",
            json={"mode": "append", "fields": [{"field_name": "c1", "data_type": "varchar"}]},
            headers=_auth(admin_token),
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "DATASET_ARCHIVED"

    def test_bulk_import_invalid_mode_400(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        url_base = _url(test_workspace_id, test_dataset_id)
        r = client.post(
            f"{url_base}/bulk-import",
            json={"mode": "upsert", "fields": [{"field_name": "c1", "data_type": "varchar"}]},
            headers=_auth(admin_token),
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_MODE"

    def test_bulk_import_validation_error_400(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        url_base = _url(test_workspace_id, test_dataset_id)
        r = client.post(
            f"{url_base}/bulk-import",
            json={"mode": "append", "fields": [{"field_name": "", "data_type": "varchar"}]},
            headers=_auth(admin_token),
        )
        assert r.status_code == 400

    def test_bulk_import_nonexistent_dataset_404(
        self,
        client,
        test_workspace_id,
        admin_token,
    ):
        url_base = _url(test_workspace_id, uuid.uuid4())
        r = client.post(
            f"{url_base}/bulk-import",
            json={"mode": "append", "fields": [{"field_name": "c1", "data_type": "varchar"}]},
            headers=_auth(admin_token),
        )
        assert r.status_code == 404

    def test_bulk_import_403_analyst(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        analyst_token,
    ):
        url_base = _url(test_workspace_id, test_dataset_id)
        r = client.post(
            f"{url_base}/bulk-import",
            json={"mode": "append", "fields": [{"field_name": "c1", "data_type": "varchar"}]},
            headers=_auth(analyst_token),
        )
        assert r.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Tests — RBAC
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldRBAC:
    def test_steward_can_add_field(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        steward_token,
    ):
        _cleanup_fields(test_dataset_id)
        url = _url(test_workspace_id, test_dataset_id)
        r = client.post(
            url,
            json={"field_name": "steward_col", "data_type": "varchar"},
            headers=_auth(steward_token),
        )
        assert r.status_code == 201

    def test_engineer_can_add_field(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        engineer_token,
    ):
        url = _url(test_workspace_id, test_dataset_id)
        r = client.post(
            url,
            json={"field_name": "engineer_col", "data_type": "varchar"},
            headers=_auth(engineer_token),
        )
        assert r.status_code == 201

    def test_analyst_can_list_fields(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        analyst_token,
    ):
        url = _url(test_workspace_id, test_dataset_id)
        r = client.get(url, headers=_auth(analyst_token))
        assert r.status_code == 200

    def test_no_token_401(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
    ):
        url = _url(test_workspace_id, test_dataset_id)
        r = client.post(url, json={"field_name": "col1", "data_type": "varchar"})
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Tests — Metrics
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldMetrics:
    def test_add_field_increments_counter(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        """Smoke test: adding a field doesn't crash the metrics path."""
        _cleanup_fields(test_dataset_id)
        url = _url(test_workspace_id, test_dataset_id)
        r = client.post(
            url,
            json={"field_name": "metrics_col", "data_type": "varchar"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 201

    def test_bulk_import_increments_counter(
        self,
        client,
        test_workspace_id,
        test_dataset_id,
        admin_token,
    ):
        _cleanup_fields(test_dataset_id)
        url_base = _url(test_workspace_id, test_dataset_id)
        r = client.post(
            f"{url_base}/bulk-import",
            json={"mode": "replace", "fields": [{"field_name": "m_col", "data_type": "varchar"}]},
            headers=_auth(admin_token),
        )
        assert r.status_code == 200
