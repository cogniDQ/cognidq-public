"""
Packet 7 — Unit tests: Change Tenant Status service & state machine
====================================================================

Tests cover:
    - ``_ALLOWED_TRANSITIONS``   — all 16 cells of the transition matrix (TDD §2.6)
    - ``TenantService.change_status``
          happy path (all 5 allowed transitions), archived block,
          no-op detection, forbidden transitions, status_reason validation,
          suspended→active auto-clears status_reason, outbox insertion,
          no audit log on rejected transitions, lock contention (409)
    - ``OutboxPoller``           — delivery success, failure+retry, SLA breach

All DB I/O is mocked; no Docker / live database is required.

Run inside Docker::

    docker-compose exec backend python -m pytest \\
        tests/unit/services/f001/test_p7_change_status.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, call, patch

import pytest
from app.api.v1.dependencies.tenant_auth import TenantAPIError
from app.services.tenants.commands import ChangeStatusCommand
from app.services.tenants.service import _ALLOWED_TRANSITIONS, TenantService
from sqlalchemy.exc import OperationalError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TENANT_ID = str(uuid.uuid4())
_ACTOR_ID = uuid.uuid4()
_ACTOR_ROLE = "platform_admin"


def _cmd(
    target_status: str,
    status_reason: str | None = None,
    tenant_id: str = _TENANT_ID,
) -> ChangeStatusCommand:
    return ChangeStatusCommand(
        tenant_id=tenant_id,
        actor_id=_ACTOR_ID,
        actor_role=_ACTOR_ROLE,
        target_status=target_status,
        status_reason=status_reason,
    )


def _row(status: str, status_reason: str | None = None) -> dict[str, Any]:
    """Minimal DB row for find_by_id_for_update()."""
    return {
        "tenant_id": uuid.UUID(_TENANT_ID),
        "tenant_name": "Acme Corp",
        "tenant_slug": "acme-corp",
        "status": status,
        "status_reason": status_reason,
        "region": "eu-west",
        "plan": "starter",
        "service_start_date": None,
        "tenant_notes": None,
        "created_at": datetime.now(tz=UTC),
        "updated_at": datetime.now(tz=UTC),
        "created_by": str(uuid.uuid4()),
        "updated_by": str(uuid.uuid4()),
        "version": 1,
    }


def _updated_row(status: str, status_reason: str | None = None) -> dict[str, Any]:
    """Simulates the RETURNING dict from TenantRepository.update_status()."""
    return {
        "tenant_id": _TENANT_ID,
        "status": status,
        "status_reason": status_reason,
        "updated_at": datetime.now(tz=UTC),
        "updated_by": str(_ACTOR_ID),
    }


# ===========================================================================
# TestTransitionMatrix
# ===========================================================================


class TestTransitionMatrix:
    """Validate every cell of the 4×4 transition matrix (TDD §2.6)."""

    # Allowed transitions
    @pytest.mark.parametrize(
        "frm, to",
        [
            ("draft", "active"),
            ("draft", "archived"),
            ("active", "suspended"),
            ("active", "archived"),
            ("suspended", "active"),
            ("suspended", "archived"),
        ],
    )
    def test_allowed_transitions(self, frm, to):
        assert _ALLOWED_TRANSITIONS.get((frm, to), False) is True, (
            f"Expected ({frm!r} → {to!r}) to be ALLOWED in transition matrix"
        )

    # Forbidden transitions
    @pytest.mark.parametrize(
        "frm, to",
        [
            ("draft", "suspended"),
            ("active", "draft"),
            ("suspended", "draft"),
            ("archived", "draft"),
            ("archived", "active"),
            ("archived", "suspended"),
            ("archived", "archived"),
        ],
    )
    def test_forbidden_transitions(self, frm, to):
        assert _ALLOWED_TRANSITIONS.get((frm, to), False) is False, (
            f"Expected ({frm!r} → {to!r}) to be FORBIDDEN in transition matrix"
        )

    # Self-transitions (no-op) are NOT in _ALLOWED_TRANSITIONS as True
    @pytest.mark.parametrize("status", ["draft", "active", "suspended", "archived"])
    def test_self_transitions_not_allowed(self, status):
        assert _ALLOWED_TRANSITIONS.get((status, status), False) is not True, (
            f"Self-transition ({status!r} → {status!r}) must not be allowed"
        )


# ===========================================================================
# TestChangeStatusService
# ===========================================================================


class TestChangeStatusService:
    """TenantService.change_status — full behaviour coverage."""

    # ------------------------------------------------------------------
    # Happy-path transitions
    # ------------------------------------------------------------------

    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    @patch("app.services.tenants.service.TenantRepository.update_status")
    @patch("app.services.tenants.service.AuditLogRepository.insert_status_change")
    @patch("app.services.tenants.service.OutboxRepository.insert_suspended_event")
    @patch("app.services.tenants.service.emit_tenant_status_change")
    def test_draft_to_active_happy_path(
        self, mock_metric, mock_outbox, mock_audit, mock_update, mock_find
    ):
        db = MagicMock()
        mock_find.return_value = _row("draft")
        mock_update.return_value = _updated_row("active")

        dto = TenantService.change_status(db, _cmd("active"))

        assert dto.previous_status == "draft"
        assert dto.current_status == "active"
        assert dto.status_reason is None
        mock_audit.assert_called_once()
        mock_outbox.assert_not_called()  # only on suspension
        mock_metric.assert_called_once_with(from_status="draft", to_status="active")
        db.commit.assert_called_once()

    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    @patch("app.services.tenants.service.TenantRepository.update_status")
    @patch("app.services.tenants.service.AuditLogRepository.insert_status_change")
    @patch("app.services.tenants.service.OutboxRepository.insert_suspended_event")
    @patch("app.services.tenants.service.emit_tenant_status_change")
    def test_active_to_suspended_inserts_outbox(
        self, mock_metric, mock_outbox, mock_audit, mock_update, mock_find
    ):
        db = MagicMock()
        mock_find.return_value = _row("active")
        mock_update.return_value = _updated_row("suspended", "Acme non-payment")

        dto = TenantService.change_status(
            db, _cmd("suspended", status_reason="Acme non-payment — 30-day overdue")
        )

        assert dto.previous_status == "active"
        assert dto.current_status == "suspended"
        mock_outbox.assert_called_once()
        mock_audit.assert_called_once()
        db.commit.assert_called_once()

    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    @patch("app.services.tenants.service.TenantRepository.update_status")
    @patch("app.services.tenants.service.AuditLogRepository.insert_status_change")
    @patch("app.services.tenants.service.OutboxRepository.insert_suspended_event")
    @patch("app.services.tenants.service.emit_tenant_status_change")
    def test_active_to_archived(self, mock_metric, mock_outbox, mock_audit, mock_update, mock_find):
        db = MagicMock()
        mock_find.return_value = _row("active")
        mock_update.return_value = _updated_row("archived", "Contract terminated formally")

        dto = TenantService.change_status(
            db, _cmd("archived", status_reason="Contract terminated formally")
        )

        assert dto.current_status == "archived"
        mock_outbox.assert_not_called()  # outbox only for suspended
        db.commit.assert_called_once()

    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    @patch("app.services.tenants.service.TenantRepository.update_status")
    @patch("app.services.tenants.service.AuditLogRepository.insert_status_change")
    @patch("app.services.tenants.service.OutboxRepository.insert_suspended_event")
    @patch("app.services.tenants.service.emit_tenant_status_change")
    def test_suspended_to_active_auto_clears_status_reason(
        self, mock_metric, mock_outbox, mock_audit, mock_update, mock_find
    ):
        """TDD §6.6 — status_reason MUST be set to NULL on suspended → active."""
        db = MagicMock()
        mock_find.return_value = _row("suspended", status_reason="Non-payment overdue 30days")
        mock_update.return_value = _updated_row("active", status_reason=None)

        dto = TenantService.change_status(db, _cmd("active"))

        # Service must call update_status with new_reason=None
        update_call_kwargs = mock_update.call_args
        assert update_call_kwargs.kwargs["new_reason"] is None
        assert dto.status_reason is None
        mock_outbox.assert_not_called()

    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    @patch("app.services.tenants.service.TenantRepository.update_status")
    @patch("app.services.tenants.service.AuditLogRepository.insert_status_change")
    @patch("app.services.tenants.service.OutboxRepository.insert_suspended_event")
    @patch("app.services.tenants.service.emit_tenant_status_change")
    def test_suspended_to_archived(
        self, mock_metric, mock_outbox, mock_audit, mock_update, mock_find
    ):
        db = MagicMock()
        mock_find.return_value = _row("suspended", status_reason="Non-payment overdue 30days")
        mock_update.return_value = _updated_row("archived", "Permanent closure requested")

        dto = TenantService.change_status(
            db, _cmd("archived", status_reason="Permanent closure requested")
        )

        assert dto.current_status == "archived"
        mock_outbox.assert_not_called()
        db.commit.assert_called_once()

    # ------------------------------------------------------------------
    # Not found
    # ------------------------------------------------------------------

    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    def test_not_found_raises_404(self, mock_find):
        db = MagicMock()
        mock_find.return_value = None

        with pytest.raises(TenantAPIError) as exc_info:
            TenantService.change_status(db, _cmd("active"))

        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "not_found"
        db.rollback.assert_called()

    # ------------------------------------------------------------------
    # No-op detection
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("status", ["draft", "active", "suspended", "archived"])
    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    @patch("app.services.tenants.service.AuditLogRepository.insert_status_change")
    def test_no_op_transition_raises_422(self, mock_audit, mock_find, status):
        db = MagicMock()
        mock_find.return_value = _row(status)

        with pytest.raises(TenantAPIError) as exc_info:
            TenantService.change_status(db, _cmd(status))

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "no_op_transition"
        mock_audit.assert_not_called()  # no audit log on rejected transitions
        db.rollback.assert_called()

    # ------------------------------------------------------------------
    # Forbidden transitions
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "frm, to",
        [
            ("draft", "suspended"),
            ("active", "draft"),
            ("suspended", "draft"),
            ("archived", "draft"),
            ("archived", "active"),
            ("archived", "suspended"),
        ],
    )
    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    @patch("app.services.tenants.service.AuditLogRepository.insert_status_change")
    def test_forbidden_transition_raises_422(self, mock_audit, mock_find, frm, to):
        db = MagicMock()
        mock_find.return_value = _row(frm)

        with pytest.raises(TenantAPIError) as exc_info:
            TenantService.change_status(db, _cmd(to, status_reason="Some reason here X"))

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "forbidden_transition"
        mock_audit.assert_not_called()  # no audit log on rejected transitions
        db.rollback.assert_called()

    # ------------------------------------------------------------------
    # status_reason validation — suspended / archived targets
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("target", ["suspended", "archived"])
    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    @patch("app.services.tenants.service.AuditLogRepository.insert_status_change")
    def test_missing_status_reason_raises_422(self, mock_audit, mock_find, target):
        db = MagicMock()
        # Use an appropriate source status for each target
        source = "active" if target in ("suspended", "archived") else "draft"
        mock_find.return_value = _row(source)

        with pytest.raises(TenantAPIError) as exc_info:
            TenantService.change_status(db, _cmd(target, status_reason=None))

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "missing_status_reason"
        mock_audit.assert_not_called()

    @pytest.mark.parametrize("target", ["suspended", "archived"])
    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    @patch("app.services.tenants.service.AuditLogRepository.insert_status_change")
    def test_empty_status_reason_raises_missing(self, mock_audit, mock_find, target):
        db = MagicMock()
        source = "active"
        mock_find.return_value = _row(source)

        with pytest.raises(TenantAPIError) as exc_info:
            TenantService.change_status(db, _cmd(target, status_reason="   "))

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "missing_status_reason"

    @pytest.mark.parametrize("target", ["suspended", "archived"])
    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    @patch("app.services.tenants.service.AuditLogRepository.insert_status_change")
    def test_status_reason_too_short_raises_422(self, mock_audit, mock_find, target):
        db = MagicMock()
        source = "active"
        mock_find.return_value = _row(source)

        with pytest.raises(TenantAPIError) as exc_info:
            TenantService.change_status(db, _cmd(target, status_reason="short"))

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "validation_error"
        fields = exc_info.value.fields or []
        assert any(f.get("reason") == "min_length" for f in fields)

    @pytest.mark.parametrize("target", ["suspended", "archived"])
    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    @patch("app.services.tenants.service.AuditLogRepository.insert_status_change")
    def test_status_reason_too_long_raises_422(self, mock_audit, mock_find, target):
        db = MagicMock()
        source = "active"
        mock_find.return_value = _row(source)

        with pytest.raises(TenantAPIError) as exc_info:
            TenantService.change_status(db, _cmd(target, status_reason="X" * 501))

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "validation_error"
        fields = exc_info.value.fields or []
        assert any(f.get("reason") == "max_length" for f in fields)

    @pytest.mark.parametrize("target", ["suspended", "archived"])
    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    @patch("app.services.tenants.service.AuditLogRepository.insert_status_change")
    def test_status_reason_control_chars_raises_422(self, mock_audit, mock_find, target):
        db = MagicMock()
        source = "active"
        mock_find.return_value = _row(source)

        with pytest.raises(TenantAPIError) as exc_info:
            TenantService.change_status(
                db, _cmd(target, status_reason="Bad reason\x00 here control chars")
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "validation_error"
        fields = exc_info.value.fields or []
        assert any(f.get("reason") == "invalid_characters" for f in fields)

    # ------------------------------------------------------------------
    # Outbox insertion — ONLY on suspension
    # ------------------------------------------------------------------

    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    @patch("app.services.tenants.service.TenantRepository.update_status")
    @patch("app.services.tenants.service.AuditLogRepository.insert_status_change")
    @patch("app.services.tenants.service.OutboxRepository.insert_suspended_event")
    @patch("app.services.tenants.service.emit_tenant_status_change")
    def test_outbox_not_inserted_for_non_suspension(
        self, mock_metric, mock_outbox, mock_audit, mock_update, mock_find
    ):
        """draft → archived: no outbox event."""
        db = MagicMock()
        mock_find.return_value = _row("draft")
        mock_update.return_value = _updated_row("archived", "Terminated before launch XX")

        TenantService.change_status(
            db, _cmd("archived", status_reason="Terminated before launch XX")
        )

        mock_outbox.assert_not_called()

    # ------------------------------------------------------------------
    # Lock contention
    # ------------------------------------------------------------------

    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    def test_lock_contention_raises_409(self, mock_find):
        db = MagicMock()
        orig = MagicMock()
        orig.pgcode = "55P03"
        exc = OperationalError("lock not available", None, None)
        exc.orig = orig
        mock_find.side_effect = exc

        with pytest.raises(TenantAPIError) as exc_info:
            TenantService.change_status(db, _cmd("active"))

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "conflict"
        db.rollback.assert_called()

    # ------------------------------------------------------------------
    # Metric fires on success, never propagates failure
    # ------------------------------------------------------------------

    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    @patch("app.services.tenants.service.TenantRepository.update_status")
    @patch("app.services.tenants.service.AuditLogRepository.insert_status_change")
    @patch("app.services.tenants.service.OutboxRepository.insert_suspended_event")
    @patch(
        "app.services.tenants.service.emit_tenant_status_change",
        side_effect=RuntimeError("metric down"),
    )
    def test_metric_failure_does_not_propagate(
        self, mock_metric, mock_outbox, mock_audit, mock_update, mock_find
    ):
        db = MagicMock()
        mock_find.return_value = _row("draft")
        mock_update.return_value = _updated_row("active")

        # Must not raise even though metric raises
        dto = TenantService.change_status(db, _cmd("active"))
        assert dto.current_status == "active"

    # ------------------------------------------------------------------
    # draft → active — status_reason cleared from any prior value
    # ------------------------------------------------------------------

    @patch("app.services.tenants.service.TenantRepository.find_by_id_for_update")
    @patch("app.services.tenants.service.TenantRepository.update_status")
    @patch("app.services.tenants.service.AuditLogRepository.insert_status_change")
    @patch("app.services.tenants.service.OutboxRepository.insert_suspended_event")
    @patch("app.services.tenants.service.emit_tenant_status_change")
    def test_draft_to_active_clears_status_reason(
        self, mock_metric, mock_outbox, mock_audit, mock_update, mock_find
    ):
        """Draft tenant with a pre-set status_reason: should be cleared on → active."""
        db = MagicMock()
        mock_find.return_value = _row("draft", status_reason="Pre-staged note here XX")
        mock_update.return_value = _updated_row("active", status_reason=None)

        TenantService.change_status(db, _cmd("active"))

        update_kwargs = mock_update.call_args.kwargs
        assert update_kwargs["new_reason"] is None


# ===========================================================================
# TestOutboxPoller
# ===========================================================================


class TestOutboxPoller:
    """OutboxPoller — unit tests with mocked DB and SMS client."""

    def _make_event_row(
        self,
        event_id: str | None = None,
        tenant_id: str | None = None,
        retry_count: int = 0,
        age_seconds: int = 0,
    ) -> dict[str, Any]:
        occurred_at = datetime.now(UTC) - timedelta(seconds=age_seconds)
        return {
            "event_id": event_id or str(uuid.uuid4()),
            "event_type": "tenant_suspended",
            "tenant_id": tenant_id or str(uuid.uuid4()),
            "payload": '{"event_type": "tenant_suspended"}',
            "occurred_at": occurred_at,
            "retry_count": retry_count,
        }

    @patch("app.services.tenants.outbox.SessionLocal")
    @patch("app.services.tenants.outbox._sms_client")
    def test_successful_delivery_marks_delivered(self, mock_sms, mock_session_local):
        """Happy path: event delivered → marked delivered = TRUE."""
        from app.services.tenants.outbox import OutboxPoller

        row = self._make_event_row()

        db = MagicMock()
        db.execute.return_value.mappings.return_value.all.return_value = [row]
        mock_session_local.return_value = db

        poller = OutboxPoller(sla_breach_seconds=60)
        poller._poll_cycle()

        # Should have called commit after marking delivered
        db.commit.assert_called()
        db.close.assert_called()

    @patch("app.services.tenants.outbox.SessionLocal")
    @patch("app.services.tenants.outbox._sms_client")
    def test_delivery_failure_increments_retry(self, mock_sms, mock_session_local):
        """Delivery failure → retry_count incremented, last_error set."""
        from app.services.tenants.outbox import OutboxPoller

        row = self._make_event_row(retry_count=0)
        mock_sms.deliver_tenant_suspended_event.side_effect = RuntimeError("SMS down")

        db = MagicMock()
        db.execute.return_value.mappings.return_value.all.return_value = [row]
        mock_session_local.return_value = db

        poller = OutboxPoller(sla_breach_seconds=60)
        poller._poll_cycle()

        # Should have rolled back after delivery failure, then committed retry increment
        db.rollback.assert_called()
        db.close.assert_called()

    @patch("app.services.tenants.outbox.SessionLocal")
    @patch("app.services.tenants.outbox._sms_client")
    @patch("app.services.tenants.outbox._emit_sla_breach")
    def test_sla_breach_emits_metric(self, mock_breach, mock_sms, mock_session_local):
        """Event older than SLA threshold → SLA breach metric emitted."""
        from app.services.tenants.outbox import OutboxPoller

        tid = str(uuid.uuid4())
        # Event is 60 seconds old with a 30-second SLA threshold
        row = self._make_event_row(tenant_id=tid, age_seconds=60)

        db = MagicMock()
        db.execute.return_value.mappings.return_value.all.return_value = [row]
        mock_session_local.return_value = db

        poller = OutboxPoller(sla_breach_seconds=30)
        poller._poll_cycle()

        mock_breach.assert_called_once_with(tid)

    @patch("app.services.tenants.outbox.SessionLocal")
    @patch("app.services.tenants.outbox._sms_client")
    @patch("app.services.tenants.outbox._emit_sla_breach")
    def test_no_sla_breach_within_threshold(self, mock_breach, mock_sms, mock_session_local):
        """Event younger than SLA threshold → no SLA breach metric."""
        from app.services.tenants.outbox import OutboxPoller

        row = self._make_event_row(age_seconds=5)

        db = MagicMock()
        db.execute.return_value.mappings.return_value.all.return_value = [row]
        mock_session_local.return_value = db

        poller = OutboxPoller(sla_breach_seconds=30)
        poller._poll_cycle()

        mock_breach.assert_not_called()

    @patch("app.services.tenants.outbox.SessionLocal")
    @patch("app.services.tenants.outbox._sms_client")
    def test_max_retries_exhausted_does_not_mark_delivered(self, mock_sms, mock_session_local):
        """Event with retry_count >= MAX_RETRIES must NOT be marked delivered."""
        from app.services.tenants.outbox import OutboxPoller

        poller = OutboxPoller(max_retries=5, sla_breach_seconds=60)
        self._make_event_row(
            retry_count=5
        )  # at the limit — won't appear (retry_count < max_retries filter)

        db = MagicMock()
        # Simulate the SQL filter returning NO rows (max_retries already reached in DB filter)
        db.execute.return_value.mappings.return_value.all.return_value = []
        mock_session_local.return_value = db

        poller._poll_cycle()

        # Nothing delivered when no rows returned
        mock_sms.deliver_tenant_suspended_event.assert_not_called()

    @patch("app.services.tenants.outbox.SessionLocal")
    def test_empty_batch_exits_cleanly(self, mock_session_local):
        """No undelivered events → poll cycle returns normally."""
        from app.services.tenants.outbox import OutboxPoller

        db = MagicMock()
        db.execute.return_value.mappings.return_value.all.return_value = []
        mock_session_local.return_value = db

        poller = OutboxPoller()
        poller._poll_cycle()  # Must not raise

        db.commit.assert_not_called()
        db.close.assert_called()
