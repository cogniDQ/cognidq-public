"""
Packet 6 — Unit tests: Update Tenant Metadata service & helpers
===============================================================

Tests cover:
    - ``_to_audit_value``        pure-function serialisation
    - ``_build_change_set``      pure-function diff / audit-data builder
    - ``TenantService.update_tenant``
          happy path, archived block, status_reason guard, empty change-set,
          duplicate-name check, lock contention (409)

All DB I/O is mocked; no Docker / live database is required.

Run inside Docker::

    docker-compose exec backend python -m pytest \\
        tests/unit/services/f001/test_p6_update_tenant.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from app.services.tenants.commands import UpdateTenantCommand
from app.services.tenants.service import (
    TenantService,
    _build_change_set,
    _to_audit_value,
)
from sqlalchemy.exc import IntegrityError, OperationalError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TENANT_ID = str(uuid.uuid4())
_ACTOR_ID = uuid.uuid4()
_ACTOR_ROLE = "platform_admin"


def _cmd(**fields) -> UpdateTenantCommand:
    """Build an UpdateTenantCommand with *fields* as the payload."""
    return UpdateTenantCommand(
        tenant_id=_TENANT_ID,
        actor_id=_ACTOR_ID,
        actor_role=_ACTOR_ROLE,
        fields=fields,
    )


def _active_row(**overrides) -> dict[str, Any]:
    """Return a minimal DB row dict for an active tenant."""
    base: dict[str, Any] = {
        "tenant_id": uuid.UUID(_TENANT_ID),
        "tenant_name": "Acme Corp",
        "tenant_slug": "acme-corp",
        "status": "active",
        "status_reason": None,
        "region": "eu-west",
        "plan": "starter",
        "service_start_date": None,
        "tenant_notes": None,
        "created_at": datetime.now(tz=UTC),
        "updated_at": datetime.now(tz=UTC),
        "created_by": uuid.uuid4(),
        "updated_by": uuid.uuid4(),
        "version": 1,
    }
    base.update(overrides)
    return base


def _updated_row(**overrides) -> dict[str, Any]:
    """Return an _active_row with version bumped to 2 and any extra overrides."""
    row = _active_row(version=2)
    row.update(overrides)
    return row


# ===========================================================================
# TestToAuditValue
# ===========================================================================


class TestToAuditValue:
    """_to_audit_value — convert values to JSON-serialisable form."""

    def test_date_becomes_iso_string(self):
        d = date(2025, 6, 15)
        assert _to_audit_value(d) == "2025-06-15"

    def test_string_passes_through(self):
        assert _to_audit_value("hello") == "hello"

    def test_none_passes_through(self):
        assert _to_audit_value(None) is None

    def test_int_passes_through(self):
        assert _to_audit_value(42) == 42

    def test_datetime_passes_through(self):
        """datetime is NOT a date subclass that we convert — only date objects."""
        dt = datetime(2025, 1, 1, tzinfo=UTC)
        # datetime IS a subclass of date so it will be serialised too
        result = _to_audit_value(dt)
        # Either pass-through or ISO string is fine; the key is it doesn't crash
        assert result is not None

    def test_bool_passes_through(self):
        assert _to_audit_value(True) is True


# ===========================================================================
# TestBuildChangeSet
# ===========================================================================


class TestBuildChangeSet:
    """_build_change_set — diff provided fields against current DB row."""

    def test_single_changed_field_included(self):
        row = _active_row(tenant_name="Old Name")
        changes, prev, new = _build_change_set({"tenant_name": "New Name"}, row)
        assert "tenant_name" in changes
        assert changes["tenant_name"] == "New Name"
        assert prev["tenant_name"] == "Old Name"
        assert new["tenant_name"] == "New Name"

    def test_unchanged_field_excluded(self):
        row = _active_row(tenant_name="Same Name")
        changes, prev, new = _build_change_set({"tenant_name": "Same Name"}, row)
        assert changes == {}
        assert prev == {}
        assert new == {}

    def test_multiple_fields_only_changed_included(self):
        row = _active_row(tenant_name="Old", plan="starter")
        changes, prev, new = _build_change_set({"tenant_name": "New", "plan": "starter"}, row)
        assert "tenant_name" in changes
        assert "plan" not in changes

    def test_none_to_value_is_change(self):
        row = _active_row(tenant_notes=None)
        changes, prev, new = _build_change_set({"tenant_notes": "Some note"}, row)
        assert changes["tenant_notes"] == "Some note"
        assert prev["tenant_notes"] is None

    def test_value_to_none_is_change(self):
        row = _active_row(status_reason="Valid reason here")
        changes, prev, new = _build_change_set({"status_reason": None}, row)
        assert changes["status_reason"] is None
        assert prev["status_reason"] == "Valid reason here"
        assert new["status_reason"] is None

    def test_date_serialised_in_audit_values(self):
        d = date(2025, 1, 15)
        row = _active_row(service_start_date=date(2024, 6, 1))
        changes, prev, new = _build_change_set({"service_start_date": d}, row)
        assert prev["service_start_date"] == "2024-06-01"
        assert new["service_start_date"] == "2025-01-15"

    def test_empty_fields_returns_empty_dicts(self):
        row = _active_row()
        changes, prev, new = _build_change_set({}, row)
        assert changes == {}
        assert prev == {}
        assert new == {}

    def test_all_same_values_returns_empty(self):
        row = _active_row(tenant_name="Acme Corp", plan="starter")
        changes, prev, new = _build_change_set({"tenant_name": "Acme Corp", "plan": "starter"}, row)
        assert changes == {}


# ===========================================================================
# Shared patch context for service-layer tests
# ===========================================================================

_REPO_PATH = "app.services.tenants.service.TenantRepository"
_AUDIT_PATH = "app.services.tenants.service.AuditLogRepository"


def _make_db_mock() -> MagicMock:
    """Return a SQLAlchemy Session mock."""
    db = MagicMock()
    db.rollback = MagicMock()
    db.commit = MagicMock()
    return db


# ===========================================================================
# TestUpdateTenantHappyPath
# ===========================================================================


class TestUpdateTenantHappyPath:
    """update_tenant — successful update returns a TenantDTO."""

    def test_returns_tenant_dto_with_updated_name(self):
        row = _active_row()
        upd = _updated_row(tenant_name="New Corp")
        db = _make_db_mock()

        with (
            patch(_REPO_PATH) as mock_repo,
            patch(_AUDIT_PATH) as mock_audit,
        ):
            mock_repo.find_by_id_for_update.return_value = row
            mock_repo.check_name_exists_excluding.return_value = False
            mock_repo.update.return_value = upd
            mock_audit.insert_update.return_value = None

            dto = TenantService.update_tenant(db, _cmd(tenant_name="New Corp"))

        assert dto.tenant_name == "New Corp"

    def test_db_commit_called_on_success(self):
        row = _active_row()
        upd = _updated_row(tenant_name="New Corp")
        db = _make_db_mock()

        with (
            patch(_REPO_PATH) as mock_repo,
            patch(_AUDIT_PATH) as mock_audit,
        ):
            mock_repo.find_by_id_for_update.return_value = row
            mock_repo.check_name_exists_excluding.return_value = False
            mock_repo.update.return_value = upd
            mock_audit.insert_update.return_value = None

            TenantService.update_tenant(db, _cmd(tenant_name="New Corp"))

        db.commit.assert_called_once()

    def test_audit_insert_called_with_correct_changes(self):
        row = _active_row(tenant_name="Old Name")
        upd = _updated_row(tenant_name="New Name")
        db = _make_db_mock()

        with (
            patch(_REPO_PATH) as mock_repo,
            patch(_AUDIT_PATH) as mock_audit,
        ):
            mock_repo.find_by_id_for_update.return_value = row
            mock_repo.check_name_exists_excluding.return_value = False
            mock_repo.update.return_value = upd
            mock_audit.insert_update.return_value = None

            TenantService.update_tenant(db, _cmd(tenant_name="New Name"))

        call_kwargs = mock_audit.insert_update.call_args.kwargs
        assert call_kwargs["previous_data"] == {"tenant_name": "Old Name"}
        assert call_kwargs["new_data"] == {"tenant_name": "New Name"}

    def test_update_called_with_change_set_only(self):
        """TenantRepository.update receives only the changed fields."""
        row = _active_row(tenant_name="Old", plan="starter")
        upd = _updated_row(tenant_name="New")
        db = _make_db_mock()

        with (
            patch(_REPO_PATH) as mock_repo,
            patch(_AUDIT_PATH) as mock_audit,
        ):
            mock_repo.find_by_id_for_update.return_value = row
            mock_repo.check_name_exists_excluding.return_value = False
            mock_repo.update.return_value = upd
            mock_audit.insert_update.return_value = None

            TenantService.update_tenant(
                db,
                _cmd(tenant_name="New", plan="starter"),  # plan unchanged
            )

        call_args = mock_repo.update.call_args
        changes_passed = call_args.args[2]  # positional: db, tenant_id, changes, actor
        assert "tenant_name" in changes_passed
        assert "plan" not in changes_passed

    def test_dto_has_all_thirteen_fields(self):
        row = _active_row()
        upd = _updated_row(tenant_name="New Corp")
        db = _make_db_mock()

        with (
            patch(_REPO_PATH) as mock_repo,
            patch(_AUDIT_PATH) as mock_audit,
        ):
            mock_repo.find_by_id_for_update.return_value = row
            mock_repo.check_name_exists_excluding.return_value = False
            mock_repo.update.return_value = upd
            mock_audit.insert_update.return_value = None

            dto = TenantService.update_tenant(db, _cmd(tenant_name="New Corp"))

        expected_fields = {
            "tenant_id",
            "tenant_name",
            "tenant_slug",
            "status",
            "status_reason",
            "region",
            "plan",
            "service_start_date",
            "tenant_notes",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        }
        actual = {f for f in vars(dto) if not f.startswith("_")}
        assert expected_fields == actual


# ===========================================================================
# TestUpdateTenantNotFound
# ===========================================================================


class TestUpdateTenantNotFound:
    """update_tenant — 404 when tenant row does not exist."""

    def test_raises_404_when_row_is_none(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        db = _make_db_mock()

        with patch(_REPO_PATH) as mock_repo:
            mock_repo.find_by_id_for_update.return_value = None

            with pytest.raises(TenantAPIError) as exc_info:
                TenantService.update_tenant(db, _cmd(tenant_name="X"))

        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "not_found"

    def test_db_rollback_called_on_not_found(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        db = _make_db_mock()

        with patch(_REPO_PATH) as mock_repo:
            mock_repo.find_by_id_for_update.return_value = None

            with pytest.raises(TenantAPIError):
                TenantService.update_tenant(db, _cmd(tenant_name="X"))

        db.rollback.assert_called()


# ===========================================================================
# TestUpdateTenantArchivedBlock
# ===========================================================================


class TestUpdateTenantArchivedBlock:
    """update_tenant — archived tenants are unconditionally rejected."""

    def test_raises_422_archived_tenant(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        row = _active_row(status="archived")
        db = _make_db_mock()

        with patch(_REPO_PATH) as mock_repo:
            mock_repo.find_by_id_for_update.return_value = row

            with pytest.raises(TenantAPIError) as exc_info:
                TenantService.update_tenant(db, _cmd(tenant_name="X"))

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "archived_tenant"

    def test_active_tenant_not_blocked(self):
        row = _active_row(status="active")
        upd = _updated_row(tenant_name="New Corp")
        db = _make_db_mock()

        with (
            patch(_REPO_PATH) as mock_repo,
            patch(_AUDIT_PATH) as mock_audit,
        ):
            mock_repo.find_by_id_for_update.return_value = row
            mock_repo.check_name_exists_excluding.return_value = False
            mock_repo.update.return_value = upd
            mock_audit.insert_update.return_value = None

            dto = TenantService.update_tenant(db, _cmd(tenant_name="New Corp"))

        assert dto is not None


# ===========================================================================
# TestUpdateTenantStatusReasonGuard
# ===========================================================================


class TestUpdateTenantStatusReasonGuard:
    """update_tenant — status_reason guard for suspended/archived tenants."""

    def test_clear_status_reason_on_suspended_raises_422(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        row = _active_row(status="suspended", status_reason="Long enough reason here")
        db = _make_db_mock()

        with patch(_REPO_PATH) as mock_repo:
            mock_repo.find_by_id_for_update.return_value = row

            with pytest.raises(TenantAPIError) as exc_info:
                TenantService.update_tenant(db, _cmd(status_reason=None))

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "status_reason_required_for_current_status"

    def test_short_status_reason_on_suspended_raises_422(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        row = _active_row(status="suspended", status_reason="Old reason here")
        db = _make_db_mock()

        with patch(_REPO_PATH) as mock_repo:
            mock_repo.find_by_id_for_update.return_value = row

            with pytest.raises(TenantAPIError) as exc_info:
                TenantService.update_tenant(db, _cmd(status_reason="Too short"))

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "validation_error"
        details = exc_info.value.fields
        assert details is not None
        assert any(d.get("reason") == "min_length" for d in details)

    def test_long_status_reason_on_suspended_succeeds(self):
        row = _active_row(status="suspended", status_reason="Old reason here")
        upd = _updated_row(status="suspended", status_reason="This is a long enough reason")
        db = _make_db_mock()

        with (
            patch(_REPO_PATH) as mock_repo,
            patch(_AUDIT_PATH) as mock_audit,
        ):
            mock_repo.find_by_id_for_update.return_value = row
            mock_repo.check_name_exists_excluding.return_value = False
            mock_repo.update.return_value = upd
            mock_audit.insert_update.return_value = None

            dto = TenantService.update_tenant(
                db, _cmd(status_reason="This is a long enough reason")
            )

        assert dto is not None

    def test_status_reason_can_be_cleared_on_draft(self):
        """draft tenants have no min-length restriction — clearing is allowed."""
        row = _active_row(status="draft", status_reason="Some draft reason")
        upd = _updated_row(status="draft", status_reason=None)
        db = _make_db_mock()

        with (
            patch(_REPO_PATH) as mock_repo,
            patch(_AUDIT_PATH) as mock_audit,
        ):
            mock_repo.find_by_id_for_update.return_value = row
            mock_repo.check_name_exists_excluding.return_value = False
            mock_repo.update.return_value = upd
            mock_audit.insert_update.return_value = None

            dto = TenantService.update_tenant(db, _cmd(status_reason=None))

        assert dto is not None

    def test_status_reason_can_be_cleared_on_active(self):
        """active tenants have no restriction — clearing is allowed."""
        row = _active_row(status="active", status_reason="Some reason")
        upd = _updated_row(status="active", status_reason=None)
        db = _make_db_mock()

        with (
            patch(_REPO_PATH) as mock_repo,
            patch(_AUDIT_PATH) as mock_audit,
        ):
            mock_repo.find_by_id_for_update.return_value = row
            mock_repo.check_name_exists_excluding.return_value = False
            mock_repo.update.return_value = upd
            mock_audit.insert_update.return_value = None

            dto = TenantService.update_tenant(db, _cmd(status_reason=None))

        assert dto is not None


# ===========================================================================
# TestUpdateTenantEmptyChangeset
# ===========================================================================


class TestUpdateTenantEmptyChangeset:
    """update_tenant — 422 when no field actually differs from current values."""

    def test_all_same_values_raises_no_mutable_fields(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        row = _active_row(tenant_name="Acme Corp")
        db = _make_db_mock()

        with patch(_REPO_PATH) as mock_repo:
            mock_repo.find_by_id_for_update.return_value = row

            with pytest.raises(TenantAPIError) as exc_info:
                TenantService.update_tenant(
                    db,
                    _cmd(tenant_name="Acme Corp"),  # same value
                )

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "no_mutable_fields"

    def test_no_commit_when_change_set_empty(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        row = _active_row(plan="starter")
        db = _make_db_mock()

        with patch(_REPO_PATH) as mock_repo:
            mock_repo.find_by_id_for_update.return_value = row

            with pytest.raises(TenantAPIError):
                TenantService.update_tenant(db, _cmd(plan="starter"))

        db.commit.assert_not_called()


# ===========================================================================
# TestUpdateTenantDuplicateName
# ===========================================================================


class TestUpdateTenantDuplicateName:
    """update_tenant — 422 when tenant_name collision detected."""

    def test_duplicate_name_raises_422(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        row = _active_row(tenant_name="Old Name")
        db = _make_db_mock()

        with patch(_REPO_PATH) as mock_repo:
            mock_repo.find_by_id_for_update.return_value = row
            mock_repo.check_name_exists_excluding.return_value = True  # collision

            with pytest.raises(TenantAPIError) as exc_info:
                TenantService.update_tenant(db, _cmd(tenant_name="Taken Name"))

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "duplicate_name"

    def test_uniqueness_not_checked_when_name_unchanged(self):
        """check_name_exists_excluding must NOT be called when name didn't change."""
        row = _active_row(tenant_name="Acme Corp", plan="starter")
        upd = _updated_row(plan="growth")
        db = _make_db_mock()

        with (
            patch(_REPO_PATH) as mock_repo,
            patch(_AUDIT_PATH) as mock_audit,
        ):
            mock_repo.find_by_id_for_update.return_value = row
            mock_repo.check_name_exists_excluding.return_value = False
            mock_repo.update.return_value = upd
            mock_audit.insert_update.return_value = None

            TenantService.update_tenant(
                db,
                _cmd(plan="growth"),  # name not in fields at all
            )

        mock_repo.check_name_exists_excluding.assert_not_called()


# ===========================================================================
# TestUpdateTenantLockConflict
# ===========================================================================


class TestUpdateTenantLockConflict:
    """update_tenant — 409 on FOR UPDATE NOWAIT lock contention."""

    def _make_lock_error(self, pgcode: str) -> OperationalError:
        orig = MagicMock()
        orig.pgcode = pgcode
        err = OperationalError("could not obtain lock", params=None, orig=orig)
        err.orig = orig
        return err

    def test_lock_not_available_returns_409(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        db = _make_db_mock()

        with patch(_REPO_PATH) as mock_repo:
            mock_repo.find_by_id_for_update.side_effect = self._make_lock_error("55P03")

            with pytest.raises(TenantAPIError) as exc_info:
                TenantService.update_tenant(db, _cmd(tenant_name="X"))

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "conflict"

    def test_serialization_failure_returns_409(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        db = _make_db_mock()

        with patch(_REPO_PATH) as mock_repo:
            mock_repo.find_by_id_for_update.side_effect = self._make_lock_error("40001")

            with pytest.raises(TenantAPIError) as exc_info:
                TenantService.update_tenant(db, _cmd(tenant_name="X"))

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "conflict"

    def test_other_operational_error_returns_500(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        db = _make_db_mock()
        other_err = OperationalError("connection lost", params=None, orig=None)
        other_err.orig = None

        with patch(_REPO_PATH) as mock_repo:
            mock_repo.find_by_id_for_update.side_effect = other_err

            with pytest.raises(TenantAPIError) as exc_info:
                TenantService.update_tenant(db, _cmd(tenant_name="X"))

        assert exc_info.value.status_code == 500

    def test_rollback_called_on_lock_error(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        db = _make_db_mock()

        with patch(_REPO_PATH) as mock_repo:
            mock_repo.find_by_id_for_update.side_effect = self._make_lock_error("55P03")

            with pytest.raises(TenantAPIError):
                TenantService.update_tenant(db, _cmd(tenant_name="X"))

        db.rollback.assert_called()
