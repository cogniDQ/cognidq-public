"""
F-CONN-CORE — Connector registry + catalog endpoint tests.

Covers:
  - Registry default specs (every P0 + P1 connector listed in spec §7 is present)
  - Truthful status (only PostgreSQL is `ready`; cloud connectors `integration_ready`;
    file/object/lakehouse connectors `deferred` until F-CONN-P0-LOCAL/P1 lands)
  - Capability declarations match status (ready ⇒ supports_connection_test, etc.)
  - Credential schema serialisation
  - Filter API (category, priority, status, local_only)
  - DEFERRED specs require a deferred_reason
  - Duplicate registration is rejected
  - Catalog endpoint returns the registry contents and rejects unauthenticated calls
  - Error code constants are aligned with spec §13.4
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    TenantAPIError,
    get_actor_context,
    tenant_api_error_handler,
)
from app.api.v1.endpoints.connector_catalog import router as catalog_router
from app.services.datasources.connectors import registry as connectors_module
from app.services.datasources.connectors.registry import (
    ConnectorCapabilities,
    ConnectorCategory,
    ConnectorPriority,
    ConnectorRegistry,
    ConnectorSpec,
    ConnectorStatus,
    CredentialField,
    CredentialFieldType,
    registry,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

ACTOR_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _user_actor():
    return ActorContext(actor_id=ACTOR_ID, actor_role="business_analyst", tenant_id=TENANT_ID)


def _make_client(actor_factory=_user_actor):
    app = FastAPI()
    app.include_router(catalog_router, prefix="/api/v1")
    app.add_exception_handler(TenantAPIError, tenant_api_error_handler)
    app.dependency_overrides[get_actor_context] = lambda: actor_factory()
    return TestClient(app, raise_server_exceptions=False)


# ── Registry contents ────────────────────────────────────────────────────────


class TestRegistryContents:
    def test_postgresql_is_ready_and_local(self):
        spec = registry.get("postgresql")
        assert spec is not None
        assert spec.status == ConnectorStatus.READY
        assert spec.priority == ConnectorPriority.P0
        assert spec.capabilities.local_test_available is True
        assert spec.capabilities.supports_connection_test is True
        assert spec.capabilities.requires_external_credentials is False

    def test_p0_required_connectors_present(self):
        # spec §7.1 — every entry must be in the registry, regardless of status
        expected = {
            "csv",
            "excel",
            "postgresql",
            "mssql",
            "snowflake",
            "databricks",
            "bigquery",
            "s3",
            "adls_gen2",
            "parquet",
        }
        present = {s.type for s in registry.list(priority=ConnectorPriority.P0)}
        missing = expected - present
        assert not missing, f"Missing P0 connectors: {missing}"

    def test_p1_required_connectors_present(self):
        expected = {
            "oracle",
            "redshift",
            "synapse",
            "iceberg",
            "hive_metastore",
            "trino",
            "gcs",
            "json",
            "dbt_manifest",
            "powerbi",
        }
        present = {s.type for s in registry.list(priority=ConnectorPriority.P1)}
        missing = expected - present
        assert not missing, f"Missing P1 connectors: {missing}"

    def test_cloud_connectors_require_external_credentials(self):
        for t in ("snowflake", "bigquery", "databricks", "adls_gen2", "redshift", "synapse", "gcs"):
            spec = registry.get(t)
            assert spec is not None, f"{t!r} not registered"
            assert spec.capabilities.requires_external_credentials is True
            assert spec.capabilities.local_test_available is False

    def test_no_unimplemented_connector_marked_ready(self):
        # Truthfulness: connectors marked `ready` must have a real
        # implementation backed by tests. Update this list as connectors land.
        # Currently `ready`:
        #   - postgresql (F-CONN-CORE)
        #   - csv / excel / json / parquet / s3 (F-CONN-P0-LOCAL)
        ready = sorted(s.type for s in registry.list(status=ConnectorStatus.READY))
        assert ready == [
            "csv",
            "excel",
            "json",
            "parquet",
            "postgresql",
            "s3",
        ], f"READY connectors changed unexpectedly. Got: {ready}"

    def test_deferred_specs_have_reason(self):
        for spec in registry.list(status=ConnectorStatus.DEFERRED):
            assert spec.deferred_reason, f"{spec.type!r} is DEFERRED but has no deferred_reason"


# ── Credential schema serialisation ──────────────────────────────────────────


class TestCredentialSchema:
    def test_postgresql_jdbc_fields(self):
        spec = registry.get("postgresql")
        names = {f.name for f in spec.credential_schema}
        assert {"host", "port", "database", "username", "password"} <= names

    def test_password_is_secret_type(self):
        for t in ("postgresql", "mysql", "mssql", "oracle"):
            spec = registry.get(t)
            assert spec is not None
            password = next(f for f in spec.credential_schema if f.name == "password")
            assert password.type == CredentialFieldType.SECRET

    def test_field_to_dict_omits_none(self):
        f = CredentialField("host", CredentialFieldType.STRING, "Host")
        d = f.to_dict()
        assert d == {
            "name": "host",
            "type": "string",
            "label": "Host",
            "required": True,
        }

    def test_field_to_dict_includes_optionals(self):
        f = CredentialField(
            "ssl_mode",
            CredentialFieldType.SELECT,
            "SSL Mode",
            required=False,
            options=["disable", "require"],
            placeholder="require",
            help_text="TLS mode",
        )
        d = f.to_dict()
        assert d["options"] == ["disable", "require"]
        assert d["placeholder"] == "require"
        assert d["help_text"] == "TLS mode"
        assert d["required"] is False

    def test_spec_to_dict_round_trip(self):
        spec = registry.get("postgresql")
        d = spec.to_dict()
        assert d["type"] == "postgresql"
        assert d["status"] == "ready"
        assert d["priority"] == "P0"
        assert d["category"] == "database"
        assert isinstance(d["credential_schema"], list)
        assert isinstance(d["capabilities"], dict)


# ── Registry filtering and registration ──────────────────────────────────────


class TestRegistryFilters:
    def test_filter_by_category(self):
        warehouses = registry.list(category=ConnectorCategory.WAREHOUSE)
        types = {s.type for s in warehouses}
        assert {"snowflake", "bigquery", "redshift", "synapse"} <= types

    def test_filter_by_status(self):
        deferred = registry.list(status=ConnectorStatus.DEFERRED)
        # Spec §8: DEFERRED is a real status, must yield at least one result
        assert len(deferred) >= 1

    def test_local_only_true_excludes_cloud(self):
        local = registry.list(local_only=True)
        for s in local:
            assert s.capabilities.local_test_available is True
        types = {s.type for s in local}
        assert "snowflake" not in types  # cloud, not local

    def test_local_only_false_keeps_only_cloud(self):
        cloud = registry.list(local_only=False)
        for s in cloud:
            assert s.capabilities.local_test_available is False


class TestRegistryRegistration:
    def test_register_duplicate_rejected(self):
        r = ConnectorRegistry()
        spec = ConnectorSpec(
            type="x",
            display_name="X",
            category=ConnectorCategory.DATABASE,
            priority=ConnectorPriority.P0,
            status=ConnectorStatus.INTEGRATION_READY,
            description="x",
        )
        r.register(spec)
        with pytest.raises(ValueError, match="already registered"):
            r.register(spec)

    def test_register_deferred_without_reason_rejected(self):
        r = ConnectorRegistry()
        bad = ConnectorSpec(
            type="x",
            display_name="X",
            category=ConnectorCategory.DATABASE,
            priority=ConnectorPriority.P0,
            status=ConnectorStatus.DEFERRED,
            description="x",
            deferred_reason=None,
        )
        with pytest.raises(ValueError, match="deferred_reason"):
            r.register(bad)


# ── Catalog endpoint ────────────────────────────────────────────────────────


class TestCatalogEndpoint:
    def test_list_returns_all_connectors(self):
        client = _make_client()
        resp = client.get("/api/v1/connectors")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == len(registry.types())
        types = {item["type"] for item in body["items"]}
        assert "postgresql" in types
        assert "snowflake" in types

    def test_list_filter_by_priority(self):
        client = _make_client()
        resp = client.get("/api/v1/connectors", params={"priority": "P0"})
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["priority"] == "P0"

    def test_list_filter_by_status(self):
        client = _make_client()
        resp = client.get("/api/v1/connectors", params={"status": "ready"})
        assert resp.status_code == 200
        body = resp.json()
        assert {i["type"] for i in body["items"]} == {
            "csv",
            "excel",
            "json",
            "parquet",
            "postgresql",
            "s3",
        }

    def test_list_filter_invalid_priority_400(self):
        client = _make_client()
        resp = client.get("/api/v1/connectors", params={"priority": "P99"})
        assert resp.status_code == 400

    def test_list_filter_local_only(self):
        client = _make_client()
        resp = client.get("/api/v1/connectors", params={"local_only": "true"})
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["capabilities"]["local_test_available"] is True

    def test_get_single_connector(self):
        client = _make_client()
        resp = client.get("/api/v1/connectors/postgresql")
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "postgresql"
        assert body["status"] == "ready"
        assert any(f["name"] == "password" for f in body["credential_schema"])

    def test_get_unknown_connector_404(self):
        client = _make_client()
        resp = client.get("/api/v1/connectors/nonexistent")
        assert resp.status_code == 404

    def test_unauthenticated_request_blocked(self):
        # Build a client WITHOUT overriding get_actor_context — request must fail.
        app = FastAPI()
        app.include_router(catalog_router, prefix="/api/v1")
        app.add_exception_handler(TenantAPIError, tenant_api_error_handler)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/connectors")
        assert resp.status_code in (401, 403, 422)


# ── Spec §13.4 error codes ──────────────────────────────────────────────────


class TestSpecErrorCodes:
    def test_connection_codes_present(self):
        from app.services.connections import errors

        assert errors.CONNECTION_AUTH_FAILED == "CONNECTION_AUTH_FAILED"
        assert errors.CONNECTION_TIMEOUT == "CONNECTION_TIMEOUT"
        assert errors.CONNECTION_NETWORK_ERROR == "CONNECTION_NETWORK_ERROR"
        assert errors.CONNECTION_PERMISSION_DENIED == "CONNECTION_PERMISSION_DENIED"
        assert errors.CONNECTION_INVALID_CONFIG == "CONNECTION_INVALID_CONFIG"
        assert errors.UNKNOWN_CONNECTOR_TYPE == "UNKNOWN_CONNECTOR_TYPE"
        assert errors.RBAC_FORBIDDEN == "RBAC_FORBIDDEN"
        assert errors.TENANT_ISOLATION_VIOLATION == "TENANT_ISOLATION_VIOLATION"

    def test_dataset_codes_present(self):
        from app.services.datasets import errors

        assert errors.DATASET_NOT_FOUND == "DATASET_NOT_FOUND"
        assert errors.DATASET_ACCESS_DENIED == "DATASET_ACCESS_DENIED"
        assert errors.DATASET_EMPTY == "DATASET_EMPTY"
        assert errors.DATASET_PREVIEW_FAILED == "DATASET_PREVIEW_FAILED"
        assert errors.UNSUPPORTED_FILE_TYPE == "UNSUPPORTED_FILE_TYPE"
        assert errors.FILE_PARSE_ERROR == "FILE_PARSE_ERROR"
        assert errors.CHECK_EXECUTION_FAILED == "CHECK_EXECUTION_FAILED"
