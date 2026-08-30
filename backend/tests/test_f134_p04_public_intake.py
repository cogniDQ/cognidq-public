"""
F134 P04 — Tests for Public Intake API endpoints and DemoRequestService

API tests use a minimal FastAPI app containing only the demo_requests router,
so there is no dependency on pyspark or other heavy services.
Service/repo tests use MagicMock directly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from app.api.v1.endpoints.demo_requests import router as demo_requests_router
from app.models.database import get_db
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_row():
    """A typical DemoRequest dict returned by the repo."""
    return {
        "id": uuid.uuid4(),
        "status": "submitted",
        "public_status_token": "tok_" + "a" * 60,
        "work_email": "prospect@company.io",
        "first_name": "Alice",
        "last_name": "Smith",
        "company_name": "Acme Corp",
        "team_size": "11-50",
        "primary_use_case": "We need data quality checks.",
        "consent": True,
        "is_personal_email": False,
        "created_at": datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC),
        "decided_at": None,
    }


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def app_with_mock_db(mock_db):
    """Minimal FastAPI app with only the demo_requests router."""
    _app = FastAPI()
    _app.include_router(demo_requests_router, prefix="/api/v1")
    _app.dependency_overrides[get_db] = lambda: mock_db
    return _app


@pytest.fixture
def client(app_with_mock_db):
    with TestClient(app_with_mock_db, raise_server_exceptions=False) as c:
        yield c


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_row():
    """A typical DemoRequest dict returned by the repo."""
    return {
        "id": uuid.uuid4(),
        "status": "submitted",
        "public_status_token": "tok_" + "a" * 60,
        "work_email": "prospect@company.io",
        "first_name": "Alice",
        "last_name": "Smith",
        "company_name": "Acme Corp",
        "team_size": "11-50",
        "primary_use_case": "We need data quality checks.",
        "consent": True,
        "is_personal_email": False,
        "created_at": datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC),
        "decided_at": None,
    }


@pytest.fixture
def mock_db():
    return MagicMock()


# ── DemoRequestService unit tests ─────────────────────────────────────────────


class TestDemoRequestService:
    def test_find_active_by_email_delegates_to_repo(self, mock_db):
        from app.services.sandbox.demo_request_service import DemoRequestService

        mock_repo = MagicMock()
        mock_repo.find_active_by_email.return_value = None
        svc = DemoRequestService(mock_db, repo=mock_repo)
        result = svc.find_active_by_email("user@corp.com")
        mock_repo.find_active_by_email.assert_called_once_with("user@corp.com")
        assert result is None

    def test_create_delegates_to_repo(self, mock_db, fake_row):
        from app.services.sandbox.demo_request_service import DemoRequestService

        mock_repo = MagicMock()
        mock_repo.create.return_value = fake_row
        svc = DemoRequestService(mock_db, repo=mock_repo)
        result = svc.create(
            work_email="prospect@company.io",
            first_name="Alice",
            last_name="Smith",
            company_name="Acme Corp",
            team_size="11-50",
            primary_use_case="We need data quality checks.",
            consent=True,
        )
        assert mock_repo.create.called
        assert result == fake_row

    def test_create_flags_personal_email(self, mock_db, fake_row):
        from app.services.sandbox.demo_request_service import DemoRequestService

        mock_repo = MagicMock()
        personal_row = dict(fake_row, work_email="user@gmail.com", is_personal_email=True)
        mock_repo.create.return_value = personal_row
        svc = DemoRequestService(mock_db, repo=mock_repo)
        svc.create(
            work_email="user@gmail.com",
            first_name="Alice",
            last_name="Smith",
            company_name="Acme",
            team_size="1-10",
            primary_use_case="We need data quality checks.",
            consent=True,
        )
        # The keyword arg passed to repo should have is_personal_email=True
        call_kwargs = mock_repo.create.call_args.kwargs
        assert call_kwargs["is_personal_email"] is True

    def test_get_status_delegates_to_repo(self, mock_db, fake_row):
        from app.services.sandbox.demo_request_service import DemoRequestService

        mock_repo = MagicMock()
        mock_repo.find_by_public_token.return_value = fake_row
        svc = DemoRequestService(mock_db, repo=mock_repo)
        result = svc.get_status("some-token")
        mock_repo.find_by_public_token.assert_called_once_with("some-token")
        assert result == fake_row

    def test_get_status_returns_none_for_unknown_token(self, mock_db):
        from app.services.sandbox.demo_request_service import DemoRequestService

        mock_repo = MagicMock()
        mock_repo.find_by_public_token.return_value = None
        svc = DemoRequestService(mock_db, repo=mock_repo)
        assert svc.get_status("bad-token") is None

    def test_emit_request_received_email_is_noop(self, fake_row):
        from app.services.sandbox.demo_request_service import emit_request_received_email

        # Should not raise
        emit_request_received_email(fake_row)


# ── POST /api/v1/demo-requests ─────────────────────────────────────────────────


class TestCreateDemoRequestEndpoint:
    _VALID_BODY = {
        "work_email": "alice@company.io",
        "first_name": "Alice",
        "last_name": "Smith",
        "company_name": "Acme Corp",
        "team_size": "11-50",
        "primary_use_case": "We need to improve data quality across ETL.",
        "consent": True,
        "country": "US",
    }

    def test_valid_request_returns_201(self, client, fake_row):
        with (
            patch("app.api.v1.endpoints.demo_requests.DemoRequestService") as MockSvc,
            patch("app.api.v1.endpoints.demo_requests.emit_request_received_email"),
        ):
            instance = MockSvc.return_value
            instance.find_active_by_email.return_value = None
            instance.create.return_value = fake_row

            resp = client.post("/api/v1/demo-requests", json=self._VALID_BODY)

        assert resp.status_code == 201
        body = resp.json()
        assert "request_id" in body
        assert body["status"] == "submitted"
        assert "public_status_token" in body

    def test_missing_consent_returns_422(self, client):
        bad = dict(self._VALID_BODY, consent=False)
        resp = client.post("/api/v1/demo-requests", json=bad)
        assert resp.status_code == 422
        data = resp.json()
        fields = [f["field"] for f in data["error"]["fields"]]
        assert "consent" in fields

    def test_invalid_email_returns_422(self, client):
        bad = dict(self._VALID_BODY, work_email="notanemail")
        resp = client.post("/api/v1/demo-requests", json=bad)
        assert resp.status_code == 422

    def test_reserved_tld_email_returns_422(self, client):
        bad = dict(self._VALID_BODY, work_email="user@corp.test")
        resp = client.post("/api/v1/demo-requests", json=bad)
        assert resp.status_code == 422

    def test_invalid_team_size_returns_422(self, client):
        bad = dict(self._VALID_BODY, team_size="lots")
        resp = client.post("/api/v1/demo-requests", json=bad)
        assert resp.status_code == 422

    def test_short_use_case_returns_422(self, client):
        bad = dict(self._VALID_BODY, primary_use_case="short")
        resp = client.post("/api/v1/demo-requests", json=bad)
        assert resp.status_code == 422

    def test_duplicate_active_request_returns_200_with_duplicate_status(self, client, fake_row):
        with patch("app.api.v1.endpoints.demo_requests.DemoRequestService") as MockSvc:
            instance = MockSvc.return_value
            instance.find_active_by_email.return_value = fake_row

            resp = client.post("/api/v1/demo-requests", json=self._VALID_BODY)

        assert resp.status_code == 200
        assert resp.json()["status"] == "duplicate"
        assert "request_id" in resp.json()

    def test_personal_email_accepted_but_flagged(self, client, fake_row):
        personal_row = dict(fake_row, is_personal_email=True, work_email="alice@gmail.com")
        body = dict(self._VALID_BODY, work_email="alice@gmail.com")
        with (
            patch("app.api.v1.endpoints.demo_requests.DemoRequestService") as MockSvc,
            patch("app.api.v1.endpoints.demo_requests.emit_request_received_email"),
        ):
            instance = MockSvc.return_value
            instance.find_active_by_email.return_value = None
            instance.create.return_value = personal_row
            resp = client.post("/api/v1/demo-requests", json=body)

        assert resp.status_code == 201
        assert resp.json()["is_personal_email"] is True

    def test_email_is_sent_after_create(self, client, fake_row):
        with (
            patch("app.api.v1.endpoints.demo_requests.DemoRequestService") as MockSvc,
            patch("app.api.v1.endpoints.demo_requests.emit_request_received_email") as mock_email,
        ):
            instance = MockSvc.return_value
            instance.find_active_by_email.return_value = None
            instance.create.return_value = fake_row
            client.post("/api/v1/demo-requests", json=self._VALID_BODY)

        mock_email.assert_called_once_with(fake_row)


# ── GET /api/v1/demo-request-status/{token} ────────────────────────────────────


class TestGetDemoRequestStatusEndpoint:
    def test_valid_token_returns_200(self, client, fake_row):
        with patch("app.api.v1.endpoints.demo_requests.DemoRequestService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_status.return_value = fake_row
            resp = client.get("/api/v1/demo-request-status/valid-token-abc")
        assert resp.status_code == 200
        body = resp.json()
        assert "request_id" in body
        assert "status" in body
        assert "created_at" in body

    def test_unknown_token_returns_404(self, client):
        with patch("app.api.v1.endpoints.demo_requests.DemoRequestService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_status.return_value = None
            resp = client.get("/api/v1/demo-request-status/bad-token")
        assert resp.status_code == 404

    def test_decided_at_none_returned_as_null(self, client, fake_row):
        row = dict(fake_row, decided_at=None)
        with patch("app.api.v1.endpoints.demo_requests.DemoRequestService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_status.return_value = row
            resp = client.get("/api/v1/demo-request-status/some-token")
        assert resp.json()["decided_at"] is None

    def test_decided_at_returned_as_iso_string(self, client, fake_row):
        decided = datetime(2026, 4, 26, 10, 0, 0, tzinfo=UTC)
        row = dict(fake_row, decided_at=decided)
        with patch("app.api.v1.endpoints.demo_requests.DemoRequestService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_status.return_value = row
            resp = client.get("/api/v1/demo-request-status/some-token")
        assert resp.json()["decided_at"] is not None
