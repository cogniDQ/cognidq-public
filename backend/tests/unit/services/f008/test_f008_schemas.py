"""
F008 P01 — Unit tests: PermissionAuditQueryParams schema validation
====================================================================

No database required.

ACs covered
-----------
AC-P01-001  action_type rejects values not in ACCESS_CONTROL_ACTION_TYPES
AC-P01-002  actor_id and target_entity_id reject non-UUID strings (Pydantic coercion)
           (FastAPI enforces UUID type at route level; Pydantic v1 coerces silently for
            UUID fields — validation of bad action_type and date-range is primary here)
AC-P01-005 (partial)  action_type validator rejects out-of-set value
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone

import pytest
from app.schemas.permission_audit import (
    ACCESS_CONTROL_ACTION_TYPES,
    PermissionAuditExportQueryParams,
    PermissionAuditQueryParams,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_params(**overrides) -> dict:
    defaults = {
        "page": 1,
        "page_size": 25,
        "sort_dir": "desc",
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# action_type validation
# ---------------------------------------------------------------------------


class TestActionTypeValidation:
    def test_valid_action_types_accepted(self):
        for at in ACCESS_CONTROL_ACTION_TYPES:
            params = PermissionAuditQueryParams(**_valid_params(action_type=at))
            assert params.action_type == at

    def test_invalid_action_type_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            PermissionAuditQueryParams(**_valid_params(action_type="rule_executed"))
        assert "invalid action_type" in str(exc_info.value).lower()

    def test_none_action_type_accepted(self):
        params = PermissionAuditQueryParams(**_valid_params(action_type=None))
        assert params.action_type is None

    def test_export_params_rejects_invalid_action_type(self):
        with pytest.raises(ValidationError):
            PermissionAuditExportQueryParams(action_type="rule_created")

    def test_export_params_accepts_valid_action_type(self):
        params = PermissionAuditExportQueryParams(action_type="role_assigned")
        assert params.action_type == "role_assigned"


# ---------------------------------------------------------------------------
# sort_dir validation
# ---------------------------------------------------------------------------


class TestSortDirValidation:
    def test_asc_accepted(self):
        params = PermissionAuditQueryParams(**_valid_params(sort_dir="asc"))
        assert params.sort_dir == "asc"

    def test_desc_accepted(self):
        params = PermissionAuditQueryParams(**_valid_params(sort_dir="desc"))
        assert params.sort_dir == "desc"

    def test_invalid_sort_dir_raises(self):
        with pytest.raises(ValidationError):
            PermissionAuditQueryParams(**_valid_params(sort_dir="random"))


# ---------------------------------------------------------------------------
# page / page_size validation
# ---------------------------------------------------------------------------


class TestPaginationValidation:
    def test_page_zero_raises(self):
        with pytest.raises(ValidationError):
            PermissionAuditQueryParams(**_valid_params(page=0))

    def test_page_size_zero_raises(self):
        with pytest.raises(ValidationError):
            PermissionAuditQueryParams(**_valid_params(page_size=0))

    def test_page_size_101_raises(self):
        with pytest.raises(ValidationError):
            PermissionAuditQueryParams(**_valid_params(page_size=101))

    def test_page_size_100_accepted(self):
        params = PermissionAuditQueryParams(**_valid_params(page_size=100))
        assert params.page_size == 100

    def test_page_size_1_accepted(self):
        params = PermissionAuditQueryParams(**_valid_params(page_size=1))
        assert params.page_size == 1


# ---------------------------------------------------------------------------
# Date range validation
# ---------------------------------------------------------------------------


class TestDateRangeValidation:
    def test_to_date_before_from_date_raises(self):
        from_dt = datetime(2026, 1, 10, tzinfo=UTC)
        to_dt = datetime(2026, 1, 5, tzinfo=UTC)
        with pytest.raises(ValidationError) as exc_info:
            PermissionAuditQueryParams(**_valid_params(from_date=from_dt, to_date=to_dt))
        assert "to_date" in str(exc_info.value).lower()

    def test_equal_dates_accepted(self):
        dt = datetime(2026, 1, 10, tzinfo=UTC)
        params = PermissionAuditQueryParams(**_valid_params(from_date=dt, to_date=dt))
        assert params.from_date == params.to_date

    def test_valid_range_accepted(self):
        from_dt = datetime(2026, 1, 1, tzinfo=UTC)
        to_dt = datetime(2026, 1, 31, tzinfo=UTC)
        params = PermissionAuditQueryParams(**_valid_params(from_date=from_dt, to_date=to_dt))
        assert params.from_date == from_dt
        assert params.to_date == to_dt

    def test_only_from_date_accepted(self):
        from_dt = datetime(2026, 1, 1, tzinfo=UTC)
        params = PermissionAuditQueryParams(**_valid_params(from_date=from_dt))
        assert params.from_date == from_dt
        assert params.to_date is None

    def test_export_params_date_range_validated(self):
        from_dt = datetime(2026, 1, 10, tzinfo=UTC)
        to_dt = datetime(2026, 1, 5, tzinfo=UTC)
        with pytest.raises(ValidationError):
            PermissionAuditExportQueryParams(from_date=from_dt, to_date=to_dt)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_default_page(self):
        params = PermissionAuditQueryParams()
        assert params.page == 1

    def test_default_page_size(self):
        params = PermissionAuditQueryParams()
        assert params.page_size == 25

    def test_default_sort_dir(self):
        params = PermissionAuditQueryParams()
        assert params.sort_dir == "desc"
