"""
F130 P03 — Tenant Glossary API Tests
========================================
15 tests covering:
  - GlossaryTermResponse schema change (tenant_id field)
  - GlossaryService tenant-scoped methods
  - tenant_glossary endpoint router wiring
  - GlossaryTermLoader tenant_id parameter (2 tests)
  - GlossaryTermLoader backward compatibility (1 test)
  - router.py registration check
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, call, patch
from uuid import UUID, uuid4

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

TENANT_ID = uuid4()
WORKSPACE_ID = uuid4()
TERM_ID = uuid4()


def _make_term_response(tenant_id: UUID = TENANT_ID):
    from app.schemas.glossary import GlossaryTermResponse

    return GlossaryTermResponse(
        term_id=TERM_ID,
        workspace_id=WORKSPACE_ID,
        business_name="Customer ID",
        technical_name="cust_id",
        definition="Unique customer identifier",
        synonyms=["client_id"],
        domain="customers",
        linked_asset_ids=[],
        source="manual",
        trust_level="high",
        created_at=datetime.now(UTC),
        tenant_id=tenant_id,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1. Schema tests
# ──────────────────────────────────────────────────────────────────────────────


class TestGlossarySchema:
    def test_term_response_has_tenant_id_field(self):
        import inspect

        from app.schemas.glossary import GlossaryTermResponse

        fields = GlossaryTermResponse.model_fields
        assert "tenant_id" in fields, "GlossaryTermResponse must have tenant_id field"

    def test_tenant_id_is_optional(self):
        from app.schemas.glossary import GlossaryTermResponse

        field = GlossaryTermResponse.model_fields["tenant_id"]
        # Optional means default is None
        assert field.default is None or field.is_required() is False

    def test_term_response_tenant_id_none_by_default(self):
        from app.schemas.glossary import GlossaryTermResponse

        term = GlossaryTermResponse(
            term_id=TERM_ID,
            workspace_id=WORKSPACE_ID,
            business_name="Test",
            technical_name=None,
            definition=None,
            synonyms=[],
            domain=None,
            linked_asset_ids=[],
            source="manual",
            trust_level="medium",
            created_at=datetime.now(UTC),
        )
        assert term.tenant_id is None


# ──────────────────────────────────────────────────────────────────────────────
# 2. GlossaryService tenant method tests
# ──────────────────────────────────────────────────────────────────────────────


class TestGlossaryServiceTenantMethods:
    def test_service_has_create_for_tenant(self):
        from app.services.glossary.service import GlossaryService

        assert hasattr(GlossaryService, "create_term_for_tenant")

    def test_service_has_get_for_tenant(self):
        from app.services.glossary.service import GlossaryService

        assert hasattr(GlossaryService, "get_term_for_tenant")

    def test_service_has_list_for_tenant(self):
        from app.services.glossary.service import GlossaryService

        assert hasattr(GlossaryService, "list_terms_for_tenant")

    def test_service_has_update_for_tenant(self):
        from app.services.glossary.service import GlossaryService

        assert hasattr(GlossaryService, "update_term_for_tenant")

    def test_service_has_delete_for_tenant(self):
        from app.services.glossary.service import GlossaryService

        assert hasattr(GlossaryService, "delete_term_for_tenant")

    def test_list_for_tenant_returns_glossary_list_response(self):
        from app.schemas.glossary import GlossaryListResponse
        from app.services.glossary.service import GlossaryService

        svc = GlossaryService()

        # Mock DB to return empty result
        mock_scalar = MagicMock()
        mock_scalar.return_value = 0
        mock_result_count = MagicMock()
        mock_result_count.scalar.return_value = 0
        mock_result_rows = MagicMock()
        mock_result_rows.fetchall.return_value = []

        mock_db = MagicMock()
        mock_db.execute.side_effect = [mock_result_count, mock_result_rows]

        result = svc.list_terms_for_tenant(mock_db, TENANT_ID)
        assert isinstance(result, GlossaryListResponse)
        assert result.total == 0
        assert result.items == []

    def test_get_for_tenant_returns_none_when_missing(self):
        from app.services.glossary.service import GlossaryService

        svc = GlossaryService()

        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db = MagicMock()
        mock_db.execute.return_value = mock_result

        result = svc.get_term_for_tenant(mock_db, TENANT_ID, TERM_ID)
        assert result is None

    def test_delete_for_tenant_returns_false_when_missing(self):
        from app.services.glossary.service import GlossaryService

        svc = GlossaryService()

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db = MagicMock()
        mock_db.execute.return_value = mock_result

        result = svc.delete_term_for_tenant(mock_db, TENANT_ID, TERM_ID)
        assert result is False


# ──────────────────────────────────────────────────────────────────────────────
# 3. Endpoint router tests
# ──────────────────────────────────────────────────────────────────────────────


class TestTenantGlossaryEndpoints:
    def test_router_import(self):
        from app.api.v1.endpoints.tenant_glossary import router

        assert router is not None

    def test_router_prefix(self):
        from app.api.v1.endpoints.tenant_glossary import router

        assert "tenants" in router.prefix
        assert "glossary" in router.prefix

    def test_router_registered_in_router_py(self):
        router_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "app",
            "api",
            "v1",
            "router.py",
        )
        with open(router_path, encoding="utf-8") as f:
            source = f.read()
        assert "tenant_glossary" in source
        assert "tenant_glossary.router" in source

    def test_service_instance_on_module(self):
        from app.api.v1.endpoints.tenant_glossary import _service
        from app.services.glossary.service import GlossaryService

        assert isinstance(_service, GlossaryService)


# ──────────────────────────────────────────────────────────────────────────────
# 4. GlossaryTermLoader tenant_id tests
# ──────────────────────────────────────────────────────────────────────────────


class TestGlossaryLoaderTenantId:
    def test_loader_accepts_tenant_id_kwarg(self):
        import inspect

        from app.services.nl_rule_builder.glossary_loader import GlossaryTermLoader

        sig = inspect.signature(GlossaryTermLoader.load_glossary_for_rule)
        assert "tenant_id" in sig.parameters, (
            "load_glossary_for_rule must accept tenant_id parameter"
        )

    def test_loader_uses_tenant_query_when_tenant_id_provided(self):
        from app.schemas.glossary import GlossaryListResponse
        from app.services.nl_rule_builder.glossary_loader import GlossaryTermLoader

        mock_svc = MagicMock()
        mock_svc.list_terms_for_tenant.return_value = GlossaryListResponse(
            items=[], total=0, page=1, page_size=20
        )

        loader = GlossaryTermLoader(glossary_service=mock_svc)
        loader.load_glossary_for_rule(
            db=MagicMock(),
            workspace_id=WORKSPACE_ID,
            rule_text="email must not be null",
            tenant_id=TENANT_ID,
        )

        mock_svc.list_terms_for_tenant.assert_called_once()
        mock_svc.list_terms.assert_not_called()

    def test_loader_resolves_tenant_from_workspace_when_no_tenant_id(self):
        """When tenant_id is not provided, the loader resolves the tenant_id
        from the workspace and still queries the shared tenant glossary —
        all workspaces in a tenant share the same glossary."""
        from app.schemas.glossary import GlossaryListResponse
        from app.services.nl_rule_builder.glossary_loader import GlossaryTermLoader

        mock_svc = MagicMock()
        mock_svc.list_terms_for_tenant.return_value = GlossaryListResponse(
            items=[], total=0, page=1, page_size=20
        )

        # Mock the workspace→tenant lookup performed inside the loader.
        mock_row = MagicMock()
        mock_row.tenant_id = TENANT_ID
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db = MagicMock()
        mock_db.execute.return_value = mock_result

        loader = GlossaryTermLoader(glossary_service=mock_svc)
        loader.load_glossary_for_rule(
            db=mock_db,
            workspace_id=WORKSPACE_ID,
            rule_text="email must not be null",
            # No tenant_id — resolved from workspace
        )

        mock_svc.list_terms_for_tenant.assert_called_once()
        mock_svc.list_terms.assert_not_called()
