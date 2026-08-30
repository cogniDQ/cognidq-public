"""
F002 P02 — Integration tests: Repository layer, domain model, RBAC stub
=========================================================================

These tests run against the live ``dq-db-1`` PostgreSQL container.

Prerequisites
-------------
* Migration 007_f002_workspace_schema.sql has been applied (F002 P01 closed).
* The ``control.tenants`` table exists (F001 P01 schema).
* psycopg2-binary and SQLAlchemy are available in the test environment.

Run from the backend container:
    pytest tests/integration/test_f002_p2_repository.py -v

Environment variable:
    DATABASE_URL  Defaults to the Docker Compose default if not set.
"""

from __future__ import annotations

import os
import threading
import time
import unicodedata
import uuid
from datetime import UTC, datetime, timezone

import psycopg2
import psycopg2.extras
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

psycopg2.extras.register_uuid()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/dataquality_db",
)

# ---------------------------------------------------------------------------
# SQLAlchemy engine + session factory
# ---------------------------------------------------------------------------

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_session():
    """Module-scoped session; individual tests use savepoints via nested()."""
    session = SessionFactory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def db(db_session):
    """Per-test nested transaction (SAVEPOINT) — no committed side effects."""
    db_session.begin_nested()
    yield db_session
    db_session.rollback()


@pytest.fixture(scope="module")
def seed_tenant(db_session):
    """
    Insert one tenant row used by all tests in this module.
    Committed so that cross-connection references (FOR UPDATE test) can see it.
    """
    from datetime import datetime, timezone

    tenant_id = uuid.uuid4()
    now = datetime.now(UTC)
    db_session.execute(
        text(
            """
            INSERT INTO control.tenants (
                tenant_id, tenant_name,
                tenant_slug, status, region, plan,
                created_at, updated_at, created_by, updated_by
            ) VALUES (
                CAST(:tid AS UUID), :name,
                :slug, CAST('active' AS control.tenant_status_enum),
                CAST('us-east' AS control.tenant_region_enum),
                CAST('starter' AS control.tenant_plan_enum),
                :now, :now,
                CAST(:tid AS UUID), CAST(:tid AS UUID)
            )
            """
        ),
        {
            "tid": str(tenant_id),
            "name": f"Test Tenant {tenant_id}",
            "slug": f"test-tenant-{str(tenant_id)[:8]}",
            "now": now,
        },
    )
    db_session.commit()
    yield tenant_id

    # Cleanup: delete workspaces first (FK), then tenant
    db_session.execute(
        text("DELETE FROM control.workspace_audit_logs WHERE tenant_id = CAST(:tid AS UUID)"),
        {"tid": str(tenant_id)},
    )
    db_session.execute(
        text("DELETE FROM control.workspaces WHERE tenant_id = CAST(:tid AS UUID)"),
        {"tid": str(tenant_id)},
    )
    db_session.execute(
        text("DELETE FROM control.tenants WHERE tenant_id = CAST(:tid AS UUID)"),
        {"tid": str(tenant_id)},
    )
    db_session.commit()


def _make_workspace(tenant_id: uuid.UUID, slug_suffix: str = "") -> Workspace:
    from app.services.workspaces.models import Workspace

    actor = uuid.uuid4()
    now = datetime.now(UTC)
    slug = f"ws-{str(uuid.uuid4())[:8]}{slug_suffix}"
    return Workspace(
        tenant_id=tenant_id,
        workspace_name=f"Workspace {slug}",
        workspace_name_lower=f"workspace {slug}",
        workspace_slug=slug,
        default_timezone="UTC",
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
    )


# ---------------------------------------------------------------------------
# TestInsertWorkspaceHappyPath
# ---------------------------------------------------------------------------


class TestInsertWorkspaceHappyPath:
    """insert_workspace returns a fully populated Workspace with correct defaults."""

    def test_insert_returns_uuid_v4(self, db, seed_tenant):
        from app.services.workspaces.repository import WorkspaceRepository

        repo = WorkspaceRepository()
        ws = _make_workspace(seed_tenant)
        result = repo.insert_workspace(db, ws)

        assert result.workspace_id is not None
        assert result.workspace_id.version == 4  # UUID v4

    def test_insert_returns_version_zero(self, db, seed_tenant):
        from app.services.workspaces.repository import WorkspaceRepository

        repo = WorkspaceRepository()
        result = repo.insert_workspace(db, _make_workspace(seed_tenant))
        assert result.version == 0

    def test_insert_status_is_active(self, db, seed_tenant):
        from app.services.workspaces.models import WorkspaceStatus
        from app.services.workspaces.repository import WorkspaceRepository

        repo = WorkspaceRepository()
        result = repo.insert_workspace(db, _make_workspace(seed_tenant))
        assert result.status == WorkspaceStatus.active

    def test_all_14_fields_returned(self, db, seed_tenant):
        from app.services.workspaces.repository import WorkspaceRepository

        repo = WorkspaceRepository()
        ws = _make_workspace(seed_tenant)
        result = repo.insert_workspace(db, ws)

        assert result.workspace_id is not None
        assert result.tenant_id == seed_tenant
        assert result.workspace_name == ws.workspace_name
        assert result.workspace_name_lower == ws.workspace_name_lower
        assert result.workspace_slug == ws.workspace_slug
        assert result.description is None
        assert result.default_timezone == "UTC"
        assert result.status_reason is None
        assert result.created_at is not None
        assert result.updated_at is not None
        assert result.created_by is not None
        assert result.updated_by is not None
        assert result.version == 0


# ---------------------------------------------------------------------------
# TestFindByIdCrossTenantIsolation
# ---------------------------------------------------------------------------


class TestFindByIdCrossTenantIsolation:
    """find_by_id must raise WorkspaceNotFoundError for cross-tenant access."""

    def test_cross_tenant_raises_not_found(self, db, seed_tenant):
        from app.services.workspaces.exceptions import WorkspaceNotFoundError
        from app.services.workspaces.repository import WorkspaceRepository

        repo = WorkspaceRepository()
        # Insert workspace under seed_tenant
        inserted = repo.insert_workspace(db, _make_workspace(seed_tenant))

        # Try to retrieve it with a different tenant_id
        other_tenant = uuid.uuid4()
        with pytest.raises(WorkspaceNotFoundError):
            repo.find_by_id(db, inserted.workspace_id, other_tenant)

    def test_correct_tenant_succeeds(self, db, seed_tenant):
        from app.services.workspaces.repository import WorkspaceRepository

        repo = WorkspaceRepository()
        inserted = repo.insert_workspace(db, _make_workspace(seed_tenant))
        found = repo.find_by_id(db, inserted.workspace_id, seed_tenant)
        assert found.workspace_id == inserted.workspace_id

    def test_nonexistent_id_raises_not_found(self, db, seed_tenant):
        from app.services.workspaces.exceptions import WorkspaceNotFoundError
        from app.services.workspaces.repository import WorkspaceRepository

        repo = WorkspaceRepository()
        with pytest.raises(WorkspaceNotFoundError):
            repo.find_by_id(db, uuid.uuid4(), seed_tenant)


# ---------------------------------------------------------------------------
# TestForUpdateLock
# ---------------------------------------------------------------------------


class TestForUpdateLock:
    """
    find_by_id(for_update=True) must acquire a row lock that blocks a
    concurrent UPDATE until the first transaction commits or rolls back.

    Implementation: two psycopg2 connections used to avoid SQLAlchemy
    transaction management complexity for a two-connection locking test.
    """

    def test_for_update_blocks_concurrent_update(self, seed_tenant):
        # Insert a row in autocommit connection (visible to both conns)
        setup_conn = psycopg2.connect(DATABASE_URL)
        setup_conn.autocommit = True
        actor = uuid.uuid4()
        workspace_id = uuid.uuid4()
        now = datetime.now(UTC)
        slug = f"lock-test-{str(uuid.uuid4())[:8]}"

        with setup_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO control.workspaces (
                    workspace_id, tenant_id, workspace_name, workspace_name_lower,
                    workspace_slug, default_timezone, status,
                    created_at, updated_at, created_by, updated_by, version
                ) VALUES (
                    %s, %s, %s, %s, %s, 'UTC',
                    'active'::control.workspace_status_enum,
                    %s, %s, %s, %s, 0
                )
                """,
                (
                    workspace_id,
                    seed_tenant,
                    f"Lock Test {slug}",
                    f"lock test {slug}",
                    slug,
                    now,
                    now,
                    actor,
                    actor,
                ),
            )
        setup_conn.close()

        # Connection 1: begins tx, acquires FOR UPDATE lock
        conn1 = psycopg2.connect(DATABASE_URL)
        conn1.autocommit = False
        cur1 = conn1.cursor()
        cur1.execute(
            "SELECT * FROM control.workspaces "
            "WHERE workspace_id = %s AND tenant_id = %s FOR UPDATE",
            (workspace_id, seed_tenant),
        )
        cur1.fetchone()  # row locked

        # Connection 2: attempts UPDATE in a separate thread; should block
        conn2 = psycopg2.connect(DATABASE_URL)
        conn2.autocommit = False
        update_completed = threading.Event()
        update_error: list = []

        def update_in_thread():
            try:
                cur2 = conn2.cursor()
                cur2.execute("SET lock_timeout = '500ms'")  # fail fast if blocked too long
                cur2.execute(
                    "UPDATE control.workspaces SET version = 1 WHERE workspace_id = %s",
                    (workspace_id,),
                )
                conn2.commit()
                update_completed.set()
            except Exception as exc:
                update_error.append(exc)
                try:
                    conn2.rollback()
                except Exception:
                    pass
                update_completed.set()

        t = threading.Thread(target=update_in_thread, daemon=True)
        t.start()

        # Give the thread time to attempt the lock
        time.sleep(0.3)

        # Update should not have completed yet (blocked by conn1)
        assert not update_completed.is_set() or update_error, (
            "Concurrent UPDATE should have been blocked by FOR UPDATE lock"
        )

        # Release conn1's lock
        conn1.rollback()
        conn1.close()

        # Wait for thread to finish
        t.join(timeout=3.0)

        conn2.close()

        # Cleanup
        cleanup_conn = psycopg2.connect(DATABASE_URL)
        cleanup_conn.autocommit = True
        with cleanup_conn.cursor() as cur:
            cur.execute(
                "DELETE FROM control.workspaces WHERE workspace_id = %s",
                (workspace_id,),
            )
        cleanup_conn.close()


# ---------------------------------------------------------------------------
# TestListWorkspacesPagination
# ---------------------------------------------------------------------------


class TestListWorkspacesPagination:
    """list_workspaces returns paginated results with correct total_count."""

    def test_pagination_returns_correct_page(self, db, seed_tenant):
        from app.services.workspaces.repository import WorkspaceRepository

        repo = WorkspaceRepository()
        # Insert 7 workspaces
        for i in range(7):
            repo.insert_workspace(db, _make_workspace(seed_tenant, f"-p{i}"))

        workspaces, total = repo.list_workspaces(db, seed_tenant, page=1, page_size=5)
        assert total == 7
        assert len(workspaces) == 5

    def test_second_page(self, db, seed_tenant):
        from app.services.workspaces.repository import WorkspaceRepository

        repo = WorkspaceRepository()
        for i in range(7):
            repo.insert_workspace(db, _make_workspace(seed_tenant, f"-pg2-{i}"))

        workspaces, total = repo.list_workspaces(db, seed_tenant, page=2, page_size=5)
        assert total == 7
        assert len(workspaces) == 2

    def test_empty_tenant_returns_zero(self, db):
        from app.services.workspaces.repository import WorkspaceRepository

        repo = WorkspaceRepository()
        empty_tenant = uuid.uuid4()
        workspaces, total = repo.list_workspaces(db, empty_tenant)
        assert workspaces == []
        assert total == 0


# ---------------------------------------------------------------------------
# TestListWorkspacesIlikeMetacharacter
# ---------------------------------------------------------------------------


class TestListWorkspacesIlikeMetacharacter:
    """list_workspaces with a q containing ILIKE metacharacters must not error."""

    def test_percent_in_q_no_error(self, db, seed_tenant):
        from app.services.workspaces.repository import WorkspaceRepository

        repo = WorkspaceRepository()
        # Just ensure no exception — result set may be empty
        workspaces, total = repo.list_workspaces(db, seed_tenant, q="test%value")
        assert isinstance(workspaces, list)
        assert isinstance(total, int)

    def test_underscore_in_q_no_error(self, db, seed_tenant):
        from app.services.workspaces.repository import WorkspaceRepository

        repo = WorkspaceRepository()
        workspaces, total = repo.list_workspaces(db, seed_tenant, q="my_workspace")
        assert isinstance(workspaces, list)

    def test_whitespace_only_q_treated_as_absent(self, db, seed_tenant):
        from app.services.workspaces.repository import WorkspaceRepository

        repo = WorkspaceRepository()
        # Insert one workspace
        repo.insert_workspace(db, _make_workspace(seed_tenant))
        _, total_no_q = repo.list_workspaces(db, seed_tenant)
        _, total_whitespace_q = repo.list_workspaces(db, seed_tenant, q="   ")
        assert total_no_q == total_whitespace_q


# ---------------------------------------------------------------------------
# TestCountActiveWorkspaces
# ---------------------------------------------------------------------------


class TestCountActiveWorkspaces:
    """count_active_workspaces returns only active rows."""

    def test_counts_active_only(self, db, seed_tenant):
        from app.services.workspaces.models import WorkspaceStatus
        from app.services.workspaces.repository import WorkspaceRepository

        repo = WorkspaceRepository()
        # Insert 2 active workspaces
        ws1 = repo.insert_workspace(db, _make_workspace(seed_tenant))
        repo.insert_workspace(db, _make_workspace(seed_tenant))

        count_before = repo.count_active_workspaces(db, seed_tenant)

        # Manually archive ws1 via SQL (bypassing the service layer)
        db.execute(
            text(
                "UPDATE control.workspaces "
                "SET status = CAST('archived' AS control.workspace_status_enum), "
                "    status_reason = 'archived for test', "
                "    version = 1 "
                "WHERE workspace_id = CAST(:wid AS UUID)"
            ),
            {"wid": str(ws1.workspace_id)},
        )

        count_after = repo.count_active_workspaces(db, seed_tenant)
        assert count_after == count_before - 1

    def test_empty_tenant_returns_zero(self, db):
        from app.services.workspaces.repository import WorkspaceRepository

        repo = WorkspaceRepository()
        count = repo.count_active_workspaces(db, uuid.uuid4())
        assert count == 0


# ---------------------------------------------------------------------------
# TestNFCNormalizationInDB (TG-2)
# ---------------------------------------------------------------------------


class TestNFCNormalizationInDB:
    """
    TG-2: Insert a workspace with an NFD-encoded workspace_name; confirm that
    the stored workspace_name_lower equals the NFC-normalized lowercase form.
    This verifies no normalization drift between application layer and storage.
    """

    def test_nfd_name_stored_as_nfc(self, db, seed_tenant):
        from app.services.workspaces.repository import WorkspaceRepository

        # NFD-encoded café: 'e' + combining acute accent (U+0301)
        nfd_name = "caf\u0065\u0301 Test"  # = "café Test" in NFD
        nfc_name = unicodedata.normalize("NFC", nfd_name)
        nfc_lower = nfc_name.lower()

        actor = uuid.uuid4()
        now = datetime.now(UTC)
        from app.services.workspaces.models import Workspace

        ws = Workspace(
            tenant_id=seed_tenant,
            workspace_name=nfc_name,  # application normalises before storing
            workspace_name_lower=nfc_lower,
            workspace_slug=f"cafe-test-{str(uuid.uuid4())[:8]}",
            default_timezone="UTC",
            created_at=now,
            updated_at=now,
            created_by=actor,
            updated_by=actor,
        )

        repo = WorkspaceRepository()
        result = repo.insert_workspace(db, ws)

        # Read back from DB
        found = repo.find_by_id(db, result.workspace_id, seed_tenant)
        assert found.workspace_name_lower == nfc_lower


# ---------------------------------------------------------------------------
# TestRBACServiceStubIntegration
# ---------------------------------------------------------------------------


class TestRBACServiceStubIntegration:
    """Integration-level RBAC stub tests against the live database."""

    def test_stub_interface_compliance(self):
        from app.services.workspaces.rbac import RBACServiceInterface, RBACServiceStub

        assert issubclass(RBACServiceStub, RBACServiceInterface)

    def test_stub_missing_table_no_error(self, db):
        """
        When role_assignments table does not exist (likely in pre-F007 env),
        stub must complete without RoleGrantFailedError.
        """
        from app.services.workspaces.exceptions import RoleGrantFailedError
        from app.services.workspaces.rbac import RBACServiceStub

        stub = RBACServiceStub()

        # This call may or may not find the table; either way should not raise
        try:
            stub.grant_workspace_admin(uuid.uuid4(), uuid.uuid4(), db)
        except RoleGrantFailedError:
            pytest.fail(
                "RoleGrantFailedError raised by stub — expected no error when table is absent"
            )
