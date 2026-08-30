"""
F034 P01 — Unit tests: Schema and Domain Models

AC-P01-01: IssueSample.__tablename__ == "issue_record_samples"
AC-P01-02: SampleDomain defaults rows=[], masking_applied=False, sample_count=0
AC-P01-03: SampleDomain model_config has from_attributes=True
AC-P01-04: SampleDomain accepts masking_threshold=None
AC-P01-05: Import of SampleDomain succeeds
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from app.models.issue import IssueSample
from app.services.issues.issue_sample_models import SampleDomain

_ISSUE_ID = uuid.uuid4()
_WS_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# AC-P01-01: ORM tablename
# ---------------------------------------------------------------------------
class TestIssueSampleORM:
    def test_tablename(self):
        assert IssueSample.__tablename__ == "issue_record_samples"

    def test_orm_has_required_columns(self):
        cols = {c.key for c in IssueSample.__table__.columns}
        assert {
            "id",
            "issue_id",
            "workspace_id",
            "captured_at",
            "sample_count",
            "rows",
            "masking_applied",
            "masking_threshold",
        } <= cols


# ---------------------------------------------------------------------------
# AC-P01-02: SampleDomain defaults
# ---------------------------------------------------------------------------
class TestSampleDomainDefaults:
    def test_rows_default_is_empty_list(self):
        d = SampleDomain(issue_id=_ISSUE_ID, workspace_id=_WS_ID)
        assert d.rows == []

    def test_masking_applied_default_false(self):
        d = SampleDomain(issue_id=_ISSUE_ID, workspace_id=_WS_ID)
        assert d.masking_applied is False

    def test_sample_count_default_zero(self):
        d = SampleDomain(issue_id=_ISSUE_ID, workspace_id=_WS_ID)
        assert d.sample_count == 0


# ---------------------------------------------------------------------------
# AC-P01-03: from_attributes
# ---------------------------------------------------------------------------
class TestSampleDomainFromAttributes:
    def test_model_config_from_attributes(self):
        assert SampleDomain.model_config.get("from_attributes") is True


# ---------------------------------------------------------------------------
# AC-P01-04: masking_threshold nullable
# ---------------------------------------------------------------------------
class TestSampleDomainMaskingThreshold:
    def test_accepts_none(self):
        d = SampleDomain(issue_id=_ISSUE_ID, workspace_id=_WS_ID, masking_threshold=None)
        assert d.masking_threshold is None

    def test_accepts_string(self):
        d = SampleDomain(issue_id=_ISSUE_ID, workspace_id=_WS_ID, masking_threshold="confidential")
        assert d.masking_threshold == "confidential"
