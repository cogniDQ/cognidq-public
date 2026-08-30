"""
F034 P03 — Unit tests: GET /workspaces/{ws_id}/issues/{issue_id}/samples

AC-P03-05: no sample → 200 with sample_count=0, rows=[]
AC-P03-06: sample exists → 200 with rows
AC-P03-07: issue not in workspace → 404
AC-P03-08: permission guard enforced (issues:read)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock

import app.api.v1.endpoints.issues as issues_mod
import pytest
from app.services.issues.issue_sample_models import SampleDomain
from fastapi import FastAPI
from fastapi.testclient import TestClient

_WS = uuid.uuid4()
_OTHER_WS = uuid.uuid4()
_ISSUE_ID = uuid.uuid4()
_TENANT = uuid.uuid4()
_NOW = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
_ACTOR = MagicMock(actor_id=uuid.uuid4(), actor_role="analyst", tenant_id=_TENANT)


@pytest.fixture()
def _app():
    """
    Lightweight test client that patches _detail_svc, _sample_repo,
    auth guard, and DB dependency.
    """
    mock_detail_svc = MagicMock()
    mock_sample_repo = MagicMock()
    mock_db = MagicMock()

    orig_detail_svc = issues_mod._detail_svc
    orig_sample_repo = issues_mod._sample_repo

    issues_mod._detail_svc = mock_detail_svc
    issues_mod._sample_repo = mock_sample_repo

    app = FastAPI()
    app.include_router(issues_mod.router)

    from app.models.database import get_db as real_get_db

    app.dependency_overrides[real_get_db] = lambda: mock_db

    # Override auth guards
    for route in app.routes:
        if hasattr(route, "dependant") and hasattr(route.dependant, "dependencies"):
            for dep in route.dependant.dependencies:
                if dep.call is not None and getattr(dep.call, "__name__", "") == "_guard":
                    app.dependency_overrides[dep.call] = lambda: _ACTOR

    client = TestClient(app)
    yield client, mock_detail_svc, mock_sample_repo

    issues_mod._detail_svc = orig_detail_svc
    issues_mod._sample_repo = orig_sample_repo


# ---------------------------------------------------------------------------
# AC-P03-05: no sample → 200 with empty
# ---------------------------------------------------------------------------
class TestNoSample:
    def test_returns_200_with_empty(self, _app):
        client, mock_detail_svc, mock_sample_repo = _app
        mock_detail_svc.get_enriched_detail.return_value = MagicMock()  # issue exists
        mock_sample_repo.find_by_issue.return_value = None

        resp = client.get(f"/workspaces/{_WS}/issues/{_ISSUE_ID}/samples")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sample_count"] == 0
        assert body["rows"] == []
        assert body["masking_applied"] is False
        assert body["captured_at"] is None


# ---------------------------------------------------------------------------
# AC-P03-06: sample exists → 200 with rows
# ---------------------------------------------------------------------------
class TestSampleExists:
    def test_returns_200_with_rows(self, _app):
        client, mock_detail_svc, mock_sample_repo = _app
        mock_detail_svc.get_enriched_detail.return_value = MagicMock()
        sample = SampleDomain(
            id=uuid.uuid4(),
            issue_id=_ISSUE_ID,
            workspace_id=_WS,
            captured_at=_NOW,
            sample_count=2,
            rows=[{"customer_id": 1, "email": "[MASKED]"}, {"customer_id": 2, "email": "[MASKED]"}],
            masking_applied=True,
            masking_threshold="confidential",
        )
        mock_sample_repo.find_by_issue.return_value = sample

        resp = client.get(f"/workspaces/{_WS}/issues/{_ISSUE_ID}/samples")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sample_count"] == 2
        assert len(body["rows"]) == 2
        assert body["masking_applied"] is True
        assert body["masking_threshold"] == "confidential"
        assert body["rows"][0]["email"] == "[MASKED]"


# ---------------------------------------------------------------------------
# AC-P03-07: issue not in workspace → 404
# ---------------------------------------------------------------------------
class TestIssueNotFound:
    def test_returns_404(self, _app):
        client, mock_detail_svc, mock_sample_repo = _app
        mock_detail_svc.get_enriched_detail.return_value = None  # not found

        resp = client.get(f"/workspaces/{_WS}/issues/{_ISSUE_ID}/samples")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC-P03-08: auth guard is present (issues:read)
# ---------------------------------------------------------------------------
class TestAuthGuard:
    def test_guard_present_on_route(self):
        """Verify the samples endpoint has an auth dependency."""
        for route in issues_mod.router.routes:
            if hasattr(route, "path") and route.path.endswith("/{issue_id}/samples"):
                dep_names = [
                    getattr(d.call, "__name__", "")
                    for d in route.dependant.dependencies
                    if d.call is not None
                ]
                assert "_guard" in dep_names, "Auth guard not found on samples route"
                return
        pytest.fail("Samples route not found in router")
