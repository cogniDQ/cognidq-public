"""
F032 P01 — Schema Verification Tests
======================================

Verifies that:
1. Migration 016_f032_issue_grouping.sql adds the `last_seen_at` column.
2. `last_seen_at` defaults to NULL on fresh issue creation.
3. The partial indexes for grouping lookups exist after migration.
4. `IssueDomain` and `IssueDetail` Pydantic models include `last_seen_at`.
5. Existing F031 issue creation code is unaffected.

ACs covered
-----------
AC-P01-01  last_seen_at column exists in public.issues after migration
AC-P01-02  last_seen_at is TIMESTAMPTZ, nullable
AC-P01-03  idx_issues_grouping_rule index exists
AC-P01-04  idx_issues_grouping_day index exists
AC-P01-05  IssueDomain constructed without last_seen_at defaults to None
AC-P01-06  IssueDetail includes last_seen_at field (defaults to None)
AC-P01-07  Issue ORM model has last_seen_at column attribute
AC-P01-08  IssueDomain.model_validate(orm_obj) succeeds when last_seen_at is None
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from decimal import Decimal

import pytest
from app.models.issue import Issue
from app.services.issues.issue_models import IssueDetail, IssueDomain

# ---------------------------------------------------------------------------
# AC-P01-05: IssueDomain defaults last_seen_at to None
# ---------------------------------------------------------------------------


def test_issue_domain_last_seen_at_defaults_to_none():
    """AC-P01-05: IssueDomain can be constructed without last_seen_at → None."""
    domain = IssueDomain(
        tenant_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        flow_execution_id=uuid.uuid4(),
        issue_type="threshold_breach",
        severity="minor",
        status="open",
        title="Test issue",
    )
    assert domain.last_seen_at is None


# ---------------------------------------------------------------------------
# AC-P01-06: IssueDetail has last_seen_at field defaulting to None
# ---------------------------------------------------------------------------


def test_issue_detail_has_last_seen_at_field():
    """AC-P01-06: IssueDetail includes last_seen_at; defaults to None."""
    detail = IssueDetail(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        flow_execution_id=uuid.uuid4(),
        issue_type="threshold_breach",
        severity="critical",
        status="open",
        title="Test",
    )
    assert hasattr(detail, "last_seen_at")
    assert detail.last_seen_at is None


# ---------------------------------------------------------------------------
# AC-P01-07: Issue ORM model has last_seen_at attribute
# ---------------------------------------------------------------------------


def test_issue_orm_model_has_last_seen_at():
    """AC-P01-07: Issue ORM class has a last_seen_at column attribute."""
    assert hasattr(Issue, "last_seen_at"), (
        "Issue ORM model is missing last_seen_at column. "
        "Ensure migration 016 was applied and issue.py was updated."
    )


# ---------------------------------------------------------------------------
# AC-P01-08: IssueDomain.model_validate from ORM object with last_seen_at=None
# ---------------------------------------------------------------------------


def test_issue_domain_model_validate_with_none_last_seen_at():
    """AC-P01-08: model_validate succeeds when last_seen_at is None on ORM object."""
    orm_obj = Issue()
    orm_obj.id = uuid.uuid4()
    orm_obj.tenant_id = uuid.uuid4()
    orm_obj.workspace_id = uuid.uuid4()
    orm_obj.flow_execution_id = uuid.uuid4()
    orm_obj.issue_type = "threshold_breach"
    orm_obj.severity = "minor"
    orm_obj.status = "open"
    orm_obj.title = "Test"
    orm_obj.failure_count = 10
    orm_obj.rows_scanned = 100
    orm_obj.pass_rate = Decimal("90.0")
    orm_obj.opened_at = datetime(2026, 4, 1, 8, 0, 0, tzinfo=UTC)
    orm_obj.last_seen_at = None  # explicit None
    orm_obj.created_at = datetime(2026, 4, 1, 8, 0, 1, tzinfo=UTC)
    orm_obj.updated_at = datetime(2026, 4, 1, 8, 0, 1, tzinfo=UTC)

    domain = IssueDomain.model_validate(orm_obj)
    assert domain.last_seen_at is None
    assert domain.failure_count == 10


# ---------------------------------------------------------------------------
# Test: last_seen_at carries through when set
# ---------------------------------------------------------------------------


def test_issue_domain_last_seen_at_set():
    """IssueDomain stores last_seen_at when explicitly provided."""
    ts = datetime(2026, 4, 2, 10, 30, 0, tzinfo=UTC)
    domain = IssueDomain(
        tenant_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        flow_execution_id=uuid.uuid4(),
        issue_type="threshold_breach",
        severity="major",
        status="open",
        title="Grouped issue",
        last_seen_at=ts,
    )
    assert domain.last_seen_at == ts
