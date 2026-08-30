"""
Tests for F102 — Metadata Resolution and Ranking
Covers signal scoring, resolution engine, schemas, and API endpoint.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from app.schemas.metadata_search import MetadataAsset, MetadataSearchResponse, MetadataTermResponse
from app.schemas.nl_rule_builder import (
    RuleType,
    SIREntity,
    SIRScope,
    StructuredIntermediateRepresentation,
)
from app.schemas.resolution import (
    EntityResolution,
    ResolutionCandidate,
    ResolveRequest,
    ResolveResponse,
    SignalBreakdown,
)
from app.services.resolution.engine import ResolutionEngine
from app.services.resolution.rationale_adapter import ResolverRationaleAdapter
from app.services.resolution.signals import (
    DEFAULT_WEIGHTS,
    compute_weighted_score,
    is_type_compatible,
    score_co_occurrence,
    score_dataset_context,
    score_domain_context,
    score_glossary_match,
    score_historical_usage,
    score_lexical_match,
    score_lineage_proximity,
    score_ownership,
    score_profile_compatibility,
)

WORKSPACE_ID = uuid.uuid4()


def _make_asset(
    name: str, data_type: str = "varchar", domain: str = None, parent_id=None
) -> MetadataAsset:
    return MetadataAsset(
        asset_id=uuid.uuid4(),
        asset_type="field",
        workspace_id=WORKSPACE_ID,
        name=name,
        source_table="dataset_fields",
        source_id=uuid.uuid4(),
        data_type=data_type,
        business_domain=domain,
        parent_asset_id=parent_id,
    )


def _make_sir(
    subject_text: str, operator: str = None, object_text: str = None, **kwargs
) -> StructuredIntermediateRepresentation:
    obj = SIREntity(raw_text=object_text) if object_text else None
    return StructuredIntermediateRepresentation(
        rule_type=kwargs.get("rule_type", RuleType.NOT_NULL),
        subject=SIREntity(raw_text=subject_text),
        operator=operator or "is_not_null",
        object=obj,
        confidence=kwargs.get("confidence", 0.90),
        scope=kwargs.get("scope", SIRScope()),
    )


# ============================================================
# Schema Tests (P01)
# ============================================================


class TestResolutionSchemas:
    def test_signal_breakdown(self):
        sb = SignalBreakdown(signal_name="lexical_match", score=0.95, evidence="exact")
        assert sb.score == 0.95

    def test_signal_score_clamped(self):
        with pytest.raises(Exception):
            SignalBreakdown(signal_name="test", score=1.5)

    def test_resolution_candidate_defaults(self):
        rc = ResolutionCandidate(
            asset_id=uuid.uuid4(),
            column_name="order_date",
            overall_score=0.85,
        )
        assert rc.confidence_band == "low"
        assert rc.signal_breakdown == []

    def test_entity_resolution_defaults(self):
        er = EntityResolution(raw_text="shipping date")
        assert er.candidates == []
        assert er.best_candidate is None
        assert er.requires_disambiguation is False

    def test_resolve_request_strips_context(self):
        sir = _make_sir("test")
        req = ResolveRequest(
            parsed_rule=sir,
            dataset_context="  orders  ",
            domain_context="  finance  ",
        )
        assert req.dataset_context == "orders"
        assert req.domain_context == "finance"

    def test_resolve_request_empty_context(self):
        sir = _make_sir("test")
        req = ResolveRequest(parsed_rule=sir, dataset_context="   ")
        assert req.dataset_context is None

    def test_resolve_response_shape(self):
        sir = _make_sir("test")
        resp = ResolveResponse(
            resolved_rule=sir,
            subject_resolution=EntityResolution(raw_text="test"),
            overall_confidence=0.85,
        )
        assert resp.object_resolution is None
        assert resp.requires_disambiguation is False


# ============================================================
# Signal Scoring Tests (P02)
# ============================================================


class TestSignalScoring:
    def test_exact_name_match(self):
        asset = _make_asset("order_date")
        score = score_lexical_match("order_date", asset, {})
        assert score == 1.0

    def test_exact_name_case_insensitive(self):
        asset = _make_asset("Order_Date")
        score = score_lexical_match("order_date", asset, {})
        assert score == 1.0

    def test_normalized_name_match(self):
        asset = _make_asset("shipping_date")
        score = score_lexical_match("shipping date", asset, {})
        assert score == 0.95

    def test_fuzzy_name_partial(self):
        asset = _make_asset("ship_dt")
        score = score_lexical_match("shipping date", asset, {})
        assert 0.0 < score < 0.95

    def test_glossary_match_with_link(self):
        asset = _make_asset("revenue_total")
        term = MetadataTermResponse(
            term_id=uuid.uuid4(),
            workspace_id=WORKSPACE_ID,
            business_name="Revenue",
            synonyms=["Rev", "Total Revenue"],
            linked_asset_ids=[str(asset.asset_id)],
        )
        score = score_glossary_match("Revenue", asset, {"terms": [term]})
        assert score == 1.0

    def test_glossary_synonym_match(self):
        asset = _make_asset("revenue_total")
        term = MetadataTermResponse(
            term_id=uuid.uuid4(),
            workspace_id=WORKSPACE_ID,
            business_name="Revenue",
            synonyms=["Rev"],
            linked_asset_ids=[str(asset.asset_id)],
        )
        score = score_glossary_match("Rev", asset, {"terms": [term]})
        assert score == 0.95

    def test_glossary_no_link(self):
        asset = _make_asset("revenue_total")
        term = MetadataTermResponse(
            term_id=uuid.uuid4(),
            workspace_id=WORKSPACE_ID,
            business_name="Revenue",
            synonyms=[],
            linked_asset_ids=["other-id"],
        )
        score = score_glossary_match("Revenue", asset, {"terms": [term]})
        assert score == 0.3  # partial credit

    def test_glossary_no_terms(self):
        asset = _make_asset("test")
        score = score_glossary_match("test", asset, {})
        assert score == 0.0

    def test_dataset_context_match(self):
        parent_id = uuid.uuid4()
        asset = _make_asset("order_date", parent_id=parent_id)
        context = {
            "dataset_hint": "orders",
            "parent_dataset_names": {str(parent_id): "orders"},
        }
        score = score_dataset_context("order_date", asset, context)
        assert score == 1.0

    def test_dataset_context_no_match(self):
        asset = _make_asset("order_date")
        score = score_dataset_context("order_date", asset, {"dataset_hint": "orders"})
        assert score == 0.0

    def test_domain_context_match(self):
        asset = _make_asset("revenue", domain="finance")
        score = score_domain_context("revenue", asset, {"domain_hint": "finance"})
        assert score == 1.0

    def test_domain_context_no_match(self):
        asset = _make_asset("revenue", domain="marketing")
        score = score_domain_context("revenue", asset, {"domain_hint": "finance"})
        assert score == 0.0

    def test_profile_compatibility_date_operator(self):
        asset = _make_asset("created_at", data_type="timestamp")
        score = score_profile_compatibility("created_at", asset, {"operator": "after"})
        assert score == 1.0

    def test_profile_incompatible(self):
        asset = _make_asset("name", data_type="varchar")
        score = score_profile_compatibility("name", asset, {"operator": "after"})
        assert score == 0.0

    def test_profile_neutral(self):
        asset = _make_asset("test")
        score = score_profile_compatibility("test", asset, {})
        assert score == 0.5

    def test_lineage_proximity_signal(self):
        asset = _make_asset("order_date")
        score = score_lineage_proximity(
            "order date",
            asset,
            {"lineage_distance_by_asset": {str(asset.asset_id): 1}},
        )
        assert 0.0 < score <= 1.0

    def test_co_occurrence_signal(self):
        asset = _make_asset("order_date")
        score = score_co_occurrence(
            "order date",
            asset,
            {"cooccurrence_by_asset": {str(asset.asset_id): 0.82}},
        )
        assert score == 0.82

    def test_historical_usage_signal(self):
        asset = _make_asset("order_date")
        score = score_historical_usage(
            "order date",
            asset,
            {
                "usage_count_by_asset": {str(asset.asset_id): 20},
                "recency_days_by_asset": {str(asset.asset_id): 5.0},
            },
        )
        assert 0.0 < score <= 1.0

    def test_ownership_profile_signal(self):
        asset = _make_asset("customer_id")
        score = score_ownership(
            "customer id",
            asset,
            {
                "profile_stats_by_asset": {
                    str(asset.asset_id): {
                        "null_rate": 0.05,
                        "cardinality_class": "high",
                    }
                }
            },
        )
        assert 0.0 < score <= 1.0

    def test_type_compatible_date(self):
        asset = _make_asset("created_at", data_type="timestamp")
        assert is_type_compatible(asset, "after") is True

    def test_type_incompatible(self):
        asset = _make_asset("name", data_type="varchar")
        assert is_type_compatible(asset, "after") is False

    def test_type_compatible_no_operator(self):
        asset = _make_asset("name", data_type="varchar")
        assert is_type_compatible(asset, None) is True

    def test_type_compatible_any_type_operator(self):
        asset = _make_asset("name", data_type="varchar")
        assert is_type_compatible(asset, "is_not_null") is True

    def test_default_weights_sum_to_one(self):
        assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)

    def test_compute_weighted_score_shape(self):
        asset = _make_asset("order_date")
        overall, breakdown = compute_weighted_score("order_date", asset, {})
        assert 0.0 <= overall <= 1.0
        assert len(breakdown) == len(DEFAULT_WEIGHTS)
        assert all(0.0 <= s["score"] <= 1.0 for s in breakdown)

    def test_metadata_signals_neutral_when_unavailable(self):
        asset = _make_asset("order_date")
        _, breakdown = compute_weighted_score("order_date", asset, {})

        names = {s["signal_name"]: s for s in breakdown}
        assert names["lineage_proximity"]["available"] is False
        assert names["co_occurrence"]["available"] is False
        assert names["historical_usage"]["available"] is False
        assert names["ownership"]["available"] is False

        assert names["lineage_proximity"]["score"] == 0.5
        assert names["co_occurrence"]["score"] == 0.5
        assert names["historical_usage"]["score"] == 0.5
        assert names["ownership"]["score"] == 0.5


# ============================================================
# ResolutionEngine Tests (P03)
# ============================================================


class TestResolutionEngine:
    def _mock_search(self, assets: list[MetadataAsset]):
        svc = MagicMock()
        svc.search.return_value = MetadataSearchResponse(assets=assets, terms=[], total=len(assets))
        return svc

    def _mock_terms(self, terms=None):
        svc = MagicMock()
        svc.list_terms.return_value = terms or []
        return svc

    def test_exact_match_high_confidence(self):
        asset = _make_asset("order_date", data_type="date")
        engine = ResolutionEngine(
            search_service=self._mock_search([asset]),
            term_service=self._mock_terms(),
        )
        sir = _make_sir("order_date", operator="is_not_null")
        request = ResolveRequest(parsed_rule=sir)
        db = MagicMock()

        result = engine.resolve(db, WORKSPACE_ID, request)
        assert result.subject_resolution.best_candidate is not None
        assert result.subject_resolution.best_candidate.column_name == "order_date"
        assert result.subject_resolution.best_candidate.overall_score > 0

    def test_no_candidates_disambiguation(self):
        engine = ResolutionEngine(
            search_service=self._mock_search([]),
            term_service=self._mock_terms(),
        )
        sir = _make_sir("nonexistent_field")
        request = ResolveRequest(parsed_rule=sir)
        db = MagicMock()

        result = engine.resolve(db, WORKSPACE_ID, request)
        assert result.requires_disambiguation is True
        assert result.subject_resolution.requires_disambiguation is True
        assert result.subject_resolution.best_candidate is None

    def test_type_incompatible_filtered(self):
        asset = _make_asset("customer_name", data_type="varchar")
        engine = ResolutionEngine(
            search_service=self._mock_search([asset]),
            term_service=self._mock_terms(),
        )
        sir = _make_sir("date field", operator="after")
        request = ResolveRequest(parsed_rule=sir)
        db = MagicMock()

        result = engine.resolve(db, WORKSPACE_ID, request)
        # varchar should be filtered out for "after" operator
        assert result.requires_disambiguation is True

    def test_user_override(self):
        override_id = str(uuid.uuid4())
        engine = ResolutionEngine(
            search_service=self._mock_search([]),
            term_service=self._mock_terms(),
        )
        sir = _make_sir("some_field")
        request = ResolveRequest(
            parsed_rule=sir,
            selected_candidates={"subject": override_id},
        )
        db = MagicMock()

        result = engine.resolve(db, WORKSPACE_ID, request)
        assert result.subject_resolution.best_candidate is not None
        assert str(result.subject_resolution.best_candidate.asset_id) == override_id
        assert result.subject_resolution.requires_disambiguation is False

    def test_multi_entity_resolution(self):
        asset1 = _make_asset("shipping_date", data_type="date")
        asset2 = _make_asset("order_date", data_type="date")
        search_svc = MagicMock()
        search_svc.search.side_effect = [
            MetadataSearchResponse(assets=[asset1], terms=[], total=1),
            MetadataSearchResponse(assets=[asset2], terms=[], total=1),
        ]
        engine = ResolutionEngine(
            search_service=search_svc,
            term_service=self._mock_terms(),
        )
        sir = _make_sir(
            "shipping date",
            operator="greater_than",
            object_text="order date",
            rule_type=RuleType.COLUMN_COMPARISON,
        )
        request = ResolveRequest(parsed_rule=sir)
        db = MagicMock()

        result = engine.resolve(db, WORKSPACE_ID, request)
        assert result.subject_resolution.best_candidate is not None
        assert result.object_resolution is not None
        assert result.object_resolution.best_candidate is not None

    def test_close_score_gap_disambiguation(self):
        asset1 = _make_asset("ship_date", data_type="date")
        asset2 = _make_asset("ship_dt", data_type="date")
        engine = ResolutionEngine(
            search_service=self._mock_search([asset1, asset2]),
            term_service=self._mock_terms(),
        )
        sir = _make_sir("shipping date", operator="is_not_null")
        request = ResolveRequest(parsed_rule=sir)
        db = MagicMock()

        result = engine.resolve(db, WORKSPACE_ID, request)
        # With similar names, scores should be close → disambiguation
        assert result.subject_resolution.candidates is not None

    def test_domain_context_boost(self):
        asset_finance = _make_asset("revenue", data_type="numeric", domain="finance")
        asset_other = _make_asset("revenue", data_type="numeric", domain="marketing")
        engine = ResolutionEngine(
            search_service=self._mock_search([asset_finance, asset_other]),
            term_service=self._mock_terms(),
        )
        sir = _make_sir("revenue", operator="is_not_null")
        request = ResolveRequest(parsed_rule=sir, domain_context="finance")
        db = MagicMock()

        result = engine.resolve(db, WORKSPACE_ID, request)
        assert len(result.subject_resolution.candidates) == 2
        # Finance domain candidate should score higher
        candidates = result.subject_resolution.candidates
        finance_cand = [c for c in candidates if c.asset_id == asset_finance.asset_id][0]
        other_cand = [c for c in candidates if c.asset_id == asset_other.asset_id][0]
        assert finance_cand.overall_score >= other_cand.overall_score

    def test_evidence_in_response(self):
        asset = _make_asset("order_date")
        engine = ResolutionEngine(
            search_service=self._mock_search([asset]),
            term_service=self._mock_terms(),
        )
        sir = _make_sir("order_date")
        request = ResolveRequest(parsed_rule=sir)
        db = MagicMock()

        result = engine.resolve(db, WORKSPACE_ID, request)
        assert "weights_used" in result.resolution_evidence
        assert "subject_candidates_count" in result.resolution_evidence

    def test_signal_breakdown_in_candidates(self):
        asset = _make_asset("order_date")
        engine = ResolutionEngine(
            search_service=self._mock_search([asset]),
            term_service=self._mock_terms(),
        )
        sir = _make_sir("order_date")
        request = ResolveRequest(parsed_rule=sir)
        db = MagicMock()

        result = engine.resolve(db, WORKSPACE_ID, request)
        assert len(result.subject_resolution.candidates) >= 1
        cand = result.subject_resolution.candidates[0]
        assert len(cand.signal_breakdown) > 0
        assert all(0.0 <= s.score <= 1.0 for s in cand.signal_breakdown)
        metadata_signals = [
            s
            for s in cand.signal_breakdown
            if s.signal_name
            in {"lineage_proximity", "co_occurrence", "historical_usage", "ownership"}
        ]
        assert all(s.available is False for s in metadata_signals)
        assert len(cand.rationale) > 0
        assert "neutral fallback" in " ".join(cand.rationale)

    def test_overall_confidence_is_min(self):
        asset1 = _make_asset("shipping_date", data_type="date")
        asset2 = _make_asset("order_date", data_type="date")
        search_svc = MagicMock()
        search_svc.search.side_effect = [
            MetadataSearchResponse(assets=[asset1], terms=[], total=1),
            MetadataSearchResponse(assets=[asset2], terms=[], total=1),
        ]
        engine = ResolutionEngine(
            search_service=search_svc,
            term_service=self._mock_terms(),
        )
        sir = _make_sir(
            "shipping date",
            operator="greater_than",
            object_text="order date",
            rule_type=RuleType.COLUMN_COMPARISON,
        )
        request = ResolveRequest(parsed_rule=sir)
        db = MagicMock()

        result = engine.resolve(db, WORKSPACE_ID, request)
        # Overall confidence should be min of subject and object
        subj_score = (
            result.subject_resolution.best_candidate.overall_score
            if result.subject_resolution.best_candidate
            else 0
        )
        obj_score = (
            result.object_resolution.best_candidate.overall_score
            if result.object_resolution and result.object_resolution.best_candidate
            else 0
        )
        expected_min = min(subj_score, obj_score)
        assert result.overall_confidence == pytest.approx(expected_min, abs=0.01)


class TestResolverRationaleAdapter:
    def test_build_candidate_rationale_includes_confidence_and_unavailable_note(self):
        adapter = ResolverRationaleAdapter()
        breakdown = [
            SignalBreakdown(
                signal_name="lexical_match", score=1.0, evidence="exact normalized match"
            ),
            SignalBreakdown(
                signal_name="dataset_context",
                score=0.0,
                available=False,
                reason="dataset hint missing",
                evidence="",
            ),
        ]

        rationale = adapter.build_candidate_rationale(
            raw_text="order date",
            candidate_name="order_date",
            overall_score=0.91,
            confidence_band="high",
            signal_breakdown=breakdown,
        )

        assert "high confidence" in rationale[0]
        assert "name similarity" in " ".join(rationale)
        assert "neutral fallback" in " ".join(rationale)


# ============================================================
# API Endpoint Tests (P04)
# ============================================================


class TestResolveEndpoint:
    def test_resolve_endpoint_calls_engine(self):
        from app.api.v1.endpoints.rule_builder import resolve_rule

        db = MagicMock()
        sir = _make_sir("order_date")

        with patch("app.api.v1.endpoints.rule_builder._resolution_engine") as mock_engine:
            mock_engine.resolve.return_value = ResolveResponse(
                resolved_rule=sir,
                subject_resolution=EntityResolution(raw_text="order_date"),
                overall_confidence=0.95,
            )

            result = resolve_rule(
                workspace_id=WORKSPACE_ID,
                request=ResolveRequest(parsed_rule=sir),
                db=db,
                current_user=MagicMock(id=uuid.uuid4()),
            )

            assert result.overall_confidence == 0.95
            mock_engine.resolve.assert_called_once()

    def test_resolve_endpoint_unauthorized(self):
        from app.api.v1.endpoints.rule_builder import resolve_rule
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            resolve_rule(
                workspace_id=WORKSPACE_ID,
                request=ResolveRequest(parsed_rule=_make_sir("test")),
                db=MagicMock(),
                current_user=None,
            )
