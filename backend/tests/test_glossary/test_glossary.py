"""
Tests for F109 — Business Glossary Management
Covers schemas, service CRUD, CSV import/export, and API endpoints.
"""

import csv
import io
import json
import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from app.schemas.glossary import (
    GlossaryImportResult,
    GlossaryListResponse,
    GlossarySearchRequest,
    GlossaryTermCreate,
    GlossaryTermResponse,
    GlossaryTermUpdate,
)
from app.services.glossary.service import GlossaryService

WORKSPACE_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()
TERM_ID = uuid.uuid4()
NOW = datetime.now(UTC)


# ============================================================
# Schema Validation Tests (P01)
# ============================================================


class TestGlossarySchemas:
    """Tests for glossary Pydantic schemas."""

    def test_create_term_minimal(self):
        t = GlossaryTermCreate(business_name="Revenue")
        assert t.business_name == "Revenue"
        assert t.technical_name is None
        assert t.data_type is None
        assert t.is_mandatory is False
        assert t.synonyms == []

    def test_create_term_full(self):
        t = GlossaryTermCreate(
            business_name="Employee Status",
            technical_name="emp_status",
            definition="Current employment status",
            synonyms=["status", "emp_state"],
            domain="HR",
            data_type="string",
            owner="HR Dept",
            is_mandatory=True,
            allowed_values=["ACTIVE", "INACTIVE"],
        )
        assert t.business_name == "Employee Status"
        assert t.technical_name == "emp_status"
        assert t.data_type == "string"
        assert t.is_mandatory is True
        assert len(t.allowed_values) == 2

    def test_update_term_partial(self):
        t = GlossaryTermUpdate(owner="Finance")
        assert t.owner == "Finance"
        assert t.business_name is None

    def test_response_model(self):
        t = GlossaryTermResponse(
            term_id=TERM_ID,
            workspace_id=WORKSPACE_ID,
            business_name="Revenue",
            created_at=NOW,
            updated_at=NOW,
        )
        assert t.term_id == TERM_ID
        assert t.is_mandatory is False
        assert t.allowed_values is None

    def test_list_response(self):
        resp = GlossaryListResponse(items=[], total=0)
        assert resp.total == 0
        assert resp.items == []

    def test_import_result(self):
        r = GlossaryImportResult(
            imported=5, skipped=1, errors=[{"row": 3, "reason": "missing name"}]
        )
        assert r.imported == 5
        assert r.skipped == 1
        assert len(r.errors) == 1

    def test_search_request(self):
        s = GlossarySearchRequest(query="rev", domain="Finance")
        assert s.query == "rev"


# ============================================================
# Service Tests (P02) — with mocked DB
# ============================================================


def _make_mock_row(**kwargs):
    """Create a mock DB row as an object with attribute access."""
    defaults = {
        "term_id": str(TERM_ID),
        "workspace_id": str(WORKSPACE_ID),
        "business_name": "Revenue",
        "technical_name": "total_revenue",
        "definition": "Total revenue",
        "synonyms": ["income"],
        "domain": "Finance",
        "linked_asset_ids": [],
        "source": "manual",
        "trust_level": "high",
        "data_type": "decimal",
        "owner": "Finance Dept",
        "is_mandatory": True,
        "allowed_values": ["USD", "EUR"],
        "created_at": NOW,
        "updated_at": NOW,
    }
    defaults.update(kwargs)

    class Row:
        pass

    row = Row()
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


class TestGlossaryService:
    """Tests for GlossaryService CRUD operations."""

    def _mock_db(self, rows=None, scalar_result=None):
        db = MagicMock()
        mock_result = MagicMock()
        if rows is not None:
            mock_result.fetchall.return_value = rows
            mock_result.fetchone.return_value = rows[0] if rows else None
        if scalar_result is not None:
            mock_result.scalar.return_value = scalar_result
        db.execute.return_value = mock_result
        return db

    def test_create_term(self):
        db = self._mock_db(rows=[_make_mock_row()])
        svc = GlossaryService()
        result = svc.create_term(
            db,
            WORKSPACE_ID,
            TENANT_ID,
            GlossaryTermCreate(business_name="Revenue", domain="Finance"),
        )
        assert result.business_name == "Revenue"
        assert db.execute.called
        assert db.commit.called

    def test_get_term_found(self):
        db = self._mock_db(rows=[_make_mock_row()])
        svc = GlossaryService()
        result = svc.get_term(db, WORKSPACE_ID, TERM_ID)
        assert result is not None
        assert result.term_id == TERM_ID

    def test_get_term_not_found(self):
        db = self._mock_db(rows=[])
        db.execute.return_value.fetchone.return_value = None
        svc = GlossaryService()
        result = svc.get_term(db, WORKSPACE_ID, uuid.uuid4())
        assert result is None

    def test_list_terms(self):
        db = MagicMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 2
        list_result = MagicMock()
        list_result.fetchall.return_value = [
            _make_mock_row(business_name="Revenue"),
            _make_mock_row(term_id=str(uuid.uuid4()), business_name="Cost"),
        ]
        db.execute.side_effect = [count_result, list_result]
        svc = GlossaryService()
        result = svc.list_terms(db, WORKSPACE_ID)
        assert result.total == 2
        assert len(result.items) == 2

    def test_list_terms_with_search(self):
        db = MagicMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        list_result = MagicMock()
        list_result.fetchall.return_value = [_make_mock_row()]
        db.execute.side_effect = [count_result, list_result]
        svc = GlossaryService()
        result = svc.list_terms(db, WORKSPACE_ID, search="rev")
        assert result.total == 1

    def test_list_terms_with_domain_filter(self):
        db = MagicMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        list_result = MagicMock()
        list_result.fetchall.return_value = [_make_mock_row()]
        db.execute.side_effect = [count_result, list_result]
        svc = GlossaryService()
        result = svc.list_terms(db, WORKSPACE_ID, domain="Finance")
        assert result.total == 1

    def test_update_term(self):
        db = self._mock_db(rows=[_make_mock_row(owner="Updated Dept")])
        svc = GlossaryService()
        result = svc.update_term(
            db, WORKSPACE_ID, TERM_ID, GlossaryTermUpdate(owner="Updated Dept")
        )
        assert result is not None
        assert db.commit.called

    def test_delete_term(self):
        db = MagicMock()
        db.execute.return_value.rowcount = 1
        svc = GlossaryService()
        result = svc.delete_term(db, WORKSPACE_ID, TERM_ID)
        assert result is True
        assert db.commit.called

    def test_delete_term_not_found(self):
        db = MagicMock()
        db.execute.return_value.rowcount = 0
        svc = GlossaryService()
        result = svc.delete_term(db, WORKSPACE_ID, TERM_ID)
        assert result is False

    def test_export_csv(self):
        # export_csv calls list_terms internally which does 2 DB calls
        db = MagicMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        list_result = MagicMock()
        list_result.fetchall.return_value = [_make_mock_row()]
        db.execute.side_effect = [count_result, list_result]
        svc = GlossaryService()
        csv_str = svc.export_csv(db, WORKSPACE_ID)
        assert "Revenue" in csv_str
        assert "total_revenue" in csv_str
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        assert len(rows) == 2  # header + 1 data row
        assert rows[0][0] == "Business Term"

    def test_import_csv(self):
        csv_content = "business_name,technical_name,domain,definition\nRevenue,total_rev,Finance,Total revenue\nCost,total_cost,Finance,Total cost"
        db = MagicMock()
        # For each row: 1 SELECT (existing check) → fetchone returns None → create_term → fetchone returns row → commit
        select_result_none = MagicMock()
        select_result_none.fetchone.return_value = None
        insert_result = MagicMock()
        insert_result.fetchone.return_value = _make_mock_row()
        # 2 rows: each row does SELECT (none) + INSERT
        db.execute.side_effect = [
            select_result_none,
            insert_result,
            select_result_none,
            insert_result,
        ]
        svc = GlossaryService()
        result = svc.import_csv(db, WORKSPACE_ID, TENANT_ID, csv_content)
        assert result.imported == 2
        assert result.skipped == 0

    def test_import_csv_missing_name(self):
        csv_content = "business_name,technical_name\n,col1\nValid,col2"
        db = MagicMock()
        # Row 1 skipped (no name), Row 2: SELECT (none) + INSERT
        select_result_none = MagicMock()
        select_result_none.fetchone.return_value = None
        insert_result = MagicMock()
        insert_result.fetchone.return_value = _make_mock_row(business_name="Valid")
        db.execute.side_effect = [select_result_none, insert_result]
        svc = GlossaryService()
        result = svc.import_csv(db, WORKSPACE_ID, TENANT_ID, csv_content)
        assert result.imported == 1
        assert result.skipped == 1


# ============================================================
# Signal Enhancement Tests (F110)
# ============================================================


class TestGlossarySignalEnhancement:
    """Tests for enhanced glossary match scoring."""

    def test_exact_match_score(self):
        from app.schemas.metadata_search import MetadataAsset
        from app.services.resolution.signals import score_glossary_match

        candidate = MetadataAsset(
            asset_id=uuid.uuid4(),
            asset_type="field",
            workspace_id=WORKSPACE_ID,
            name="revenue",
            source_table="datasets",
            source_id=uuid.uuid4(),
        )
        term = MagicMock()
        term.business_name = "Revenue"
        term.synonyms = []
        term.linked_asset_ids = [str(candidate.asset_id)]

        score = score_glossary_match("Revenue", candidate, {"terms": [term]})
        assert score == 1.0

    def test_synonym_match_score(self):
        from app.schemas.metadata_search import MetadataAsset
        from app.services.resolution.signals import score_glossary_match

        candidate = MetadataAsset(
            asset_id=uuid.uuid4(),
            asset_type="field",
            workspace_id=WORKSPACE_ID,
            name="income",
            source_table="datasets",
            source_id=uuid.uuid4(),
        )
        term = MagicMock()
        term.business_name = "Revenue"
        term.synonyms = ["income", "earnings"]
        term.linked_asset_ids = [str(candidate.asset_id)]

        score = score_glossary_match("income", candidate, {"terms": [term]})
        assert score >= 0.9

    def test_fuzzy_match_score(self):
        from app.schemas.metadata_search import MetadataAsset
        from app.services.resolution.signals import score_glossary_match

        candidate = MetadataAsset(
            asset_id=uuid.uuid4(),
            asset_type="field",
            workspace_id=WORKSPACE_ID,
            name="rev",
            source_table="datasets",
            source_id=uuid.uuid4(),
        )
        term = MagicMock()
        term.business_name = "Revenue Total"
        term.synonyms = []
        term.linked_asset_ids = [str(candidate.asset_id)]

        score = score_glossary_match("Revenue Totl", candidate, {"terms": [term]})
        # Fuzzy match should score > 0 for close strings
        assert score > 0.0

    def test_no_terms_returns_zero(self):
        from app.schemas.metadata_search import MetadataAsset
        from app.services.resolution.signals import score_glossary_match

        candidate = MetadataAsset(
            asset_id=uuid.uuid4(),
            asset_type="field",
            workspace_id=WORKSPACE_ID,
            name="x",
            source_table="datasets",
            source_id=uuid.uuid4(),
        )
        score = score_glossary_match("anything", candidate, {"terms": []})
        assert score == 0.0

    def test_unlinked_match_partial_credit(self):
        from app.schemas.metadata_search import MetadataAsset
        from app.services.resolution.signals import score_glossary_match

        candidate = MetadataAsset(
            asset_id=uuid.uuid4(),
            asset_type="field",
            workspace_id=WORKSPACE_ID,
            name="other",
            source_table="datasets",
            source_id=uuid.uuid4(),
        )
        term = MagicMock()
        term.business_name = "Revenue"
        term.synonyms = []
        term.linked_asset_ids = []  # not linked to this candidate

        score = score_glossary_match("Revenue", candidate, {"terms": [term]})
        assert 0 < score < 1.0  # partial credit


# ============================================================
# Proposal Schema Tests (F111)
# ============================================================


class TestProposalSchemas:
    """Tests for proposal Pydantic schemas."""

    def test_proposal_request(self):
        from app.schemas.proposal import ProposalRequest

        r = ProposalRequest(prompt="email must not be null")
        assert r.prompt == "email must not be null"
        assert r.dataset_context is None

    def test_proposal_request_too_short(self):
        from app.schemas.proposal import ProposalRequest

        with pytest.raises(Exception):
            ProposalRequest(prompt="ab")

    def test_proposal_status_values(self):
        from app.schemas.proposal import ProposalStatus

        assert ProposalStatus.pending == "pending"
        assert ProposalStatus.confirmed == "confirmed"
        assert ProposalStatus.rejected == "rejected"
        assert ProposalStatus.adjusted == "adjusted"

    def test_proposal_payload(self):
        from app.schemas.proposal import ProposalPayload

        p = ProposalPayload(
            parsed_rule={"rule_type": "not_null"},
            parse_confidence=0.95,
            resolution_confidence=0.85,
        )
        assert p.parse_confidence == 0.95
        assert p.glossary_matches == []
        assert p.compiled_checks is None

    def test_confirm_request(self):
        from app.schemas.proposal import ConfirmProposalRequest, ProposalAdjustment

        r = ConfirmProposalRequest(
            adjustments=[
                ProposalAdjustment(field="rule_type", old_value="not_null", new_value="is_not_null")
            ],
            create_flow=True,
        )
        assert len(r.adjustments) == 1
        assert r.create_flow is True

    def test_reject_request(self):
        from app.schemas.proposal import RejectProposalRequest

        r = RejectProposalRequest(reason="Wrong column mapping")
        assert r.reason == "Wrong column mapping"


# ============================================================
# Resolution Schema Tests (F110)
# ============================================================


class TestGlossaryMatchSchema:
    """Tests for GlossaryMatch schema added in F110."""

    def test_glossary_match_model(self):
        from app.schemas.resolution import GlossaryMatch

        m = GlossaryMatch(
            term_id=TERM_ID,
            business_name="Revenue",
            match_score=0.95,
            match_type="exact",
            matched_on="Revenue",
        )
        assert m.term_id == TERM_ID
        assert m.match_score == 0.95
        assert m.domain is None

    def test_resolve_response_has_glossary_matches(self):
        from app.schemas.nl_rule_builder import SIREntity, StructuredIntermediateRepresentation
        from app.schemas.resolution import EntityResolution, ResolveResponse

        sir = StructuredIntermediateRepresentation(
            rule_type="not_null",
            subject=SIREntity(raw_text="email"),
            operator="is_not_null",
            confidence=0.9,
        )
        resp = ResolveResponse(
            resolved_rule=sir,
            subject_resolution=EntityResolution(raw_text="email"),
            glossary_matches=[],
        )
        assert resp.glossary_matches == []
        assert resp.overall_confidence == 0.0
