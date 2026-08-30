"""
F031 P03 — Integration tests for IssueCreationService
======================================================

Exercises ``IssueCreationService.create_from_node_result()`` against a live
PostgreSQL database.  All prerequisite records are created in-transaction and
rolled back after each test to leave the database clean.

Prerequisite: Migrations 006 – 013 must be applied.

Run (inside the backend container or with DATABASE_URL pointing at the DB):
    pytest backend/tests/integration/test_f031_p03_issue_creation.py -v

Environment variable:
    DATABASE_URL  (defaults to the local Docker Compose default)
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta, timezone

import pytest
from app.models.issue import Issue
from app.services.issues.issue_creation_service import IssueCreationService
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
ACTOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")  # synthetic actor


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    """
    SQLAlchemy Session backed by a SAVEPOINT.

    Records inserted within the test are visible inside the transaction but
    rolled back at the end, leaving the database unmodified.
    """
    session = _SessionFactory()
    try:
        session.execute(text("SAVEPOINT sp_f031_p03"))
        yield session
    finally:
        session.execute(text("ROLLBACK TO SAVEPOINT sp_f031_p03"))
        try:
            session.execute(text("RELEASE SAVEPOINT sp_f031_p03"))
        except Exception:
            pass
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# Setup helpers
# ─────────────────────────────────────────────────────────────────────────────


def _insert_tenant(db: Session) -> uuid.UUID:
    """Insert a minimal control.tenants row; return tenant_id."""
    tid = uuid.uuid4()
    db.execute(
        text(
            """
            INSERT INTO control.tenants
                (tenant_id, tenant_name, tenant_slug, status, region, plan,
                 created_by, updated_by)
            VALUES
                (:tid, :name, :slug,
                 'active'::control.tenant_status_enum,
                 'eu-west'::control.tenant_region_enum,
                 'starter'::control.tenant_plan_enum,
                 :actor, :actor)
            """
        ),
        {
            "tid": str(tid),
            "name": f"Test Tenant {tid.hex[:6]}",
            "slug": f"t-{tid.hex[:8]}",
            "actor": str(ACTOR_ID),
        },
    )
    return tid


def _insert_workspace(db: Session, tenant_id: uuid.UUID) -> uuid.UUID:
    """Insert a minimal control.workspaces row; return workspace_id."""
    wid = uuid.uuid4()
    ws_name = f"Test WS {wid.hex[:6]}"
    db.execute(
        text(
            """
            INSERT INTO control.workspaces
                (workspace_id, tenant_id, workspace_name, workspace_name_lower,
                 workspace_slug, default_timezone, status, created_at, updated_at,
                 created_by, updated_by, version)
            VALUES
                (:wid, :tid, :name, LOWER(:name), :slug, 'UTC',
                 'active'::control.workspace_status_enum,
                 NOW(), NOW(), :actor, :actor, 0)
            """
        ),
        {
            "wid": str(wid),
            "tid": str(tenant_id),
            "name": ws_name,
            "slug": f"ws-{wid.hex[:8]}",
            "actor": str(ACTOR_ID),
        },
    )
    return wid


def _insert_workspace_settings(
    db: Session,
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID,
    sla_policy: dict | None = None,
) -> None:
    """Insert a control.workspace_settings row with optional sla_policy."""
    db.execute(
        text(
            """
            INSERT INTO control.workspace_settings
                (workspace_id, tenant_id, default_timezone, sla_policy, updated_at)
            VALUES
                (:wid, :tid, 'UTC', :sla, NOW())
            ON CONFLICT (workspace_id) DO NOTHING
            """
        ),
        {
            "wid": str(workspace_id),
            "tid": str(tenant_id),
            "sla": json.dumps(sla_policy) if sla_policy is not None else None,
        },
    )


def _insert_organization(db: Session) -> uuid.UUID:
    """Insert a minimal public.organizations row; return id."""
    oid = uuid.uuid4()
    db.execute(
        text(
            """
            INSERT INTO organizations (id, name, slug, status)
            VALUES (:oid, :name, :slug, 'active')
            """
        ),
        {
            "oid": str(oid),
            "name": f"Test Org {oid.hex[:6]}",
            "slug": f"org-{oid.hex[:8]}",
        },
    )
    return oid


def _insert_flow(db: Session, workspace_id: uuid.UUID, rule_id: uuid.UUID) -> uuid.UUID:
    """Insert a minimal dq_flows row; return flow_id."""
    fid = uuid.uuid4()
    flow_def = json.dumps(
        {
            "nodes": [
                {
                    "id": "node_check_001",
                    "type": "check",
                    "config": {"rule_id": str(rule_id)},
                }
            ],
            "connections": [],
        }
    )
    db.execute(
        text(
            """
            INSERT INTO dq_flows (id, name, workspace_id, flow_definition, status)
            VALUES (:fid, :name, :oid, CAST(:fdef AS JSONB), 'active')
            """
        ),
        {
            "fid": str(fid),
            "name": f"Test Flow {fid.hex[:6]}",
            "oid": str(workspace_id),
            "fdef": flow_def,
        },
    )
    return fid


def _insert_execution(db: Session, flow_id: uuid.UUID) -> uuid.UUID:
    """Insert a minimal flow_executions row with status='completed'; return id."""
    eid = uuid.uuid4()
    db.execute(
        text(
            """
            INSERT INTO flow_executions
                (id, flow_id, execution_type, status, started_at, completed_at)
            VALUES
                (:eid, :fid, 'manual', 'completed', NOW(), NOW())
            """
        ),
        {"eid": str(eid), "fid": str(flow_id)},
    )
    return eid


def _insert_node_result(
    db: Session,
    execution_id: uuid.UUID,
    *,
    node_id: str = "node_check_001",
    status: str = "failed",
    rows_scanned: int = 1000,
    rows_failed: int = 150,
    pass_rate: float = 85.0,
    completed_at: datetime | None = None,
) -> uuid.UUID:
    """Insert a flow_node_results row; return id."""
    nrid = uuid.uuid4()
    result_data = json.dumps(
        {
            "rows_scanned": rows_scanned,
            "rows_failed": rows_failed,
            "pass_rate": pass_rate,
        }
    )
    db.execute(
        text(
            """
            INSERT INTO flow_node_results
                (id, execution_id, node_id, node_type, status, result_data,
                 completed_at)
            VALUES
                (:nrid, :eid, :nid, 'check', :status,
                 CAST(:rdata AS JSONB), :cat)
            """
        ),
        {
            "nrid": str(nrid),
            "eid": str(execution_id),
            "nid": node_id,
            "status": status,
            "rdata": result_data,
            "cat": (completed_at or NOW).isoformat(),
        },
    )
    return nrid


def _insert_rule(db: Session, workspace_id: uuid.UUID, severity: str = "critical") -> uuid.UUID:
    """Insert a minimal dq_rules row; return id."""
    rid = uuid.uuid4()
    db.execute(
        text(
            """
            INSERT INTO dq_rules
                (id, name, rule_type, workspace_id, severity, status)
            VALUES
                (:rid, :name, 'threshold', :oid, :sev, 'active')
            """
        ),
        {
            "rid": str(rid),
            "name": f"Test Rule {rid.hex[:6]}",
            "oid": str(workspace_id),
            "sev": severity,
        },
    )
    return rid


def _full_setup(
    db: Session,
    *,
    sla_policy: dict | None = None,
    rule_severity: str = "critical",
    node_rows_scanned: int = 1000,
    node_rows_failed: int = 150,
    node_pass_rate: float = 85.0,
    node_completed_at: datetime | None = None,
    node_status: str = "failed",
) -> dict:
    """
    Create all prerequisite records for the IssueCreationService tests.

    Returns a dict of relevant IDs for assertion use.
    """
    tenant_id = _insert_tenant(db)
    workspace_id = _insert_workspace(db, tenant_id)
    _insert_workspace_settings(db, workspace_id, tenant_id, sla_policy=sla_policy)
    workspace_id = _insert_organization(db)
    rule_id = _insert_rule(db, workspace_id, severity=rule_severity)
    flow_id = _insert_flow(db, workspace_id, rule_id)
    exec_id = _insert_execution(db, flow_id)
    nr_id = _insert_node_result(
        db,
        exec_id,
        node_id="node_check_001",
        status=node_status,
        rows_scanned=node_rows_scanned,
        rows_failed=node_rows_failed,
        pass_rate=node_pass_rate,
        completed_at=node_completed_at,
    )
    db.flush()

    # Map workspace_id → workspace_id so the service can resolve tenant_id.
    # IssueCreationService uses flow.workspace_id as workspace_id, then calls
    # WorkspaceRepository.find_by_id_any_tenant(db, workspace_id) which queries
    # control.workspaces WHERE workspace_id = :workspace_id.
    # We must make flow.workspace_id == control.workspaces.workspace_id.
    db.execute(
        text("UPDATE dq_flows SET workspace_id = :wid WHERE id = :fid"),
        {"wid": str(workspace_id), "fid": str(flow_id)},
    )
    db.flush()

    return {
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "flow_id": flow_id,
        "execution_id": exec_id,
        "node_result_id": nr_id,
        "rule_id": rule_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# IT-001: End-to-end — failed node creates Issue with correct field values
# ─────────────────────────────────────────────────────────────────────────────


class TestIssueCreatedFromFailedNode:
    def test_end_to_end_issue_creation(self, db):
        """IT-001: failed FlowNodeResult → Issue row with correct fields."""
        ids = _full_setup(
            db,
            sla_policy={
                "critical_hours": 4,
                "major_hours": 24,
                "minor_hours": 72,
                "informational_hours": None,
            },
            rule_severity="critical",
            node_rows_scanned=1000,
            node_rows_failed=150,
            node_pass_rate=85.0,
            node_completed_at=NOW,
        )

        svc = IssueCreationService()
        result = svc.create_from_node_result(db, ids["node_result_id"], ids["execution_id"])

        assert result is not None, "Service must return a persisted IssueDomain"
        db.commit()

        issue = db.query(Issue).filter(Issue.id == result.id).first()
        assert issue is not None, "Issue must exist in the database after commit"
        assert issue.workspace_id == ids["workspace_id"]
        assert issue.failure_count == 150
        assert "150 of 1000 rows failed" in issue.impact_summary
        assert "85.0% pass rate" in issue.impact_summary
        assert issue.severity == "critical"
        assert issue.status == "open"
        assert issue.opened_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# IT-002: Two failing nodes → two Issue records
# ─────────────────────────────────────────────────────────────────────────────


class TestTwoFailingNodesProduceTwoIssues:
    def test_two_failing_nodes_produce_two_issues(self, db):
        """IT-002: Two failing FlowNodeResults → two distinct Issue records."""
        ids = _full_setup(db, rule_severity="major")

        # Insert a second failing node result for the same execution
        nr_id_2 = _insert_node_result(
            db,
            ids["execution_id"],
            node_id="node_check_002",
            status="failed",
        )
        # Give the second node a configured rule_id in the flow definition
        # by appending a second node to the flow definition
        db.execute(
            text(
                """
                UPDATE dq_flows
                SET flow_definition = jsonb_set(
                    flow_definition,
                    '{nodes}',
                    flow_definition->'nodes' || :extra_node::jsonb
                )
                WHERE id = :fid
                """
            ),
            {
                "extra_node": json.dumps(
                    {
                        "id": "node_check_002",
                        "type": "check",
                        "config": {"rule_id": str(ids["rule_id"])},
                    }
                ),
                "fid": str(ids["flow_id"]),
            },
        )
        db.flush()

        svc = IssueCreationService()
        r1 = svc.create_from_node_result(db, ids["node_result_id"], ids["execution_id"])
        if r1:
            db.commit()
        r2 = svc.create_from_node_result(db, nr_id_2, ids["execution_id"])
        if r2:
            db.commit()

        assert r1 is not None, "First issue must be created"
        assert r2 is not None, "Second issue must be created"
        assert r1.id != r2.id, "Issues must have distinct IDs"
        assert r1.flow_node_result_id != r2.flow_node_result_id, (
            "Issues must have distinct flow_node_result_id values"
        )

        count = db.query(Issue).filter(Issue.flow_execution_id == ids["execution_id"]).count()
        assert count == 2


# ─────────────────────────────────────────────────────────────────────────────
# IT-003: DB failure during issue creation does NOT change FlowExecution.status
# ─────────────────────────────────────────────────────────────────────────────


class TestDBFailureDoesNotMutateExecutionStatus:
    def test_repo_failure_leaves_execution_status_unchanged(self, db):
        """IT-003: DB failure in the repo does not mutate FlowExecution.status."""
        from unittest.mock import MagicMock, patch

        from app.models.flow import FlowExecution

        ids = _full_setup(db)

        # Confirm the execution has 'completed' status
        execution = db.query(FlowExecution).filter(FlowExecution.id == ids["execution_id"]).first()
        assert execution is not None
        original_status = execution.status

        # Force the repository insert to raise
        failing_repo = MagicMock()
        failing_repo.insert.side_effect = Exception("simulated DB failure")
        svc = IssueCreationService(repository=failing_repo)

        result = svc.create_from_node_result(db, ids["node_result_id"], ids["execution_id"])

        assert result is None, "Service must return None on DB failure"
        # Re-load execution to confirm its status was untouched
        db.refresh(execution)
        assert execution.status == original_status, (
            "FlowExecution.status must not change when issue creation fails"
        )


# ─────────────────────────────────────────────────────────────────────────────
# IT-004: SLA due_at is computed correctly from workspace settings
# ─────────────────────────────────────────────────────────────────────────────


class TestSLADueAtApplied:
    def test_due_at_is_opened_at_plus_sla_hours(self, db):
        """IT-004: critical severity + critical_hours=4 → due_at = opened_at + 4h."""
        completed_at = datetime(2025, 5, 1, 12, 0, 0, tzinfo=UTC)
        ids = _full_setup(
            db,
            sla_policy={
                "critical_hours": 4,
                "major_hours": 24,
                "minor_hours": 72,
                "informational_hours": None,
            },
            rule_severity="critical",
            node_completed_at=completed_at,
        )

        svc = IssueCreationService()
        result = svc.create_from_node_result(db, ids["node_result_id"], ids["execution_id"])

        assert result is not None
        db.commit()

        issue = db.query(Issue).filter(Issue.id == result.id).first()
        assert issue.due_at is not None

        expected_due = completed_at + timedelta(hours=4)
        # Allow a small tolerance for timezone representation differences
        assert abs((issue.due_at.replace(tzinfo=UTC) - expected_due).total_seconds()) < 60


# ─────────────────────────────────────────────────────────────────────────────
# IT-005: Issues created for workspace A are not visible via workspace B query
# ─────────────────────────────────────────────────────────────────────────────


class TestCrossWorkspaceIsolation:
    def test_issues_not_visible_in_wrong_workspace(self, db):
        """IT-005: Issue for workspace A not returned when querying workspace B."""
        ids_a = _full_setup(db, rule_severity="minor")

        # Create an independent second workspace
        tenant_id_b = _insert_tenant(db)
        workspace_id_b = _insert_workspace(db, tenant_id_b)
        db.flush()

        svc = IssueCreationService()
        result = svc.create_from_node_result(db, ids_a["node_result_id"], ids_a["execution_id"])
        assert result is not None
        db.commit()

        repo = IssueRepository()
        items_a, total_a = repo.list_by_workspace(db, ids_a["workspace_id"])
        items_b, total_b = repo.list_by_workspace(db, workspace_id_b)

        assert total_a >= 1, "Issue must appear in workspace A"
        assert total_b == 0, "Issue must NOT appear in workspace B (cross-workspace leak)"
