"""
Integration tests — F003 Packet 2: Settings Repository

Verifies all SQL operations in settings_repository.py against the live
PostgreSQL database.  The control.workspace_settings table must exist
(applied by migration 008_f003_workspace_settings.sql — P01).

Run:
    docker exec dq-backend-1 python -m pytest tests/integration/test_f003_p02_repository.py -v
"""

import json
import os
import uuid
from datetime import UTC, datetime, timezone

import psycopg2
import psycopg2.extras
import pytest

psycopg2.extras.register_uuid()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@db:5432/dataquality_db",
)

NOW = datetime.now(UTC)

# ─────────────────────────────────────────────────────────────────────────────
# DB fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def conn():
    connection = psycopg2.connect(DATABASE_URL)
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture()
def cur(conn):
    """Per-test cursor with savepoint rollback — no committed side-effects."""
    mgmt = conn.cursor()
    mgmt.execute("SAVEPOINT sp_test")
    mgmt.close()
    cursor = conn.cursor()
    yield cursor
    cursor.close()
    cleanup = conn.cursor()
    cleanup.execute("ROLLBACK TO SAVEPOINT sp_test")
    cleanup.execute("RELEASE SAVEPOINT sp_test")
    cleanup.close()


# ─────────────────────────────────────────────────────────────────────────────
# SQLAlchemy session fixture wrapping the psycopg2 connection
# ─────────────────────────────────────────────────────────────────────────────

import re
from unittest.mock import MagicMock

from sqlalchemy import text as sa_text


def _sa_to_psycopg2(sql_str: str) -> str:
    """Convert SQLAlchemy :named_param placeholders to psycopg2 %(named_param)s.

    Uses a negative lookbehind to avoid converting PostgreSQL cast syntax
    ``::typename`` (double-colon) into a parameter placeholder.
    """
    return re.sub(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)", r"%(\1)s", sql_str)


class _PsycopgSession:
    """Minimal SQLAlchemy Session shim backed by a psycopg2 cursor.

    Converts SQLAlchemy-style ``:named`` parameters to psycopg2-style
    ``%(named)s`` parameters so that the repository functions can be tested
    against a live psycopg2 connection without a full SQLAlchemy engine.
    """

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, stmt, params=None):
        # Extract raw SQL text from SQLAlchemy text() objects
        if hasattr(stmt, "text"):
            sql_str = stmt.text
        else:
            sql_str = str(stmt)
        # Convert :param → %(param)s for psycopg2 (skip ::cast syntax)
        pg_sql = _sa_to_psycopg2(sql_str)
        self._cursor.execute(pg_sql, params or {})
        return _PsycopgResult(self._cursor)


class _PsycopgResult:
    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _new_tenant(cur) -> uuid.UUID:
    tid = uuid.uuid4()
    actor = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO control.tenants (
            tenant_id, tenant_name, tenant_slug,
            status, region, plan,
            created_by, updated_by, version,
            created_at, updated_at
        ) VALUES (%s, %s, %s, 'active', 'eu-west', 'starter',
                  %s, %s, 0, NOW(), NOW())
        """,
        (tid, f"Tenant {tid}", f"t-{str(tid)[:8]}", actor, actor),
    )
    return tid


def _new_workspace(cur, tenant_id: uuid.UUID, timezone_str: str = "UTC") -> uuid.UUID:
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = f"WS {wid}"
    cur.execute(
        """
        INSERT INTO control.workspaces (
            workspace_id, tenant_id, workspace_name, workspace_name_lower,
            workspace_slug, description, default_timezone, status, status_reason,
            created_at, updated_at, created_by, updated_by, version
        ) VALUES (
            %s, %s, %s, %s, %s, NULL, %s, 'active', NULL,
            NOW(), NOW(), %s, %s, 0
        )
        """,
        (wid, tenant_id, name, name.lower(), f"ws-{str(wid)[:8]}", timezone_str, actor, actor),
    )
    return wid


def _get_raw_settings(cur, workspace_id: uuid.UUID):
    cur.execute(
        """
        SELECT workspace_id, tenant_id, default_timezone,
               severity_policy, sla_policy, issue_grouping_policy,
               naming_standards, updated_at, updated_by
        FROM control.workspace_settings
        WHERE workspace_id = %s
        """,
        (workspace_id,),
    )
    return cur.fetchone()


# ─────────────────────────────────────────────────────────────────────────────
# Import repository under test (inside Docker; source is volume-mounted)
# ─────────────────────────────────────────────────────────────────────────────

from app.services.workspaces import settings_repository as repo
from app.services.workspaces.settings_models import (
    NamingConstraint,
    NamingStandards,
    SeverityPolicy,
    SLAPolicy,
    WorkspaceSettings,
    WorkspaceSettingsUpdate,
)

# ─────────────────────────────────────────────────────────────────────────────
# AC-P02 Test classes
# ─────────────────────────────────────────────────────────────────────────────


class TestFindByWorkspaceId:
    """find_by_workspace_id — happy path and tenant isolation."""

    def test_returns_settings_row_for_existing_workspace(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        db = _PsycopgSession(cur)
        result = repo.find_by_workspace_id(db, wid, tid)
        assert result is not None
        assert result.workspace_id == wid
        assert result.tenant_id == tid

    def test_returns_none_for_nonexistent_workspace(self, cur):
        tid = _new_tenant(cur)
        db = _PsycopgSession(cur)
        result = repo.find_by_workspace_id(db, uuid.uuid4(), tid)
        assert result is None

    def test_returns_none_for_wrong_tenant(self, cur):
        tid1 = _new_tenant(cur)
        tid2 = _new_tenant(cur)
        wid = _new_workspace(cur, tid1)
        db = _PsycopgSession(cur)
        result = repo.find_by_workspace_id(db, wid, tid2)
        assert result is None

    def test_platform_operator_omits_tenant_filter(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        db = _PsycopgSession(cur)
        # None tenant_id = Platform Operator — should still find the row
        result = repo.find_by_workspace_id(db, wid, None)
        assert result is not None
        assert result.workspace_id == wid

    def test_default_timezone_copied_from_workspace(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid, timezone_str="America/Chicago")
        db = _PsycopgSession(cur)
        result = repo.find_by_workspace_id(db, wid, tid)
        assert result.default_timezone == "America/Chicago"

    def test_jsonb_columns_are_none_by_default(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        db = _PsycopgSession(cur)
        result = repo.find_by_workspace_id(db, wid, tid)
        assert result.severity_policy is None
        assert result.sla_policy is None
        assert result.naming_standards is None

    def test_returns_workspace_settings_instance(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        db = _PsycopgSession(cur)
        result = repo.find_by_workspace_id(db, wid, tid)
        assert isinstance(result, WorkspaceSettings)


class TestCreateDefault:
    """create_default — inserts or returns existing row."""

    def test_creates_row_when_absent(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        # Delete the trigger-created row so create_default has to do the work
        cur.execute(
            "DELETE FROM control.workspace_settings WHERE workspace_id = %s",
            (wid,),
        )
        db = _PsycopgSession(cur)
        result = repo.create_default(db, wid, tid, "Europe/London")
        assert result is not None
        assert result.workspace_id == wid
        assert result.default_timezone == "Europe/London"
        assert result.issue_grouping_policy == "one_per_execution"

    def test_on_conflict_returns_existing_row(self, cur):
        """Calling create_default when a row already exists must not raise."""
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        db = _PsycopgSession(cur)
        # Row exists from trigger; create_default should handle ON CONFLICT
        result = repo.create_default(db, wid, tid, "UTC")
        assert result is not None
        assert result.workspace_id == wid

    def test_new_row_has_null_jsonb_columns(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        cur.execute(
            "DELETE FROM control.workspace_settings WHERE workspace_id = %s",
            (wid,),
        )
        db = _PsycopgSession(cur)
        result = repo.create_default(db, wid, tid, "UTC")
        assert result.severity_policy is None
        assert result.sla_policy is None
        assert result.naming_standards is None

    def test_new_row_has_null_updated_by(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        cur.execute(
            "DELETE FROM control.workspace_settings WHERE workspace_id = %s",
            (wid,),
        )
        db = _PsycopgSession(cur)
        result = repo.create_default(db, wid, tid, "UTC")
        assert result.updated_by is None


class TestUpdateSettings:
    """update_settings — partial update with SELECT FOR UPDATE."""

    def test_updates_timezone(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        actor = uuid.uuid4()
        db = _PsycopgSession(cur)
        upd = WorkspaceSettingsUpdate(default_timezone="Asia/Tokyo")
        result = repo.update_settings(db, wid, tid, upd, actor, NOW)
        assert result.default_timezone == "Asia/Tokyo"

    def test_updates_grouping_policy(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        actor = uuid.uuid4()
        db = _PsycopgSession(cur)
        upd = WorkspaceSettingsUpdate(issue_grouping_policy="one_per_rule")
        result = repo.update_settings(db, wid, tid, upd, actor, NOW)
        assert result.issue_grouping_policy == "one_per_rule"

    def test_updates_severity_policy(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        actor = uuid.uuid4()
        db = _PsycopgSession(cur)
        sev = SeverityPolicy("P1", "P2", "P3", "P4")
        upd = WorkspaceSettingsUpdate(severity_policy=sev)
        result = repo.update_settings(db, wid, tid, upd, actor, NOW)
        assert result.severity_policy is not None
        assert result.severity_policy.critical_label == "P1"

    def test_updates_sla_policy(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        actor = uuid.uuid4()
        db = _PsycopgSession(cur)
        sla = SLAPolicy(2, 12, 48, None)
        upd = WorkspaceSettingsUpdate(sla_policy=sla)
        result = repo.update_settings(db, wid, tid, upd, actor, NOW)
        assert result.sla_policy is not None
        assert result.sla_policy.critical_hours == 2

    def test_updates_naming_standards(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        actor = uuid.uuid4()
        db = _PsycopgSession(cur)
        nc = NamingConstraint("raw_", None, None, 200, None)
        ns = NamingStandards(datasets=nc, rules=NamingConstraint(None, None, None, None, None))
        upd = WorkspaceSettingsUpdate(naming_standards=ns)
        result = repo.update_settings(db, wid, tid, upd, actor, NOW)
        assert result.naming_standards is not None
        assert result.naming_standards.datasets.required_prefix == "raw_"

    def test_partial_update_does_not_affect_other_columns(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid, timezone_str="America/New_York")
        actor = uuid.uuid4()
        db = _PsycopgSession(cur)
        # Only update grouping — timezone should stay
        upd = WorkspaceSettingsUpdate(issue_grouping_policy="one_per_day")
        result = repo.update_settings(db, wid, tid, upd, actor, NOW)
        assert result.issue_grouping_policy == "one_per_day"
        assert result.default_timezone == "America/New_York"

    def test_sets_updated_by_to_actor_id(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        actor = uuid.uuid4()
        db = _PsycopgSession(cur)
        upd = WorkspaceSettingsUpdate(default_timezone="UTC")
        result = repo.update_settings(db, wid, tid, upd, actor, NOW)
        assert result.updated_by == actor

    def test_raises_settings_not_found_if_no_row(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        # Remove the settings row
        cur.execute(
            "DELETE FROM control.workspace_settings WHERE workspace_id = %s",
            (wid,),
        )
        actor = uuid.uuid4()
        db = _PsycopgSession(cur)
        upd = WorkspaceSettingsUpdate(default_timezone="UTC")
        with pytest.raises(repo.SettingsNotFoundError):
            repo.update_settings(db, wid, tid, upd, actor, NOW)


class TestJsonbRoundTrip:
    """Verify JSONB serialisation and deserialisation round-trips correctly."""

    def test_severity_policy_round_trips(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        actor = uuid.uuid4()
        db = _PsycopgSession(cur)
        sev = SeverityPolicy("Critical-X", "Major-X", "Minor-X", "Info-X")
        repo.update_settings(db, wid, tid, WorkspaceSettingsUpdate(severity_policy=sev), actor, NOW)
        result = repo.find_by_workspace_id(db, wid, tid)
        assert result.severity_policy == sev

    def test_sla_policy_round_trips(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        actor = uuid.uuid4()
        db = _PsycopgSession(cur)
        sla = SLAPolicy(1, 8, 24, 72)
        repo.update_settings(db, wid, tid, WorkspaceSettingsUpdate(sla_policy=sla), actor, NOW)
        result = repo.find_by_workspace_id(db, wid, tid)
        assert result.sla_policy == sla

    def test_naming_standards_round_trips(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        actor = uuid.uuid4()
        db = _PsycopgSession(cur)
        nc_ds = NamingConstraint("ds_", "_end", r"^[a-z]+$", 128, False)
        nc_ru = NamingConstraint(None, None, None, None, True)
        ns = NamingStandards(datasets=nc_ds, rules=nc_ru)
        repo.update_settings(db, wid, tid, WorkspaceSettingsUpdate(naming_standards=ns), actor, NOW)
        result = repo.find_by_workspace_id(db, wid, tid)
        assert result.naming_standards.datasets == nc_ds
        assert result.naming_standards.rules == nc_ru

    def test_empty_naming_constraint_round_trips(self, cur):
        """Empty NamingConstraint (all None) should round-trip correctly."""
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        actor = uuid.uuid4()
        db = _PsycopgSession(cur)
        empty_nc = NamingConstraint(None, None, None, None, None)
        ns = NamingStandards(datasets=empty_nc, rules=empty_nc)
        repo.update_settings(db, wid, tid, WorkspaceSettingsUpdate(naming_standards=ns), actor, NOW)
        result = repo.find_by_workspace_id(db, wid, tid)
        assert result.naming_standards.datasets == empty_nc
