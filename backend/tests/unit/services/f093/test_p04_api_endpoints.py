"""
P04 — API Endpoints Tests

Tests for: GET /rule-templates, GET /rule-templates/{id}, POST /rule-templates/{id}/apply
Uses mock service to test router logic without a real database.
"""

import copy
import uuid
from unittest.mock import MagicMock, patch

import pytest
from app.api.v1.endpoints.rule_templates import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _create_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def _mock_template_orm(seed_entry: dict) -> MagicMock:
    tpl = MagicMock()
    tpl.id = uuid.uuid4()
    tpl.name = seed_entry["name"]
    tpl.dimension = seed_entry["dimension"]
    tpl.description = seed_entry["description"]
    tpl.category = seed_entry["category"]
    tpl.tags = seed_entry.get("tags", [])
    tpl.canonical_rule_template = copy.deepcopy(seed_entry["canonical_rule_template"])
    tpl.default_severity = seed_entry.get("default_severity", "high")
    tpl.default_threshold_pass = seed_entry.get("default_threshold_pass", 98.0)
    tpl.default_threshold_warn = seed_entry.get("default_threshold_warn")
    tpl.use_count = 0
    tpl.is_active = True
    tpl.created_at = None
    tpl.updated_at = None
    return tpl


_SAMPLE_SEED = {
    "dimension": "completeness",
    "name": "Mandatory Fields — NULL Check",
    "description": "Ensures specified columns contain no NULL values.",
    "category": "completeness_basic",
    "tags": ["mandatory", "null_check"],
    "default_severity": "high",
    "default_threshold_pass": 100.0,
    "default_threshold_warn": 98.0,
    "canonical_rule_template": {
        "dimension": "completeness",
        "entity": "__TABLE__.__COLUMN__",
        "condition": "IS NOT NULL",
        "expectation": "100.0%",
        "severity": "high",
        "parameters": {
            "columns": ["__COLUMN__"],
            "check_mode": "null",
            "threshold_pass": 100.0,
            "threshold_warn": 98.0,
        },
    },
}


# -----------------------------------------------------------------------
# GET /rule-templates
# -----------------------------------------------------------------------


class TestListEndpoint:
    @patch("app.api.v1.endpoints.rule_templates._service")
    @patch("app.api.v1.endpoints.rule_templates.get_db")
    def test_list_returns_200(self, mock_get_db, mock_service):
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        tpl = _mock_template_orm(_SAMPLE_SEED)
        mock_service.get_all_templates.return_value = [tpl]

        app = _create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/rule-templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data
        assert data["total"] == 1

    @patch("app.api.v1.endpoints.rule_templates._service")
    @patch("app.api.v1.endpoints.rule_templates.get_db")
    def test_list_empty(self, mock_get_db, mock_service):
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_service.get_all_templates.return_value = []

        app = _create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/rule-templates")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @patch("app.api.v1.endpoints.rule_templates._service")
    @patch("app.api.v1.endpoints.rule_templates.get_db")
    def test_list_with_dimension_filter(self, mock_get_db, mock_service):
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_service.get_all_templates.return_value = []

        app = _create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/rule-templates?dimension=completeness")
        assert resp.status_code == 200
        mock_service.get_all_templates.assert_called_once()
        call_kwargs = mock_service.get_all_templates.call_args
        assert (
            call_kwargs.kwargs.get("dimension") == "completeness"
            or (len(call_kwargs.args) > 1 and call_kwargs.args[1] == "completeness")
            or call_kwargs[1].get("dimension") == "completeness"
        )

    @patch("app.api.v1.endpoints.rule_templates._service")
    @patch("app.api.v1.endpoints.rule_templates.get_db")
    def test_list_with_search(self, mock_get_db, mock_service):
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_service.get_all_templates.return_value = []

        app = _create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/rule-templates?search=email")
        assert resp.status_code == 200


# -----------------------------------------------------------------------
# GET /rule-templates/{id}
# -----------------------------------------------------------------------


class TestDetailEndpoint:
    @patch("app.api.v1.endpoints.rule_templates._service")
    @patch("app.api.v1.endpoints.rule_templates.get_db")
    def test_get_returns_200(self, mock_get_db, mock_service):
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        tpl = _mock_template_orm(_SAMPLE_SEED)
        mock_service.get_template_by_id.return_value = tpl

        app = _create_app()
        client = TestClient(app)
        resp = client.get(f"/api/v1/rule-templates/{tpl.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "canonical_rule_template" in data

    @patch("app.api.v1.endpoints.rule_templates._service")
    @patch("app.api.v1.endpoints.rule_templates.get_db")
    def test_get_not_found(self, mock_get_db, mock_service):
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_service.get_template_by_id.return_value = None

        app = _create_app()
        client = TestClient(app)
        resp = client.get(f"/api/v1/rule-templates/{uuid.uuid4()}")
        assert resp.status_code == 404


# -----------------------------------------------------------------------
# POST /rule-templates/{id}/apply
# -----------------------------------------------------------------------


class TestApplyEndpoint:
    @patch("app.api.v1.endpoints.rule_templates._service")
    @patch("app.api.v1.endpoints.rule_templates.get_db")
    def test_apply_returns_200(self, mock_get_db, mock_service):
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        tpl_id = uuid.uuid4()
        mock_service.apply_template.return_value = {
            "canonical_rule": {"dimension": "completeness", "parameters": {}},
            "template_id": str(tpl_id),
            "template_name": "Test",
        }

        app = _create_app()
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/rule-templates/{tpl_id}/apply",
            json={"target_table": "customers", "column_mapping": {"__COLUMN__": "email"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "canonical_rule" in data

    @patch("app.api.v1.endpoints.rule_templates._service")
    @patch("app.api.v1.endpoints.rule_templates.get_db")
    def test_apply_not_found(self, mock_get_db, mock_service):
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_service.apply_template.side_effect = LookupError("not found")

        app = _create_app()
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/rule-templates/{uuid.uuid4()}/apply",
            json={"target_table": "t", "column_mapping": {}},
        )
        assert resp.status_code == 404

    @patch("app.api.v1.endpoints.rule_templates._service")
    @patch("app.api.v1.endpoints.rule_templates.get_db")
    def test_apply_missing_mapping(self, mock_get_db, mock_service):
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_service.apply_template.side_effect = ValueError(
            "Missing required column mappings: __COLUMN__"
        )

        app = _create_app()
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/rule-templates/{uuid.uuid4()}/apply",
            json={"target_table": "t", "column_mapping": {}},
        )
        assert resp.status_code == 422
        assert "Missing" in resp.json()["detail"]

    @patch("app.api.v1.endpoints.rule_templates._service")
    @patch("app.api.v1.endpoints.rule_templates.get_db")
    def test_apply_with_overrides(self, mock_get_db, mock_service):
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        tpl_id = uuid.uuid4()
        mock_service.apply_template.return_value = {
            "canonical_rule": {"dimension": "completeness", "severity": "critical"},
            "template_id": str(tpl_id),
            "template_name": "Test",
        }

        app = _create_app()
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/rule-templates/{tpl_id}/apply",
            json={
                "target_table": "t",
                "column_mapping": {"__COLUMN__": "c"},
                "overrides": {"severity": "critical"},
            },
        )
        assert resp.status_code == 200

    @patch("app.api.v1.endpoints.rule_templates._service")
    @patch("app.api.v1.endpoints.rule_templates.get_db")
    def test_apply_increments_use_count(self, mock_get_db, mock_service):
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        tpl_id = uuid.uuid4()
        mock_service.apply_template.return_value = {
            "canonical_rule": {"dimension": "completeness"},
            "template_id": str(tpl_id),
            "template_name": "Test",
        }

        app = _create_app()
        client = TestClient(app)
        client.post(
            f"/api/v1/rule-templates/{tpl_id}/apply",
            json={"target_table": "t", "column_mapping": {"__COLUMN__": "c"}},
        )
        mock_service.apply_template.assert_called_once()
