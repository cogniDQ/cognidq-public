"""
F134 P06 — Tests for Demo Template Seeder + TemplateSeederService + endpoint

Tests:
  - GeneralDQSeeder content counts and idempotency
  - TemplateSeederService module loading and delegation
  - GET /admin/demo-templates (list + detail)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest
from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    TenantAPIError,
    get_actor_context,
    tenant_api_error_handler,
)
from app.api.v1.endpoints.admin_demo_templates import router as templates_router
from app.models.database import get_db
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Helpers ───────────────────────────────────────────────────────────────────

ADMIN_ACTOR_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
TENANT_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def _admin_actor():
    return ActorContext(actor_id=ADMIN_ACTOR_ID, actor_role="platform_admin")


def _viewer_actor():
    return ActorContext(
        actor_id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        actor_role="platform_viewer",
    )


def _fake_template(template_id: str = "general_dq"):
    return {
        "id": template_id,
        "display_name": "General Data Quality",
        "description": "E-commerce DQ demo.",
        "seeder_module": "app.services.demo.templates.general_dq.seeder",
        "default_duration_days": 7,
        "is_enabled": True,
        "created_at": datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
    }


# ── GeneralDQSeeder unit tests ────────────────────────────────────────────────


class TestGeneralDQSeeder:
    def _make_db(self):
        """Return a mock db that returns no existing rows for idempotency check,
        then records execute() calls."""
        db = MagicMock()
        # By default, idempotency check returns None (not seeded)
        db.execute.return_value.fetchone.return_value = None
        return db

    def test_seed_calls_execute_for_all_content_types(self):
        from app.services.demo.templates.general_dq.seeder import GeneralDQSeeder

        db = self._make_db()
        seeder = GeneralDQSeeder(db)
        seeder.seed(TENANT_ID, WORKSPACE_ID)

        calls = db.execute.call_count
        # 1 idempotency check + 1 data_source + 3 datasets + 5 rules + 1 flow
        # + 10 issues + 1 dashboard + 10 glossary = 32 calls
        assert calls >= 30

    def test_seed_is_idempotent_when_already_seeded(self):
        from app.services.demo.templates.general_dq.seeder import GeneralDQSeeder

        db = self._make_db()
        # Idempotency check returns a row → already seeded
        db.execute.return_value.fetchone.return_value = MagicMock()

        seeder = GeneralDQSeeder(db)
        seeder.seed(TENANT_ID, WORKSPACE_ID)

        # Only the idempotency SELECT should be called
        assert db.execute.call_count == 1

    def test_template_id_attribute(self):
        from app.services.demo.templates.general_dq.seeder import GeneralDQSeeder

        seeder = GeneralDQSeeder(MagicMock())
        assert seeder.template_id == "general_dq"

    def test_seed_creates_data_source(self):
        from app.services.demo.templates.general_dq.seeder import GeneralDQSeeder

        db = self._make_db()
        seeder = GeneralDQSeeder(db)
        seeder.seed(TENANT_ID, WORKSPACE_ID)

        sql_calls = [str(c.args[0]) for c in db.execute.call_args_list]
        assert any("data_sources" in s for s in sql_calls)

    def test_seed_creates_three_datasets(self):
        from app.services.demo.templates.general_dq.seeder import GeneralDQSeeder

        db = self._make_db()
        seeder = GeneralDQSeeder(db)
        seeder.seed(TENANT_ID, WORKSPACE_ID)

        sql_calls = [str(c.args[0]) for c in db.execute.call_args_list]
        dataset_inserts = [s for s in sql_calls if "control.datasets" in s and "INSERT" in s]
        assert len(dataset_inserts) >= 3

    def test_seed_creates_five_rules(self):
        from app.services.demo.templates.general_dq.seeder import GeneralDQSeeder

        db = self._make_db()
        seeder = GeneralDQSeeder(db)
        seeder.seed(TENANT_ID, WORKSPACE_ID)

        sql_calls = [str(c.args[0]) for c in db.execute.call_args_list]
        rule_inserts = [s for s in sql_calls if "dq_rules" in s and "INSERT" in s]
        assert len(rule_inserts) >= 5

    def test_seed_creates_one_flow(self):
        from app.services.demo.templates.general_dq.seeder import GeneralDQSeeder

        db = self._make_db()
        seeder = GeneralDQSeeder(db)
        seeder.seed(TENANT_ID, WORKSPACE_ID)

        sql_calls = [str(c.args[0]) for c in db.execute.call_args_list]
        flow_inserts = [s for s in sql_calls if "dq_flows" in s and "INSERT" in s]
        assert len(flow_inserts) >= 1

    def test_seed_creates_ten_issues(self):
        from app.services.demo.templates.general_dq.seeder import GeneralDQSeeder

        db = self._make_db()
        seeder = GeneralDQSeeder(db)
        seeder.seed(TENANT_ID, WORKSPACE_ID)

        sql_calls = [str(c.args[0]) for c in db.execute.call_args_list]
        issue_inserts = [s for s in sql_calls if "issues" in s and "INSERT" in s]
        assert len(issue_inserts) >= 10

    def test_seed_creates_one_dashboard(self):
        from app.services.demo.templates.general_dq.seeder import GeneralDQSeeder

        db = self._make_db()
        seeder = GeneralDQSeeder(db)
        seeder.seed(TENANT_ID, WORKSPACE_ID)

        sql_calls = [str(c.args[0]) for c in db.execute.call_args_list]
        dash_inserts = [s for s in sql_calls if "dashboards" in s and "INSERT" in s]
        assert len(dash_inserts) >= 1

    def test_seed_creates_ten_glossary_terms(self):
        from app.services.demo.templates.general_dq.seeder import GeneralDQSeeder

        db = self._make_db()
        seeder = GeneralDQSeeder(db)
        seeder.seed(TENANT_ID, WORKSPACE_ID)

        sql_calls = [str(c.args[0]) for c in db.execute.call_args_list]
        glossary_inserts = [s for s in sql_calls if "metadata_term_index" in s and "INSERT" in s]
        assert len(glossary_inserts) >= 10

    def test_deterministic_ids_same_workspace(self):
        from app.services.demo.templates.general_dq.seeder import _uid

        id1 = _uid(WORKSPACE_ID, "ds_customers")
        id2 = _uid(WORKSPACE_ID, "ds_customers")
        assert id1 == id2

    def test_deterministic_ids_differ_across_workspaces(self):
        from app.services.demo.templates.general_dq.seeder import _uid

        other_ws = uuid.uuid4()
        id1 = _uid(WORKSPACE_ID, "ds_customers")
        id2 = _uid(other_ws, "ds_customers")
        assert id1 != id2


# ── TemplateSeederService tests ───────────────────────────────────────────────


class TestTemplateSeederService:
    def test_raises_seeding_error_when_template_not_found(self):
        from app.services.demo.template_seeder_service import SeedingError, TemplateSeederService

        db = MagicMock()
        svc = TemplateSeederService(db)
        svc._template_repo.find_by_id = MagicMock(return_value=None)

        with pytest.raises(SeedingError, match="not found"):
            svc.seed("nonexistent_template", TENANT_ID, WORKSPACE_ID)

    def test_raises_seeding_error_on_bad_module(self):
        from app.services.demo.template_seeder_service import SeedingError, TemplateSeederService

        db = MagicMock()
        svc = TemplateSeederService(db)
        svc._template_repo.find_by_id = MagicMock(
            return_value={
                "id": "bad_template",
                "seeder_module": "app.does.not.exist.seeder",
            }
        )

        with pytest.raises(SeedingError, match="Cannot import"):
            svc.seed("bad_template", TENANT_ID, WORKSPACE_ID)

    def test_loads_and_calls_general_dq_seeder(self):
        from app.services.demo.template_seeder_service import TemplateSeederService

        db = MagicMock()
        svc = TemplateSeederService(db)
        svc._template_repo.find_by_id = MagicMock(return_value=_fake_template())

        with patch(
            "app.services.demo.templates.general_dq.seeder.GeneralDQSeeder.seed"
        ) as mock_seed:
            svc.seed("general_dq", TENANT_ID, WORKSPACE_ID)
            mock_seed.assert_called_once_with(TENANT_ID, WORKSPACE_ID)

    def test_raises_when_no_seeder_module_configured(self):
        from app.services.demo.template_seeder_service import SeedingError, TemplateSeederService

        db = MagicMock()
        svc = TemplateSeederService(db)
        svc._template_repo.find_by_id = MagicMock(
            return_value={
                "id": "some_template",
                "seeder_module": "",
            }
        )

        with pytest.raises(SeedingError, match="no seeder_module"):
            svc.seed("some_template", TENANT_ID, WORKSPACE_ID)


# ── Admin demo-templates endpoint tests ───────────────────────────────────────


def _make_templates_client(mock_db, actor_factory=_admin_actor):
    _app = FastAPI()
    _app.include_router(templates_router, prefix="/api/v1")
    _app.dependency_overrides[get_db] = lambda: mock_db
    _app.add_exception_handler(TenantAPIError, tenant_api_error_handler)
    _app.dependency_overrides[get_actor_context] = lambda: actor_factory()
    return TestClient(_app, raise_server_exceptions=False)


class TestListDemoTemplatesEndpoint:
    def test_returns_200_with_templates(self):
        mock_db = MagicMock()
        with patch(
            "app.services.sandbox.demo_template_repository.DemoTemplateRepository.list_enabled"
        ) as mock_list:
            mock_list.return_value = [_fake_template()]
            client = _make_templates_client(mock_db)
            resp = client.get("/api/v1/admin/demo-templates")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == "general_dq"

    def test_returns_403_for_platform_viewer(self):
        mock_db = MagicMock()
        client = _make_templates_client(mock_db, actor_factory=_viewer_actor)
        resp = client.get("/api/v1/admin/demo-templates")
        assert resp.status_code == 403

    def test_empty_list(self):
        mock_db = MagicMock()
        with patch(
            "app.services.sandbox.demo_template_repository.DemoTemplateRepository.list_enabled"
        ) as mock_list:
            mock_list.return_value = []
            client = _make_templates_client(mock_db)
            resp = client.get("/api/v1/admin/demo-templates")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestGetDemoTemplateEndpoint:
    def test_returns_200_when_found(self):
        mock_db = MagicMock()
        with patch(
            "app.services.sandbox.demo_template_repository.DemoTemplateRepository.find_by_id"
        ) as mock_get:
            mock_get.return_value = _fake_template()
            client = _make_templates_client(mock_db)
            resp = client.get("/api/v1/admin/demo-templates/general_dq")
        assert resp.status_code == 200
        assert resp.json()["id"] == "general_dq"

    def test_returns_404_when_not_found(self):
        mock_db = MagicMock()
        with patch(
            "app.services.sandbox.demo_template_repository.DemoTemplateRepository.find_by_id"
        ) as mock_get:
            mock_get.return_value = None
            client = _make_templates_client(mock_db)
            resp = client.get("/api/v1/admin/demo-templates/unknown")
        assert resp.status_code == 404

    def test_returns_403_for_wrong_role(self):
        mock_db = MagicMock()
        client = _make_templates_client(mock_db, actor_factory=_viewer_actor)
        resp = client.get("/api/v1/admin/demo-templates/general_dq")
        assert resp.status_code == 403
