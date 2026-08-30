"""
Tests for F101 — Metadata Search Abstraction Layer
Covers schemas, sync service, search service, term service, and API endpoints.
"""

import json
import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from app.schemas.metadata_search import (
    AssetType,
    MetadataAsset,
    MetadataSearchResponse,
    MetadataSyncResponse,
    MetadataTermCreate,
    MetadataTermResponse,
    TrustLevel,
)
from app.services.metadata_search.search_service import MetadataSearchService
from app.services.metadata_search.sync_service import MetadataSyncService
from app.services.metadata_search.term_service import MetadataTermService

WORKSPACE_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


# ============================================================
# Schema Validation Tests (P01)
# ============================================================


class TestSchemas:
    """Tests for metadata search Pydantic schemas."""

    def test_asset_type_values(self):
        assert AssetType.ALL == ["dataset", "field", "datasource"]

    def test_trust_level_values(self):
        assert TrustLevel.ALL == ["low", "medium", "high", "authoritative"]

    def test_metadata_asset_defaults(self):
        asset = MetadataAsset(
            asset_id=uuid.uuid4(),
            asset_type="dataset",
            workspace_id=WORKSPACE_ID,
            name="orders",
            source_table="datasets",
            source_id=uuid.uuid4(),
        )
        assert asset.relevance_score == 0.0
        assert asset.description is None
        assert asset.parent_asset_id is None

    def test_term_create_strips_name(self):
        term = MetadataTermCreate(business_name="  Revenue  ")
        assert term.business_name == "Revenue"

    def test_term_create_rejects_empty_name(self):
        with pytest.raises(Exception):
            MetadataTermCreate(business_name="")

    def test_term_create_rejects_invalid_trust(self):
        with pytest.raises(Exception):
            MetadataTermCreate(business_name="Test", trust_level="ultra")

    def test_term_create_defaults(self):
        term = MetadataTermCreate(business_name="ARR")
        assert term.synonyms == []
        assert term.trust_level == "medium"
        assert term.domain is None

    def test_metadata_search_response_shape(self):
        resp = MetadataSearchResponse(assets=[], terms=[], total=0)
        assert resp.total == 0

    def test_metadata_sync_response(self):
        resp = MetadataSyncResponse(
            assets_created=3,
            assets_updated=1,
            total=4,
            workspace_id=WORKSPACE_ID,
        )
        assert resp.total == 4

    def test_term_response_defaults(self):
        resp = MetadataTermResponse(
            term_id=uuid.uuid4(),
            workspace_id=WORKSPACE_ID,
            business_name="Churn Rate",
        )
        assert resp.trust_level == "medium"
        assert resp.source == "manual"
        assert resp.synonyms == []

    def test_term_create_with_synonyms(self):
        term = MetadataTermCreate(
            business_name="Net Revenue",
            synonyms=["NRR", "Net Rev"],
            domain="finance",
            trust_level="high",
        )
        assert len(term.synonyms) == 2
        assert term.domain == "finance"


# ============================================================
# MetadataSyncService Tests (P02)
# ============================================================


class TestSyncService:
    """Tests for MetadataSyncService."""

    def _make_row(self, is_insert: bool):
        row = MagicMock()
        row.is_insert = is_insert
        return row

    def test_sync_workspace_counts(self):
        svc = MetadataSyncService()
        db = MagicMock()

        # datasets: 2 inserts
        ds_result = MagicMock()
        ds_result.__iter__ = lambda s: iter([self._make_row(True), self._make_row(True)])
        # fields: 1 insert, 1 update
        fld_result = MagicMock()
        fld_result.__iter__ = lambda s: iter([self._make_row(True), self._make_row(False)])
        # sources: 1 update
        src_result = MagicMock()
        src_result.__iter__ = lambda s: iter([self._make_row(False)])

        db.execute.side_effect = [ds_result, fld_result, src_result]

        result = svc.sync_workspace(db, WORKSPACE_ID)

        assert result.assets_created == 3
        assert result.assets_updated == 2
        assert result.total == 5
        assert result.workspace_id == WORKSPACE_ID
        db.commit.assert_called_once()

    def test_sync_empty_workspace(self):
        svc = MetadataSyncService()
        db = MagicMock()

        empty = MagicMock()
        empty.__iter__ = lambda s: iter([])
        db.execute.side_effect = [empty, empty, empty]

        result = svc.sync_workspace(db, WORKSPACE_ID)

        assert result.assets_created == 0
        assert result.assets_updated == 0
        assert result.total == 0

    def test_sync_calls_three_queries(self):
        svc = MetadataSyncService()
        db = MagicMock()

        empty = MagicMock()
        empty.__iter__ = lambda s: iter([])
        db.execute.side_effect = [empty, empty, empty]

        svc.sync_workspace(db, WORKSPACE_ID)
        assert db.execute.call_count == 3


# ============================================================
# MetadataSearchService Tests (P02)
# ============================================================


class TestSearchService:
    """Tests for MetadataSearchService."""

    def test_empty_query_returns_empty(self):
        svc = MetadataSearchService()
        db = MagicMock()

        result = svc.search(db, WORKSPACE_ID, "")
        assert result.total == 0
        assert result.assets == []
        assert result.terms == []
        db.execute.assert_not_called()

    def test_whitespace_query_returns_empty(self):
        svc = MetadataSearchService()
        db = MagicMock()

        result = svc.search(db, WORKSPACE_ID, "   ")
        assert result.total == 0

    def test_search_calls_both_asset_and_term_queries(self):
        svc = MetadataSearchService()
        db = MagicMock()

        asset_result = MagicMock()
        asset_result.fetchall.return_value = []
        term_result = MagicMock()
        term_result.fetchall.return_value = []

        db.execute.side_effect = [asset_result, term_result]

        result = svc.search(db, WORKSPACE_ID, "revenue")
        assert db.execute.call_count == 2
        assert result.total == 0

    def test_search_returns_assets(self):
        svc = MetadataSearchService()
        db = MagicMock()

        asset_id = uuid.uuid4()
        source_id = uuid.uuid4()
        now = datetime.now(UTC)

        asset_row = MagicMock()
        asset_row.asset_id = asset_id
        asset_row.workspace_id = WORKSPACE_ID
        asset_row.asset_type = "dataset"
        asset_row.name = "revenue_data"
        asset_row.display_name = "revenue_data"
        asset_row.description = "Monthly revenue"
        asset_row.business_domain = "finance"
        asset_row.data_type = "table"
        asset_row.parent_asset_id = None
        asset_row.source_table = "datasets"
        asset_row.source_id = source_id
        asset_row.relevance_score = 0.85
        asset_row.created_at = now

        asset_result = MagicMock()
        asset_result.fetchall.return_value = [asset_row]
        term_result = MagicMock()
        term_result.fetchall.return_value = []

        db.execute.side_effect = [asset_result, term_result]

        result = svc.search(db, WORKSPACE_ID, "revenue")
        assert result.total == 1
        assert len(result.assets) == 1
        assert result.assets[0].name == "revenue_data"
        assert result.assets[0].relevance_score == 0.85

    def test_search_returns_terms(self):
        svc = MetadataSearchService()
        db = MagicMock()

        term_id = uuid.uuid4()
        now = datetime.now(UTC)

        term_row = MagicMock()
        term_row.term_id = term_id
        term_row.workspace_id = WORKSPACE_ID
        term_row.business_name = "Annual Recurring Revenue"
        term_row.technical_name = "arr"
        term_row.definition = "Total annual subscription revenue"
        term_row.synonyms = ["ARR"]
        term_row.domain = "finance"
        term_row.linked_asset_ids = []
        term_row.source = "manual"
        term_row.trust_level = "high"
        term_row.relevance_score = 0.92
        term_row.created_at = now

        asset_result = MagicMock()
        asset_result.fetchall.return_value = []
        term_result = MagicMock()
        term_result.fetchall.return_value = [term_row]

        db.execute.side_effect = [asset_result, term_result]

        result = svc.search(db, WORKSPACE_ID, "ARR")
        assert result.total == 1
        assert len(result.terms) == 1
        assert result.terms[0].business_name == "Annual Recurring Revenue"

    def test_search_limit_capped(self):
        svc = MetadataSearchService()
        db = MagicMock()

        asset_result = MagicMock()
        asset_result.fetchall.return_value = []
        term_result = MagicMock()
        term_result.fetchall.return_value = []
        db.execute.side_effect = [asset_result, term_result]

        # Should not error with limit > 100
        result = svc.search(db, WORKSPACE_ID, "test", limit=999)
        assert result.total == 0

    def test_search_weight_constants(self):
        svc = MetadataSearchService()
        assert svc.W_EXACT + svc.W_TSRANK + svc.W_TRIGRAM == pytest.approx(1.0)


# ============================================================
# MetadataTermService Tests (P02)
# ============================================================


class TestTermService:
    """Tests for MetadataTermService."""

    def test_create_term(self):
        svc = MetadataTermService()
        db = MagicMock()

        term_id = uuid.uuid4()
        now = datetime.now(UTC)

        row = MagicMock()
        row.term_id = term_id
        row.workspace_id = WORKSPACE_ID
        row.business_name = "Churn Rate"
        row.technical_name = "churn_rate"
        row.definition = "Percentage of customers lost"
        row.synonyms = ["attrition"]
        row.domain = "retention"
        row.linked_asset_ids = []
        row.source = "manual"
        row.trust_level = "medium"
        row.created_at = now

        result_mock = MagicMock()
        result_mock.fetchone.return_value = row
        db.execute.return_value = result_mock

        payload = MetadataTermCreate(
            business_name="Churn Rate",
            technical_name="churn_rate",
            definition="Percentage of customers lost",
            synonyms=["attrition"],
            domain="retention",
        )

        result = svc.create_term(db, WORKSPACE_ID, TENANT_ID, payload)
        assert result.business_name == "Churn Rate"
        assert result.term_id == term_id
        db.commit.assert_called_once()

    def test_list_terms_no_domain(self):
        svc = MetadataTermService()
        db = MagicMock()

        term_id = uuid.uuid4()
        now = datetime.now(UTC)

        row = MagicMock()
        row.term_id = term_id
        row.workspace_id = WORKSPACE_ID
        row.business_name = "Revenue"
        row.technical_name = "revenue"
        row.definition = "Total income"
        row.synonyms = []
        row.domain = "finance"
        row.linked_asset_ids = []
        row.source = "manual"
        row.trust_level = "high"
        row.created_at = now

        result_mock = MagicMock()
        result_mock.fetchall.return_value = [row]
        db.execute.return_value = result_mock

        terms = svc.list_terms(db, WORKSPACE_ID)
        assert len(terms) == 1
        assert terms[0].business_name == "Revenue"

    def test_list_terms_with_domain(self):
        svc = MetadataTermService()
        db = MagicMock()

        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db.execute.return_value = result_mock

        terms = svc.list_terms(db, WORKSPACE_ID, domain="finance")
        assert terms == []

    def test_list_terms_limit_capped(self):
        svc = MetadataTermService()
        db = MagicMock()

        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db.execute.return_value = result_mock

        # Should not error with limit > 200
        terms = svc.list_terms(db, WORKSPACE_ID, limit=500)
        assert terms == []


# ============================================================
# API Endpoint Tests (P03)
# ============================================================


class TestMetadataEndpoints:
    """Tests for metadata API endpoint functions."""

    def test_sync_endpoint_calls_service(self):
        from app.api.v1.endpoints.metadata import sync_metadata

        db = MagicMock()

        with patch("app.api.v1.endpoints.metadata._sync_service") as mock_svc:
            mock_svc.sync_workspace.return_value = MetadataSyncResponse(
                assets_created=2,
                assets_updated=1,
                total=3,
                workspace_id=WORKSPACE_ID,
            )

            result = sync_metadata(
                workspace_id=WORKSPACE_ID,
                db=db,
                current_user={"id": str(uuid.uuid4()), "email": "test@example.com"},
            )

            assert result.total == 3
            mock_svc.sync_workspace.assert_called_once_with(db, WORKSPACE_ID)

    def test_search_endpoint_calls_service(self):
        from app.api.v1.endpoints.metadata import search_metadata

        db = MagicMock()

        with patch("app.api.v1.endpoints.metadata._search_service") as mock_svc:
            mock_svc.search.return_value = MetadataSearchResponse(assets=[], terms=[], total=0)

            result = search_metadata(
                workspace_id=WORKSPACE_ID,
                q="revenue",
                asset_type=None,
                domain=None,
                limit=20,
                db=db,
                current_user={"id": str(uuid.uuid4()), "email": "test@example.com"},
            )

            assert result.total == 0
            mock_svc.search.assert_called_once()

    def test_create_term_endpoint_calls_service(self):
        from app.api.v1.endpoints.metadata import create_term

        db = MagicMock()
        term_id = uuid.uuid4()

        with patch("app.api.v1.endpoints.metadata._term_service") as mock_svc:
            mock_svc.create_term.return_value = MetadataTermResponse(
                term_id=term_id,
                workspace_id=WORKSPACE_ID,
                business_name="Churn",
            )

            payload = MetadataTermCreate(business_name="Churn")
            _user = MagicMock()
            _user.tenant_id = uuid.uuid4()
            _user.platform_role = None
            result = create_term(
                workspace_id=WORKSPACE_ID,
                payload=payload,
                db=db,
                current_user=_user,
            )

            assert result.business_name == "Churn"
            mock_svc.create_term.assert_called_once()

    def test_list_terms_endpoint_calls_service(self):
        from app.api.v1.endpoints.metadata import list_terms

        db = MagicMock()

        with patch("app.api.v1.endpoints.metadata._term_service") as mock_svc:
            mock_svc.list_terms.return_value = []

            _user = MagicMock()
            _user.tenant_id = uuid.uuid4()
            _user.platform_role = None
            result = list_terms(
                workspace_id=WORKSPACE_ID,
                domain=None,
                limit=50,
                db=db,
                current_user=_user,
            )

            assert result == []
            mock_svc.list_terms.assert_called_once()
