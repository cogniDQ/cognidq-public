"""
F134 P10 — Tests for Usage Tracking + Admin Usage Endpoint

Tests:
  - compute_engagement_score pure function (high/medium/low/unknown boundary)
  - UsageTrackingService.record_event (happy, silent failure on error)
  - UsageTrackingService.aggregate (score computation + DB update)
  - UsageTrackingService.get_usage_summary (shape verification)
  - GET /admin/sandboxes/{id}/usage (200, 404, 403)
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
from app.api.v1.endpoints.admin_sandboxes import router as admin_router
from app.models.database import get_db
from app.services.sandbox.usage_tracking_service import (
    UsageTrackingService,
    compute_engagement_score,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Constants ─────────────────────────────────────────────────────────────────

ADMIN_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SANDBOX_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
VIEWER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
NOW = datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC)


def _admin_actor():
    return ActorContext(actor_id=ADMIN_ID, actor_role="platform_admin")


def _viewer_actor():
    return ActorContext(actor_id=VIEWER_ID, actor_role="platform_viewer")


def _make_client(mock_db, actor_factory=_admin_actor):
    _app = FastAPI()
    _app.include_router(admin_router, prefix="/api/v1")
    _app.dependency_overrides[get_db] = lambda: mock_db
    _app.add_exception_handler(TenantAPIError, tenant_api_error_handler)
    _app.dependency_overrides[get_actor_context] = lambda: actor_factory()
    return TestClient(_app, raise_server_exceptions=False)


# ── compute_engagement_score ──────────────────────────────────────────────────


class TestComputeEngagementScore:
    def test_unknown_when_no_events(self):
        score = compute_engagement_score(
            sessions_in_48h=0,
            unique_event_types_in_48h=0,
            total_events=0,
        )
        assert score == "unknown"

    def test_high_when_5_sessions_and_10_types(self):
        score = compute_engagement_score(
            sessions_in_48h=5,
            unique_event_types_in_48h=10,
            total_events=100,
        )
        assert score == "high"

    def test_high_requires_both_conditions(self):
        # 5 sessions but only 9 unique types → medium, not high
        score = compute_engagement_score(
            sessions_in_48h=5,
            unique_event_types_in_48h=9,
            total_events=50,
        )
        assert score == "medium"

    def test_medium_when_2_sessions(self):
        score = compute_engagement_score(
            sessions_in_48h=2,
            unique_event_types_in_48h=3,
            total_events=20,
        )
        assert score == "medium"

    def test_low_when_1_session(self):
        score = compute_engagement_score(
            sessions_in_48h=1,
            unique_event_types_in_48h=5,
            total_events=10,
        )
        assert score == "low"

    def test_low_when_no_sessions_but_events(self):
        score = compute_engagement_score(
            sessions_in_48h=0,
            unique_event_types_in_48h=0,
            total_events=5,
        )
        assert score == "low"

    def test_high_boundary_exactly_5_sessions_10_types(self):
        score = compute_engagement_score(
            sessions_in_48h=5,
            unique_event_types_in_48h=10,
            total_events=50,
        )
        assert score == "high"

    def test_medium_boundary_exactly_2_sessions(self):
        score = compute_engagement_score(
            sessions_in_48h=2,
            unique_event_types_in_48h=0,
            total_events=2,
        )
        assert score == "medium"


# ── UsageTrackingService.record_event ────────────────────────────────────────


class TestRecordEvent:
    def test_happy_path_inserts_event(self):
        db = MagicMock()
        event_repo = MagicMock()
        svc = UsageTrackingService(db, event_repo=event_repo)

        svc.record_event(
            sandbox_id=SANDBOX_ID,
            user_id=ADMIN_ID,
            event_type="page_view",
            payload={"path": "/workspace/rules"},
        )
        event_repo.insert.assert_called_once()
        call_kwargs = event_repo.insert.call_args.kwargs
        assert call_kwargs["event_type"] == "page_view"
        assert call_kwargs["sandbox_id"] == SANDBOX_ID

    def test_never_raises_on_exception(self):
        """record_event must be fire-and-forget — no propagation."""
        db = MagicMock()
        event_repo = MagicMock()
        event_repo.insert.side_effect = RuntimeError("DB is down")
        svc = UsageTrackingService(db, event_repo=event_repo)

        # Should NOT raise
        svc.record_event(
            sandbox_id=SANDBOX_ID,
            user_id=ADMIN_ID,
            event_type="page_view",
        )

    def test_handles_optional_user_id(self):
        db = MagicMock()
        event_repo = MagicMock()
        svc = UsageTrackingService(db, event_repo=event_repo)

        svc.record_event(
            sandbox_id=SANDBOX_ID,
            user_id=None,
            event_type="system_notification",
        )
        event_repo.insert.assert_called_once()


# ── UsageTrackingService.aggregate ───────────────────────────────────────────


class TestAggregate:
    def _make_svc(self, sessions=0, unique_types=0, total=0):
        db = MagicMock()

        def _execute_side_effect(sql, params):
            sql_str = str(sql)
            mock_result = MagicMock()
            if "login" in sql_str:
                mock_result.fetchone.return_value = MagicMock(_mapping={"n": sessions})
            elif "DISTINCT" in sql_str:
                mock_result.fetchone.return_value = MagicMock(_mapping={"n": unique_types})
            elif "COUNT" in sql_str:
                mock_result.fetchone.return_value = MagicMock(_mapping={"n": total})
            else:
                mock_result.fetchone.return_value = None
            return mock_result

        db.execute.side_effect = _execute_side_effect
        svc = UsageTrackingService(db)
        return svc, db

    def test_returns_high_score(self):
        svc, _ = self._make_svc(sessions=5, unique_types=10, total=100)
        score = svc.aggregate(sandbox_id=SANDBOX_ID)
        assert score == "high"

    def test_returns_unknown_with_no_events(self):
        svc, _ = self._make_svc(sessions=0, unique_types=0, total=0)
        score = svc.aggregate(sandbox_id=SANDBOX_ID)
        assert score == "unknown"

    def test_calls_db_update(self):
        svc, db = self._make_svc(sessions=2, unique_types=3, total=10)
        svc.aggregate(sandbox_id=SANDBOX_ID)
        # Should have called execute 4 times (3 SELECT + 1 UPDATE)
        assert db.execute.call_count == 4


# ── UsageTrackingService.get_usage_summary ───────────────────────────────────


class TestGetUsageSummary:
    def test_returns_expected_shape(self):
        db = MagicMock()
        env_repo = MagicMock()
        event_repo = MagicMock()

        # Mock total events query
        total_row = MagicMock(_mapping={"n": 42})
        # Mock events by type
        type_row = MagicMock(
            _mapping={
                "event_type": "page_view",
                "count": 42,
                "last_seen_at": NOW,
            }
        )
        # Mock timeline
        timeline_row = MagicMock(_mapping={"day": "2026-04-25", "count": 10})

        db.execute.side_effect = [
            MagicMock(fetchone=lambda: total_row),
            MagicMock(fetchall=lambda: [type_row]),
            MagicMock(fetchall=lambda: [timeline_row]),
        ]
        env_repo.find_by_id.return_value = {"engagement_score": "medium"}

        svc = UsageTrackingService(db, event_repo=event_repo, env_repo=env_repo)
        result = svc.get_usage_summary(sandbox_id=SANDBOX_ID)

        assert "summary" in result
        assert "events_by_type" in result
        assert "timeline" in result
        assert result["summary"]["total_events"] == 42
        assert result["summary"]["engagement_score"] == "medium"


# ── GET /admin/sandboxes/{id}/usage endpoint ──────────────────────────────────


class TestAdminSandboxUsageEndpoint:
    def test_returns_200_with_usage_shape(self):
        mock_db = MagicMock()
        with (
            patch(
                "app.services.sandbox.sandbox_environment_repository.SandboxEnvironmentRepository.find_by_id"
            ) as mock_find,
            patch(
                "app.services.sandbox.usage_tracking_service.UsageTrackingService.get_usage_summary"
            ) as mock_usage,
        ):
            mock_find.return_value = {"id": str(SANDBOX_ID), "status": "active"}
            mock_usage.return_value = {
                "summary": {"total_events": 5, "engagement_score": "low"},
                "events_by_type": [],
                "timeline": [],
            }
            client = _make_client(mock_db)
            resp = client.get(f"/api/v1/admin/sandboxes/{SANDBOX_ID}/usage")

        assert resp.status_code == 200
        body = resp.json()
        assert "summary" in body
        assert "events_by_type" in body
        assert "timeline" in body

    def test_returns_404_for_unknown_sandbox(self):
        mock_db = MagicMock()
        with patch(
            "app.services.sandbox.sandbox_environment_repository.SandboxEnvironmentRepository.find_by_id"
        ) as mock_find:
            mock_find.return_value = None
            client = _make_client(mock_db)
            resp = client.get(f"/api/v1/admin/sandboxes/{uuid.uuid4()}/usage")
        assert resp.status_code == 404

    def test_returns_403_for_viewer(self):
        mock_db = MagicMock()
        client = _make_client(mock_db, actor_factory=_viewer_actor)
        resp = client.get(f"/api/v1/admin/sandboxes/{SANDBOX_ID}/usage")
        assert resp.status_code == 403
