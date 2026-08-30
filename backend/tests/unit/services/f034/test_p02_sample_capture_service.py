"""
F034 P02 — Unit tests: SampleCaptureService

AC-P02-01: no violations → returns None, repo not called
AC-P02-02: 5 violations → sample_count == 5
AC-P02-03: 80 violations → sample_count == 50 (capped)
AC-P02-04: column sensitivity=confidential → value '[MASKED]'
AC-P02-05: column sensitivity=public → value unchanged
AC-P02-06: masking_applied=True when ≥1 field masked
AC-P02-07: masking_applied=False when no fields masked
AC-P02-08: masking_threshold='confidential' when masking applied
AC-P02-09: dataset_id=None → no masking, masking_applied=False
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from app.services.issues.issue_sample_models import SampleDomain
from app.services.issues.sample_capture_service import SampleCaptureService

_ISSUE_ID = uuid.uuid4()
_WS_ID = uuid.uuid4()
_DS_ID = uuid.uuid4()


def _make_violation(**kwargs) -> dict:
    base = {"row_id": "1", "customer_id": 1001, "email": "a@b.com", "amount": 99.0}
    base.update(kwargs)
    return base


def _make_service(repo=None) -> SampleCaptureService:
    if repo is None:
        repo = MagicMock()
        repo.insert.side_effect = lambda db, domain: domain
    return SampleCaptureService(repository=repo)


def _db_returning(rows):
    """Build a mock db with execute().fetchall() returning rows."""
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = rows
    return db


# ---------------------------------------------------------------------------
# AC-P02-01: no violations → None, repo not called
# ---------------------------------------------------------------------------
class TestNoViolations:
    def test_returns_none(self):
        repo = MagicMock()
        svc = _make_service(repo)
        result = svc.capture_for_issue(
            db=MagicMock(),
            issue_id=_ISSUE_ID,
            workspace_id=_WS_ID,
            dataset_id=_DS_ID,
            node_result_result_data={},
        )
        assert result is None
        repo.insert.assert_not_called()

    def test_empty_list_returns_none(self):
        repo = MagicMock()
        svc = _make_service(repo)
        result = svc.capture_for_issue(
            db=MagicMock(),
            issue_id=_ISSUE_ID,
            workspace_id=_WS_ID,
            dataset_id=None,
            node_result_result_data={"violations": []},
        )
        assert result is None
        repo.insert.assert_not_called()


# ---------------------------------------------------------------------------
# AC-P02-02: 5 violations → sample_count == 5
# ---------------------------------------------------------------------------
class TestFiveViolations:
    def test_sample_count_equals_input(self):
        violations = [_make_violation(row_id=str(i)) for i in range(5)]
        db = _db_returning([])  # no field sensitivity rows
        repo = MagicMock()
        repo.insert.side_effect = lambda _db, domain: domain
        svc = _make_service(repo)
        result = svc.capture_for_issue(
            db=db,
            issue_id=_ISSUE_ID,
            workspace_id=_WS_ID,
            dataset_id=_DS_ID,
            node_result_result_data={"violations": violations},
        )
        assert result is not None
        assert result.sample_count == 5
        repo.insert.assert_called_once()


# ---------------------------------------------------------------------------
# AC-P02-03: 80 violations → capped at 50
# ---------------------------------------------------------------------------
class TestViolationCap:
    def test_capped_at_50(self):
        violations = [_make_violation(row_id=str(i)) for i in range(80)]
        db = _db_returning([])
        repo = MagicMock()
        repo.insert.side_effect = lambda _db, domain: domain
        svc = _make_service(repo)
        result = svc.capture_for_issue(
            db=db,
            issue_id=_ISSUE_ID,
            workspace_id=_WS_ID,
            dataset_id=_DS_ID,
            node_result_result_data={"violations": violations},
        )
        assert result.sample_count == 50
        inserted_domain = repo.insert.call_args.args[1]
        assert len(inserted_domain.rows) == 50


# ---------------------------------------------------------------------------
# AC-P02-04: confidential column masked
# ---------------------------------------------------------------------------
class TestMaskingConfidential:
    def test_confidential_value_replaced(self):
        violations = [{"customer_id": 1001, "email": "a@b.com"}]
        # Simulate field rows: email=confidential
        field_row = MagicMock()
        field_row.field_name = "email"
        field_row.sensitivity_classification = "confidential"
        db = _db_returning([field_row])
        repo = MagicMock()
        repo.insert.side_effect = lambda _db, domain: domain
        svc = _make_service(repo)
        svc.capture_for_issue(
            db=db,
            issue_id=_ISSUE_ID,
            workspace_id=_WS_ID,
            dataset_id=_DS_ID,
            node_result_result_data={"violations": violations},
        )
        _, kw = repo.insert.call_args
        assert repo.insert.call_args.args[1].rows[0]["email"] == "[MASKED]"


# ---------------------------------------------------------------------------
# AC-P02-05: public column unchanged
# ---------------------------------------------------------------------------
class TestMaskingPublic:
    def test_public_value_unchanged(self):
        violations = [{"customer_id": 1001, "email": "a@b.com"}]
        pub_row = MagicMock()
        pub_row.field_name = "customer_id"
        pub_row.sensitivity_classification = "public"
        db = _db_returning([pub_row])
        repo = MagicMock()
        repo.insert.side_effect = lambda _db, domain: domain
        svc = _make_service(repo)
        svc.capture_for_issue(
            db=db,
            issue_id=_ISSUE_ID,
            workspace_id=_WS_ID,
            dataset_id=_DS_ID,
            node_result_result_data={"violations": violations},
        )
        _, kw = repo.insert.call_args
        assert repo.insert.call_args.args[1].rows[0]["customer_id"] == 1001


# ---------------------------------------------------------------------------
# AC-P02-06: masking_applied=True when ≥1 masked
# ---------------------------------------------------------------------------
class TestMaskingAppliedFlag:
    def test_true_when_masked(self):
        violations = [{"email": "x@y.com"}]
        field_row = MagicMock()
        field_row.field_name = "email"
        field_row.sensitivity_classification = "restricted"
        db = _db_returning([field_row])
        repo = MagicMock()
        repo.insert.side_effect = lambda _db, domain: domain
        svc = _make_service(repo)
        svc.capture_for_issue(
            db=db,
            issue_id=_ISSUE_ID,
            workspace_id=_WS_ID,
            dataset_id=_DS_ID,
            node_result_result_data={"violations": violations},
        )
        _, kw = repo.insert.call_args
        assert repo.insert.call_args.args[1].masking_applied is True

    def test_false_when_no_sensitive_fields(self):
        violations = [{"amount": 99.0}]
        field_row = MagicMock()
        field_row.field_name = "amount"
        field_row.sensitivity_classification = "public"
        db = _db_returning([field_row])
        repo = MagicMock()
        repo.insert.side_effect = lambda _db, domain: domain
        svc = _make_service(repo)
        svc.capture_for_issue(
            db=db,
            issue_id=_ISSUE_ID,
            workspace_id=_WS_ID,
            dataset_id=_DS_ID,
            node_result_result_data={"violations": violations},
        )
        _, kw = repo.insert.call_args
        assert repo.insert.call_args.args[1].masking_applied is False


# ---------------------------------------------------------------------------
# AC-P02-08: masking_threshold stored as 'confidential' when masking applied
# ---------------------------------------------------------------------------
class TestMaskingThreshold:
    def test_threshold_stored_when_masking(self):
        violations = [{"email": "x@y.com"}]
        field_row = MagicMock()
        field_row.field_name = "email"
        field_row.sensitivity_classification = "confidential"
        db = _db_returning([field_row])
        repo = MagicMock()
        repo.insert.side_effect = lambda _db, domain: domain
        svc = _make_service(repo)
        svc.capture_for_issue(
            db=db,
            issue_id=_ISSUE_ID,
            workspace_id=_WS_ID,
            dataset_id=_DS_ID,
            node_result_result_data={"violations": violations},
        )
        _, kw = repo.insert.call_args
        assert repo.insert.call_args.args[1].masking_threshold == "confidential"

    def test_threshold_none_when_no_masking(self):
        violations = [{"amount": 1.0}]
        db = _db_returning([])  # no fields → no masking
        repo = MagicMock()
        repo.insert.side_effect = lambda _db, domain: domain
        svc = _make_service(repo)
        svc.capture_for_issue(
            db=db,
            issue_id=_ISSUE_ID,
            workspace_id=_WS_ID,
            dataset_id=_DS_ID,
            node_result_result_data={"violations": violations},
        )
        _, kw = repo.insert.call_args
        assert repo.insert.call_args.args[1].masking_threshold is None


# ---------------------------------------------------------------------------
# AC-P02-09: dataset_id=None → no masking
# ---------------------------------------------------------------------------
class TestNoDatasetId:
    def test_no_masking_when_dataset_id_none(self):
        violations = [{"email": "a@b.com", "amount": 5.0}]
        repo = MagicMock()
        repo.insert.side_effect = lambda _db, domain: domain
        svc = _make_service(repo)
        svc.capture_for_issue(
            db=MagicMock(),
            issue_id=_ISSUE_ID,
            workspace_id=_WS_ID,
            dataset_id=None,
            node_result_result_data={"violations": violations},
        )
        _, kw = repo.insert.call_args
        assert repo.insert.call_args.args[1].masking_applied is False
        assert repo.insert.call_args.args[1].rows[0]["email"] == "a@b.com"
