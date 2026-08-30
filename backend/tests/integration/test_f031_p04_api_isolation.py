"""
F031 P04 — Integration test: cross-workspace isolation via API.

Verifies that the issues list endpoint scopes results to the correct
workspace_id and that issues from workspace A are not visible in workspace B.

Prerequisite: Migrations 006–013 must be applied.

Run:
    pytest backend/tests/integration/test_f031_p04_api_isolation.py -v

Environment variable:
    DATABASE_URL  (defaults to the local Docker Compose default)
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timezone

import pytest
from app.services.issues.issue_repository import IssueRepository
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/dataquality_db",
)

_engine = create_engine(DATABASE_URL)
_SessionFactory = sessionmaker(bind=_engine, autocommit=False, autoflush=False)

NOW = datetime(2025, 6, 1, 9, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db():
    session = _SessionFactory()
    try:
        session.execute(text("SAVEPOINT sp_f031_p04"))
        yield session
    finally:
        session.execute(text("ROLLBACK TO SAVEPOINT sp_f031_p04"))
        session.close()


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _insert_tenant(db: Session, tid: uuid.UUID) -> None:
    db.execute(
        text("""
        INSERT INTO control.tenants (id, tenant_name, status)
        VALUES (:id, :name, 'active')
        ON CONFLICT (id) DO NOTHING
    """),
        {"id": str(tid), "name": f"tenant-{tid.hex[:8]}"},
    )
    db.flush()


def _insert_workspace(db: Session, wid: uuid.UUID, tid: uuid.UUID) -> None:
    db.execute(
        text("""
        INSERT INTO control.workspaces (id, workspace_name, workspace_slug, tenant_id, status)
        VALUES (:id, :name, :slug, :tid, 'active')
        ON CONFLICT (id) DO NOTHING
    """),
        {"id": str(wid), "name": f"ws-{wid.hex[:8]}", "slug": f"ws-{wid.hex[:8]}", "tid": str(tid)},
    )
    db.flush()


def _insert_org(db: Session, oid: uuid.UUID) -> None:
    db.execute(
        text("""
        INSERT INTO public.organizations (id, name)
        VALUES (:id, :name)
        ON CONFLICT (id) DO NOTHING
    """),
        {"id": str(oid), "name": f"org-{oid.hex[:8]}"},
    )
    db.flush()


def _insert_flow(db: Session, fid: uuid.UUID, oid: uuid.UUID) -> None:
    db.execute(
        text("""
        INSERT INTO public.dq_flows (id, name, workspace_id, flow_definition, status)
        VALUES (:id, :name, :oid, :fd, 'active')
        ON CONFLICT (id) DO NOTHING
    """),
        {
            "id": str(fid),
            "name": f"flow-{fid.hex[:8]}",
            "oid": str(oid),
            "fd": json.dumps({"nodes": [], "connections": []}),
        },
    )
    db.flush()


def _insert_execution(db: Session, eid: uuid.UUID, fid: uuid.UUID) -> None:
    db.execute(
        text("""
        INSERT INTO public.flow_executions (id, flow_id, status, started_at)
        VALUES (:id, :fid, 'completed', :now)
        ON CONFLICT (id) DO NOTHING
    """),
        {"id": str(eid), "fid": str(fid), "now": NOW},
    )
    db.flush()


def _insert_issue_row(
    db: Session,
    issue_id: uuid.UUID,
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID,
    exec_id: uuid.UUID,
) -> None:
    db.execute(
        text("""
        INSERT INTO public.issues (
            id, workspace_id, tenant_id, flow_execution_id,
            issue_type, severity, status, title, failure_count,
            impact_summary, opened_at
        ) VALUES (
            :id, :wid, :tid, :eid,
            'threshold_breach', 'critical', 'open', 'Test issue', 10,
            '10 of 100 rows failed (90.0% pass rate)', :now
        )
    """),
        {
            "id": str(issue_id),
            "wid": str(workspace_id),
            "tid": str(tenant_id),
            "eid": str(exec_id),
            "now": NOW,
        },
    )
    db.flush()


# ---------------------------------------------------------------------------
# IT: Cross-workspace isolation at repository level
# ---------------------------------------------------------------------------


class TestCrossWorkspaceIsolation:
    """
    Issues created in workspace A must not appear in list_by_workspace
    queries scoped to workspace B.
    """

    def test_issues_not_visible_in_other_workspace(self, db):
        tid = uuid.uuid4()
        ws_a = uuid.uuid4()
        ws_b = uuid.uuid4()
        org_a = ws_a  # organisation == workspace pattern
        org_b = ws_b
        flow_a = uuid.uuid4()
        flow_b = uuid.uuid4()
        exec_a = uuid.uuid4()
        exec_b = uuid.uuid4()

        # Setup: two workspaces in the same tenant
        _insert_tenant(db, tid)
        _insert_workspace(db, ws_a, tid)
        _insert_workspace(db, ws_b, tid)
        _insert_org(db, org_a)
        _insert_org(db, org_b)
        _insert_flow(db, flow_a, org_a)
        _insert_flow(db, flow_b, org_b)
        _insert_execution(db, exec_a, flow_a)
        _insert_execution(db, exec_b, flow_b)

        # Insert 2 issues in WS-A, 1 in WS-B
        issue_a1 = uuid.uuid4()
        issue_a2 = uuid.uuid4()
        issue_b1 = uuid.uuid4()
        _insert_issue_row(db, issue_a1, ws_a, tid, exec_a)
        _insert_issue_row(db, issue_a2, ws_a, tid, exec_a)
        _insert_issue_row(db, issue_b1, ws_b, tid, exec_b)

        repo = IssueRepository()

        # WS-A should see 2
        items_a, total_a = repo.list_by_workspace(db, ws_a)
        assert total_a == 2
        ids_a = {i.id for i in items_a}
        assert issue_a1 in ids_a
        assert issue_a2 in ids_a
        assert issue_b1 not in ids_a

        # WS-B should see 1
        items_b, total_b = repo.list_by_workspace(db, ws_b)
        assert total_b == 1
        assert items_b[0].id == issue_b1

        # Detail cross-check: WS-B issue not accessible from WS-A
        cross = repo.get_by_id_and_workspace(db, issue_b1, ws_a)
        assert cross is None
