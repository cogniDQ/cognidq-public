"""
P09 Observability — Unit Tests
================================

Verifies that every metric emit-function in
``app.services.workspaces.metrics`` (TDD §12.1) produces the correct
structured log line and that the canonicalisation helpers in
``app.api.v1.endpoints.workspaces`` map raw error codes to valid label
values.

Run inside Docker:
    docker-compose exec backend python -m pytest \\
        tests/unit/services/workspaces/test_f002_p9_observability_unit.py -v

No database connection required — all tests are pure unit tests.
"""

from __future__ import annotations

import logging
from datetime import UTC

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_log(caplog: pytest.LogCaptureFixture, substr: str) -> bool:
    """Return True if *substr* appears in any captured log message."""
    return any(substr in r.getMessage() for r in caplog.records)


# ===========================================================================
# 1. metrics.py — emit_workspace_create_success
# ===========================================================================


class TestEmitWorkspaceCreateSuccess:
    def test_logs_correct_line(self, caplog):
        from app.services.workspaces.metrics import emit_workspace_create_success

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            emit_workspace_create_success("tenant-abc")

        assert _has_log(caplog, "workspace_create_success_count")
        assert _has_log(caplog, "tenant_id=tenant-abc")

    def test_accepts_uuid_string(self, caplog):
        import uuid

        from app.services.workspaces.metrics import emit_workspace_create_success

        tid = str(uuid.uuid4())
        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            emit_workspace_create_success(tid)

        assert _has_log(caplog, f"tenant_id={tid}")

    def test_fire_and_forget_swallows_internal_errors(self, monkeypatch):
        """If the logger itself raises, the function must not propagate."""
        from app.services.workspaces import metrics as m

        def boom(*a, **kw):
            raise RuntimeError("logger exploded")

        monkeypatch.setattr(m.logger, "info", boom)
        # Should not raise
        m.emit_workspace_create_success("t1")


# ===========================================================================
# 2. metrics.py — emit_workspace_create_failure
# ===========================================================================


class TestEmitWorkspaceCreateFailure:
    @pytest.mark.parametrize(
        "reason",
        [
            "duplicate_name",
            "duplicate_slug",
            "invalid_input",
            "tenant_not_active",
            "unauthorized",
            "internal_error",
        ],
    )
    def test_logs_each_valid_reason(self, caplog, reason):
        from app.services.workspaces.metrics import emit_workspace_create_failure

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            emit_workspace_create_failure(reason)

        assert _has_log(caplog, "workspace_create_failure_count")
        assert _has_log(caplog, f"failure_reason={reason}")

    def test_fire_and_forget_swallows_errors(self, monkeypatch):
        from app.services.workspaces import metrics as m

        monkeypatch.setattr(
            m.logger, "info", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError())
        )
        m.emit_workspace_create_failure("invalid_input")


# ===========================================================================
# 3. metrics.py — emit_workspace_update_success
# ===========================================================================


class TestEmitWorkspaceUpdateSuccess:
    def test_logs_sorted_fields(self, caplog):
        from app.services.workspaces.metrics import emit_workspace_update_success

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            emit_workspace_update_success("description,workspace_name")

        assert _has_log(caplog, "workspace_metadata_update_count")
        assert _has_log(caplog, "updated_fields=description,workspace_name")


# ===========================================================================
# 4. metrics.py — emit_workspace_status_change_success
# ===========================================================================


class TestEmitWorkspaceStatusChangeSuccess:
    @pytest.mark.parametrize(
        "from_s,to_s",
        [
            ("active", "archived"),
            ("archived", "active"),
        ],
    )
    def test_logs_transition(self, caplog, from_s, to_s):
        from app.services.workspaces.metrics import emit_workspace_status_change_success

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            emit_workspace_status_change_success(from_s, to_s)

        assert _has_log(caplog, "workspace_status_change_count")
        assert _has_log(caplog, f"from_status={from_s}")
        assert _has_log(caplog, f"to_status={to_s}")


# ===========================================================================
# 5. metrics.py — emit_workspace_status_change_failure
# ===========================================================================


class TestEmitWorkspaceStatusChangeFailure:
    @pytest.mark.parametrize(
        "reason",
        [
            "forbidden_transition",
            "missing_reason",
            "tenant_not_active",
            "unauthorized",
            "no_op",
            "last_active_workspace",
            "internal_error",
        ],
    )
    def test_logs_each_valid_reason(self, caplog, reason):
        from app.services.workspaces.metrics import emit_workspace_status_change_failure

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            emit_workspace_status_change_failure(reason)

        assert _has_log(caplog, "workspace_status_change_failure_count")
        assert _has_log(caplog, f"failure_reason={reason}")


# ===========================================================================
# 6. metrics.py — emit_workspace_list_request_count / detail variants
# ===========================================================================


class TestEmitCounters:
    def test_list_request_count(self, caplog):
        from app.services.workspaces.metrics import emit_workspace_list_request_count

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            emit_workspace_list_request_count()

        assert _has_log(caplog, "workspace_list_request_count")

    def test_detail_request_count(self, caplog):
        from app.services.workspaces.metrics import emit_workspace_detail_request_count

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            emit_workspace_detail_request_count()

        assert _has_log(caplog, "workspace_detail_request_count")

    @pytest.mark.parametrize("count_type", ["dataset_count", "member_count"])
    def test_detail_count_query_failure(self, caplog, count_type):
        from app.services.workspaces.metrics import emit_workspace_detail_count_query_failure

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            emit_workspace_detail_count_query_failure(count_type)

        assert _has_log(caplog, "workspace_detail_count_query_failure_count")
        assert _has_log(caplog, f"count_type={count_type}")


# ===========================================================================
# 7. workspaces.py — _canon_create_failure canonicalisation
# ===========================================================================


class TestCanonCreateFailure:
    """_canon_create_failure must always return a value in _CREATE_FAILURE_REASONS."""

    def setup_method(self):
        from app.api.v1.endpoints.workspaces import (
            _CREATE_FAILURE_REASONS,
            _canon_create_failure,
        )

        self._fn = _canon_create_failure
        self._valid = _CREATE_FAILURE_REASONS

    def _assert_valid(self, code: str):
        result = self._fn(code)
        assert result in self._valid, f"{code!r} → {result!r} not in {self._valid}"

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("duplicate_name", "duplicate_name"),
            ("duplicate_slug", "duplicate_slug"),
            ("invalid_input", "invalid_input"),
            ("tenant_not_active", "tenant_not_active"),
            ("unauthorized", "unauthorized"),
            ("internal_error", "internal_error"),
            # validation-class codes → invalid_input
            ("validation_error", "invalid_input"),
            ("unknown_field", "invalid_input"),
            ("invalid_field_type", "invalid_input"),
            ("missing_required_field", "invalid_input"),
            # unknown codes → internal_error
            ("some_random_code", "internal_error"),
            ("role_grant_failed", "internal_error"),
            ("", "internal_error"),
        ],
    )
    def test_mapping(self, code, expected):
        result = self._fn(code)
        assert result == expected, f"{code!r} → {result!r}, expected {expected!r}"
        self._assert_valid(code)


# ===========================================================================
# 8. workspaces.py — _canon_status_failure canonicalisation
# ===========================================================================


class TestCanonStatusFailure:
    """_canon_status_failure must always return a value in _STATUS_FAILURE_REASONS."""

    def setup_method(self):
        from app.api.v1.endpoints.workspaces import (
            _STATUS_FAILURE_REASONS,
            _canon_status_failure,
        )

        self._fn = _canon_status_failure
        self._valid = _STATUS_FAILURE_REASONS

    def _assert_valid(self, code: str):
        result = self._fn(code)
        assert result in self._valid, f"{code!r} → {result!r} not in {self._valid}"

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("forbidden_transition", "forbidden_transition"),
            ("missing_reason", "missing_reason"),
            ("tenant_not_active", "tenant_not_active"),
            ("unauthorized", "unauthorized"),
            ("no_op", "no_op"),
            ("last_active_workspace", "last_active_workspace"),
            ("internal_error", "internal_error"),
            # unmapped codes fall through to internal_error
            ("not_found", "internal_error"),
            ("tenant_not_found", "internal_error"),
            ("some_unknown_code", "internal_error"),
        ],
    )
    def test_mapping(self, code, expected):
        result = self._fn(code)
        assert result == expected, f"{code!r} → {result!r}, expected {expected!r}"
        self._assert_valid(code)


# ===========================================================================
# 9. verify_workspace_create_admin — metric on 403
# ===========================================================================


class TestVerifyWorkspaceCreateAdmin:
    """
    verify_workspace_create_admin must emit workspace_create_failure_count
    failure_reason=unauthorized before re-raising InsufficientPermissionsError
    (TG-13 / TDD §12.1).
    """

    def _make_request(self, token: str):
        """Construct a minimal mock Request with an Authorization header."""
        from unittest.mock import MagicMock

        req = MagicMock()
        req.headers = {"Authorization": f"Bearer {token}"}
        req.state = MagicMock()
        return req

    def _make_token(self, role: str) -> str:
        import uuid
        from datetime import datetime, timedelta, timezone

        from app.core.config import settings
        from jose import jwt

        payload = {
            "actor_id": str(uuid.uuid4()),
            "actor_role": role,
            "tenant_id": str(uuid.uuid4()),
            "exp": datetime.now(tz=UTC) + timedelta(hours=1),
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    @pytest.mark.asyncio
    async def test_403_emits_unauthorized_metric(self, caplog):
        """Non-WA role → 403 → metric emitted before re-raise."""
        from app.api.v1.dependencies.workspace_auth import verify_workspace_create_admin
        from fastapi import HTTPException

        # Use a role that is not platform_admin/tenant_admin/member — falls through to 403
        token = self._make_token("editor")
        req = self._make_request(token)

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            with pytest.raises(HTTPException) as exc_info:
                await verify_workspace_create_admin(req)

        assert exc_info.value.status_code == 403
        assert _has_log(caplog, "workspace_create_failure_count")
        assert _has_log(caplog, "failure_reason=unauthorized")

    @pytest.mark.asyncio
    async def test_401_emits_unauthorized_metric(self, caplog):
        """Missing / bad JWT → 401 → metric emitted before re-raise."""
        from app.api.v1.dependencies.workspace_auth import verify_workspace_create_admin
        from fastapi import HTTPException

        req = self._make_request("not.a.valid.jwt")

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            with pytest.raises(HTTPException) as exc_info:
                await verify_workspace_create_admin(req)

        assert exc_info.value.status_code == 401
        assert _has_log(caplog, "failure_reason=unauthorized")
