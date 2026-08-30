"""
F134 P05 — Tests for Admin Review Queue API

Tests admin list/detail/approve/reject endpoints using a minimal FastAPI app.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    TenantAPIError,
    get_actor_context,
    require_write_access,
    tenant_api_error_handler,
)
from app.api.v1.endpoints.admin_demo_requests import router as admin_router
from app.models.database import get_db
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Helpers ───────────────────────────────────────────────────────────────────

ADMIN_ACTOR_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER_ACTOR_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _admin_actor():
    return ActorContext(actor_id=ADMIN_ACTOR_ID, actor_role="platform_admin")


def _viewer_actor():
    return ActorContext(actor_id=OTHER_ACTOR_ID, actor_role="platform_viewer")


def _customer_actor():
    return ActorContext(actor_id=OTHER_ACTOR_ID, actor_role="customer_actor")


def _fake_request_row(status: str = "submitted"):
    return {
        "id": str(uuid.uuid4()),
        "status": status,
        "public_status_token": "tok_" + "x" * 60,
        "work_email": "prospect@company.io",
        "first_name": "Alice",
        "last_name": "Smith",
        "company_name": "Acme Corp",
        "is_personal_email": False,
        "created_at": datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC),
    }


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    return MagicMock()


def _make_client(mock_db, actor_factory=_admin_actor):
    """Build minimal FastAPI test client with auth and DB mocked."""
    _app = FastAPI()
    _app.include_router(admin_router, prefix="/api/v1")
    _app.dependency_overrides[get_db] = lambda: mock_db
    _app.add_exception_handler(TenantAPIError, tenant_api_error_handler)

    # Override the inner guard returned by require_write_access()
    # We override get_actor_context which is the transitive dependency
    _app.dependency_overrides[get_actor_context] = lambda: actor_factory()

    return TestClient(_app, raise_server_exceptions=False)


# ── Service-layer tests ───────────────────────────────────────────────────────


class TestAdminDemoRequestService:
    def test_list_requests_delegates_to_repo(self, mock_db):
        from app.services.sandbox.admin_demo_request_service import AdminDemoRequestService

        svc = AdminDemoRequestService(mock_db)
        svc._request_repo.list_with_filters = MagicMock(return_value=([_fake_request_row()], 1))
        rows, total = svc.list_requests(status="submitted")
        assert total == 1
        assert len(rows) == 1
        svc._request_repo.list_with_filters.assert_called_once()

    def test_get_request_returns_row(self, mock_db):
        from app.services.sandbox.admin_demo_request_service import AdminDemoRequestService

        row = _fake_request_row()
        req_id = uuid.uuid4()
        svc = AdminDemoRequestService(mock_db)
        svc._request_repo.find_by_id = MagicMock(return_value=row)
        result = svc.get_request(req_id)
        assert result == row

    def test_get_request_returns_none_when_not_found(self, mock_db):
        from app.services.sandbox.admin_demo_request_service import AdminDemoRequestService

        req_id = uuid.uuid4()
        svc = AdminDemoRequestService(mock_db)
        svc._request_repo.find_by_id = MagicMock(return_value=None)
        result = svc.get_request(req_id)
        assert result is None

    def test_approve_request_updates_status_and_creates_job(self, mock_db):
        from app.services.sandbox.admin_demo_request_service import AdminDemoRequestService

        req_id = uuid.uuid4()
        updated_row = {**_fake_request_row("approved"), "decided_by": str(ADMIN_ACTOR_ID)}
        svc = AdminDemoRequestService(mock_db)
        svc._request_repo.update_status = MagicMock(return_value=updated_row)
        svc._job_repo.create = MagicMock(
            return_value={"id": str(uuid.uuid4()), "status": "pending"}
        )

        result = svc.approve_request(
            request_id=req_id,
            decided_by=ADMIN_ACTOR_ID,
            template_id="general_dq",
            duration_days=7,
            access_profile_code="mvp_default",
        )
        assert result["status"] == "approved"
        svc._request_repo.update_status.assert_called_once()
        svc._job_repo.create.assert_called_once_with(demo_request_id=req_id)

    def test_reject_request_updates_status(self, mock_db):
        from app.services.sandbox.admin_demo_request_service import AdminDemoRequestService

        req_id = uuid.uuid4()
        updated_row = {**_fake_request_row("rejected"), "rejection_reason": "spam"}
        svc = AdminDemoRequestService(mock_db)
        svc._request_repo.update_status = MagicMock(return_value=updated_row)

        result = svc.reject_request(
            request_id=req_id,
            decided_by=ADMIN_ACTOR_ID,
            reason="spam",
        )
        assert result["status"] == "rejected"
        svc._request_repo.update_status.assert_called_once()

    def test_reject_request_calls_email_stub(self, mock_db):
        from app.services.sandbox.admin_demo_request_service import (
            AdminDemoRequestService,
            emit_sandbox_rejected_email,
        )

        req_id = uuid.uuid4()
        updated_row = _fake_request_row("rejected")
        svc = AdminDemoRequestService(mock_db)
        svc._request_repo.update_status = MagicMock(return_value=updated_row)

        with patch(
            "app.services.sandbox.admin_demo_request_service.emit_sandbox_rejected_email"
        ) as mock_email:
            svc.reject_request(
                request_id=req_id,
                decided_by=ADMIN_ACTOR_ID,
                reason="Not qualified.",
            )
            mock_email.assert_called_once()


# ── Endpoint tests — List ─────────────────────────────────────────────────────


class TestListDemoRequestsEndpoint:
    def test_returns_200_for_platform_admin(self, mock_db):
        with patch(
            "app.services.sandbox.admin_demo_request_service.AdminDemoRequestService.list_requests"
        ) as mock_list:
            mock_list.return_value = ([_fake_request_row()], 1)
            client = _make_client(mock_db)
            resp = client.get("/api/v1/admin/demo-requests")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1

    def test_returns_403_for_platform_viewer(self, mock_db):
        client = _make_client(mock_db, actor_factory=_viewer_actor)
        resp = client.get("/api/v1/admin/demo-requests")
        assert resp.status_code == 403

    def test_returns_403_for_customer_actor(self, mock_db):
        client = _make_client(mock_db, actor_factory=_customer_actor)
        resp = client.get("/api/v1/admin/demo-requests")
        assert resp.status_code == 403

    def test_passes_status_filter(self, mock_db):
        with patch(
            "app.services.sandbox.admin_demo_request_service.AdminDemoRequestService.list_requests"
        ) as mock_list:
            mock_list.return_value = ([], 0)
            client = _make_client(mock_db)
            resp = client.get("/api/v1/admin/demo-requests?status=approved")
        assert resp.status_code == 200
        call_kwargs = mock_list.call_args.kwargs
        assert call_kwargs["status"] == "approved"

    def test_empty_list(self, mock_db):
        with patch(
            "app.services.sandbox.admin_demo_request_service.AdminDemoRequestService.list_requests"
        ) as mock_list:
            mock_list.return_value = ([], 0)
            client = _make_client(mock_db)
            resp = client.get("/api/v1/admin/demo-requests")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ── Endpoint tests — Detail ───────────────────────────────────────────────────


class TestGetDemoRequestEndpoint:
    def test_returns_200_when_found(self, mock_db):
        row = _fake_request_row()
        req_id = uuid.UUID(row["id"])
        with patch(
            "app.services.sandbox.admin_demo_request_service.AdminDemoRequestService.get_request"
        ) as mock_get:
            mock_get.return_value = row
            client = _make_client(mock_db)
            resp = client.get(f"/api/v1/admin/demo-requests/{req_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "submitted"

    def test_returns_404_when_not_found(self, mock_db):
        with patch(
            "app.services.sandbox.admin_demo_request_service.AdminDemoRequestService.get_request"
        ) as mock_get:
            mock_get.return_value = None
            client = _make_client(mock_db)
            resp = client.get(f"/api/v1/admin/demo-requests/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_403_for_wrong_role(self, mock_db):
        client = _make_client(mock_db, actor_factory=_viewer_actor)
        resp = client.get(f"/api/v1/admin/demo-requests/{uuid.uuid4()}")
        assert resp.status_code == 403


# ── Endpoint tests — Approve ──────────────────────────────────────────────────


class TestApproveDemoRequestEndpoint:
    def _valid_body(self):
        return {
            "template_id": "general_dq",
            "duration_days": 7,
            "access_profile_code": "mvp_default",
        }

    def test_returns_200_on_approval(self, mock_db):
        row = _fake_request_row()
        req_id = uuid.UUID(row["id"])
        approved_row = {**row, "status": "approved"}

        with (
            patch("app.api.v1.endpoints.admin_demo_requests.DemoTemplateRepository") as MockTR,
            patch("app.api.v1.endpoints.admin_demo_requests.AccessProfileRepository") as MockAR,
            patch(
                "app.services.sandbox.admin_demo_request_service.AdminDemoRequestService.get_request"
            ) as mock_get,
            patch(
                "app.services.sandbox.admin_demo_request_service.AdminDemoRequestService.approve_request"
            ) as mock_approve,
        ):
            MockTR.return_value.find_by_id.return_value = {"id": "general_dq"}
            MockAR.return_value.find_by_code.return_value = {"code": "mvp_default"}
            mock_get.return_value = row
            mock_approve.return_value = approved_row

            client = _make_client(mock_db)
            resp = client.post(
                f"/api/v1/admin/demo-requests/{req_id}/approve",
                json=self._valid_body(),
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_returns_404_when_request_not_found(self, mock_db):
        with (
            patch("app.api.v1.endpoints.admin_demo_requests.DemoTemplateRepository") as MockTR,
            patch("app.api.v1.endpoints.admin_demo_requests.AccessProfileRepository") as MockAR,
            patch(
                "app.services.sandbox.admin_demo_request_service.AdminDemoRequestService.get_request"
            ) as mock_get,
        ):
            MockTR.return_value.find_by_id.return_value = {"id": "general_dq"}
            MockAR.return_value.find_by_code.return_value = {"code": "mvp_default"}
            mock_get.return_value = None

            client = _make_client(mock_db)
            resp = client.post(
                f"/api/v1/admin/demo-requests/{uuid.uuid4()}/approve",
                json=self._valid_body(),
            )
        assert resp.status_code == 404

    def test_403_for_wrong_role(self, mock_db):
        client = _make_client(mock_db, actor_factory=_viewer_actor)
        resp = client.post(
            f"/api/v1/admin/demo-requests/{uuid.uuid4()}/approve",
            json=self._valid_body(),
        )
        assert resp.status_code == 403

    def test_422_for_invalid_duration(self, mock_db):
        with (
            patch("app.api.v1.endpoints.admin_demo_requests.DemoTemplateRepository") as MockTR,
            patch("app.api.v1.endpoints.admin_demo_requests.AccessProfileRepository") as MockAR,
        ):
            MockTR.return_value.find_by_id.return_value = {"id": "general_dq"}
            MockAR.return_value.find_by_code.return_value = {"code": "mvp_default"}
            client = _make_client(mock_db)
            resp = client.post(
                f"/api/v1/admin/demo-requests/{uuid.uuid4()}/approve",
                json={
                    "template_id": "general_dq",
                    "duration_days": 99,  # invalid
                    "access_profile_code": "mvp_default",
                },
            )
        # Pydantic model_validator fires before endpoint logic
        assert resp.status_code == 422


# ── Endpoint tests — Reject ───────────────────────────────────────────────────


class TestRejectDemoRequestEndpoint:
    def _valid_body(self):
        return {"reason": "Not a good fit for current phase."}

    def test_returns_200_on_rejection(self, mock_db):
        row = _fake_request_row()
        req_id = uuid.UUID(row["id"])
        rejected_row = {**row, "status": "rejected"}

        with (
            patch(
                "app.services.sandbox.admin_demo_request_service.AdminDemoRequestService.get_request"
            ) as mock_get,
            patch(
                "app.services.sandbox.admin_demo_request_service.AdminDemoRequestService.reject_request"
            ) as mock_reject,
        ):
            mock_get.return_value = row
            mock_reject.return_value = rejected_row

            client = _make_client(mock_db)
            resp = client.post(
                f"/api/v1/admin/demo-requests/{req_id}/reject",
                json=self._valid_body(),
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_returns_404_when_request_not_found(self, mock_db):
        with patch(
            "app.services.sandbox.admin_demo_request_service.AdminDemoRequestService.get_request"
        ) as mock_get:
            mock_get.return_value = None
            client = _make_client(mock_db)
            resp = client.post(
                f"/api/v1/admin/demo-requests/{uuid.uuid4()}/reject",
                json=self._valid_body(),
            )
        assert resp.status_code == 404

    def test_403_for_wrong_role(self, mock_db):
        client = _make_client(mock_db, actor_factory=_viewer_actor)
        resp = client.post(
            f"/api/v1/admin/demo-requests/{uuid.uuid4()}/reject",
            json=self._valid_body(),
        )
        assert resp.status_code == 403

    def test_422_for_short_reason(self, mock_db):
        client = _make_client(mock_db)
        resp = client.post(
            f"/api/v1/admin/demo-requests/{uuid.uuid4()}/reject",
            json={"reason": "No"},  # too short, < 3 chars
        )
        assert resp.status_code == 422
