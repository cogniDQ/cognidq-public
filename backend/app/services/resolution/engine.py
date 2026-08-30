"""ResolutionEngine — orchestrates 12-signal metadata resolution (F102)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.metadata_search import MetadataAsset
from app.schemas.nl_rule_builder import SIREntity, StructuredIntermediateRepresentation
from app.schemas.resolution import (
    EntityResolution,
    GlossaryMatch,
    ResolutionCandidate,
    ResolutionEvidence,
    ResolveRequest,
    ResolveResponse,
    SignalBreakdown,
)
from app.services.metadata_search.search_service import MetadataSearchService
from app.services.metadata_search.term_service import MetadataTermService
from app.services.resolution.metadata_context import MetadataContextService
from app.services.resolution.rationale_adapter import ResolverRationaleAdapter
from app.services.resolution.signals import (
    DEFAULT_WEIGHTS,
    SequenceMatcher,
    _normalize,
    compute_weighted_score,
    is_type_compatible,
)


class ResolutionEngine:
    """Resolves SIR entity raw_text references to physical metadata columns."""

    HIGH_THRESHOLD = 0.90
    DISAMBIGUATION_THRESHOLD = 0.70
    SCORE_GAP_THRESHOLD = 0.10
    DEFAULT_TOP_K = 5

    def __init__(
        self,
        search_service: MetadataSearchService | None = None,
        term_service: MetadataTermService | None = None,
        metadata_context_service: MetadataContextService | None = None,
        rationale_adapter: ResolverRationaleAdapter | None = None,
        weights: dict[str, float] | None = None,
    ):
        self._search = search_service or MetadataSearchService()
        self._terms = term_service or MetadataTermService()
        self._metadata_context = metadata_context_service or MetadataContextService()
        self._rationale = rationale_adapter or ResolverRationaleAdapter()
        self._weights = weights or DEFAULT_WEIGHTS

    def resolve(
        self,
        db: Session,
        workspace_id: UUID,
        request: ResolveRequest,
    ) -> ResolveResponse:
        sir = request.parsed_rule.model_copy(deep=True)

        # Build shared context
        context = self._build_context(request, sir)
        context = self._metadata_context.enrich_context(db, workspace_id, context)

        # Load glossary terms once
        terms = self._terms.list_terms(db, workspace_id, limit=200)
        context["terms"] = terms

        # Find glossary matches for the raw entities
        glossary_matches = self._find_glossary_matches(sir, terms)

        # Resolve subject
        subject_resolution = self._resolve_entity(
            db,
            workspace_id,
            sir.subject,
            "subject",
            context,
            request.selected_candidates,
        )

        # Apply best candidate to SIR
        if subject_resolution.best_candidate and not subject_resolution.requires_disambiguation:
            sir.subject.resolved_column = subject_resolution.best_candidate.column_name
            sir.subject.column_id = str(subject_resolution.best_candidate.asset_id)
            if subject_resolution.best_candidate.dataset_name:
                sir.subject.resolved_dataset = subject_resolution.best_candidate.dataset_name
            if subject_resolution.best_candidate.dataset_id:
                sir.subject.dataset_id = str(subject_resolution.best_candidate.dataset_id)

        # Resolve object (if present)
        object_resolution = None
        if sir.object:
            object_resolution = self._resolve_entity(
                db,
                workspace_id,
                sir.object,
                "object",
                context,
                request.selected_candidates,
            )
            if object_resolution.best_candidate and not object_resolution.requires_disambiguation:
                sir.object.resolved_column = object_resolution.best_candidate.column_name
                sir.object.column_id = str(object_resolution.best_candidate.asset_id)
                if object_resolution.best_candidate.dataset_name:
                    sir.object.resolved_dataset = object_resolution.best_candidate.dataset_name
                if object_resolution.best_candidate.dataset_id:
                    sir.object.dataset_id = str(object_resolution.best_candidate.dataset_id)

        # Overall confidence
        confidences = (
            [subject_resolution.best_candidate.overall_score]
            if subject_resolution.best_candidate
            else [0.0]
        )
        if object_resolution and object_resolution.best_candidate:
            confidences.append(object_resolution.best_candidate.overall_score)
        overall_confidence = min(confidences)

        requires_disambiguation = subject_resolution.requires_disambiguation or (
            object_resolution is not None and object_resolution.requires_disambiguation
        )

        return ResolveResponse(
            resolved_rule=sir,
            subject_resolution=subject_resolution,
            object_resolution=object_resolution,
            overall_confidence=overall_confidence,
            requires_disambiguation=requires_disambiguation,
            glossary_matches=glossary_matches,
            resolution_evidence=ResolutionEvidence(
                subject_candidates_count=len(subject_resolution.candidates),
                object_candidates_count=len(object_resolution.candidates)
                if object_resolution
                else 0,
                weights_used=self._weights,
            ),
        )

    def _resolve_entity(
        self,
        db: Session,
        workspace_id: UUID,
        entity: SIREntity,
        entity_key: str,
        context: dict,
        overrides: dict[str, str] | None,
    ) -> EntityResolution:
        raw_text = entity.raw_text

        # Check for user override
        if overrides and entity_key in overrides:
            override_id = overrides[entity_key]
            return EntityResolution(
                raw_text=raw_text,
                candidates=[],
                best_candidate=ResolutionCandidate(
                    asset_id=UUID(override_id),
                    column_name=raw_text,
                    overall_score=1.0,
                    confidence_band="high",
                    evidence_summary=["User override"],
                ),
                requires_disambiguation=False,
            )

        # Stage 1: Get candidate pool from metadata search
        candidates = self._get_candidates(db, workspace_id, raw_text, context)
        if not candidates:
            return EntityResolution(
                raw_text=raw_text,
                candidates=[],
                best_candidate=None,
                requires_disambiguation=True,
            )

        # Hard filter: type compatibility (Signal 12)
        operator = context.get("operator")
        candidates = [c for c in candidates if is_type_compatible(c, operator)]
        if not candidates:
            return EntityResolution(
                raw_text=raw_text,
                candidates=[],
                best_candidate=None,
                requires_disambiguation=True,
            )

        # Score and rank
        scored = self._score_candidates(candidates, raw_text, context)
        scored.sort(key=lambda c: c.overall_score, reverse=True)

        # Trim to top-K
        scored = scored[: self.DEFAULT_TOP_K]

        # Evaluate confidence
        requires_disambiguation, best = self._evaluate_confidence(scored)

        return EntityResolution(
            raw_text=raw_text,
            candidates=scored,
            best_candidate=best,
            requires_disambiguation=requires_disambiguation,
        )

    def _find_glossary_matches(self, sir, terms) -> list[GlossaryMatch]:
        """Find glossary terms matching raw entity text (subject/object)."""
        matches: list[GlossaryMatch] = []
        raw_texts = [sir.subject.raw_text]
        if sir.object:
            raw_texts.append(sir.object.raw_text)

        seen = set()
        for raw_text in raw_texts:
            raw_norm = _normalize(raw_text)
            raw_lower = raw_text.lower().strip()
            for term in terms:
                bname_lower = term.business_name.lower().strip()
                match_type = None
                match_score = 0.0
                matched_on = ""

                # Exact business_name
                if bname_lower == raw_lower:
                    match_type, match_score, matched_on = "exact", 1.0, term.business_name
                else:
                    # Fuzzy business_name
                    ratio = SequenceMatcher(None, raw_norm, _normalize(term.business_name)).ratio()
                    if ratio >= 0.80:
                        match_type, match_score, matched_on = (
                            "fuzzy",
                            round(ratio, 4),
                            term.business_name,
                        )

                # Check synonyms
                if match_type != "exact":
                    for syn in term.synonyms:
                        if syn.lower().strip() == raw_lower:
                            match_type, match_score, matched_on = "synonym", 0.95, syn
                            break
                        ratio = SequenceMatcher(None, raw_norm, _normalize(syn)).ratio()
                        if ratio >= 0.80 and ratio > match_score:
                            match_type, match_score, matched_on = "fuzzy", round(ratio, 4), syn

                if match_type and term.term_id not in seen:
                    seen.add(term.term_id)
                    matches.append(
                        GlossaryMatch(
                            term_id=term.term_id,
                            business_name=term.business_name,
                            technical_name=getattr(term, "technical_name", None),
                            domain=getattr(term, "domain", None),
                            definition=getattr(term, "definition", None),
                            match_score=match_score,
                            match_type=match_type,
                            matched_on=matched_on,
                        )
                    )

        matches.sort(key=lambda m: m.match_score, reverse=True)
        return matches

    def _get_candidates(
        self,
        db: Session,
        workspace_id: UUID,
        raw_text: str,
        context: dict,
    ) -> list[MetadataAsset]:
        result = self._search.search(
            db,
            workspace_id,
            raw_text,
            asset_type="field",
            domain=context.get("domain_hint"),
            limit=50,
        )
        return result.assets

    def _score_candidates(
        self,
        candidates: list[MetadataAsset],
        raw_text: str,
        context: dict,
    ) -> list[ResolutionCandidate]:
        scored = []
        for c in candidates:
            overall, breakdown = compute_weighted_score(raw_text, c, context, self._weights)

            band = "low"
            if overall >= self.HIGH_THRESHOLD:
                band = "high"
            elif overall >= self.DISAMBIGUATION_THRESHOLD:
                band = "medium"

            signal_breakdown = [
                SignalBreakdown(
                    signal_name=s["signal_name"],
                    score=s["score"],
                    available=s.get("available", True),
                    reason=s.get("reason"),
                    evidence=s["evidence"],
                )
                for s in breakdown
            ]
            scored.append(
                ResolutionCandidate(
                    asset_id=c.asset_id,
                    column_name=c.name,
                    dataset_name=None,
                    dataset_id=c.parent_asset_id,
                    data_type=c.data_type,
                    overall_score=overall,
                    confidence_band=band,
                    signal_breakdown=signal_breakdown,
                    evidence_summary=[s["signal_name"] for s in breakdown if s["score"] > 0],
                    rationale=self._rationale.build_candidate_rationale(
                        raw_text=raw_text,
                        candidate_name=c.name,
                        overall_score=overall,
                        confidence_band=band,
                        signal_breakdown=signal_breakdown,
                    ),
                )
            )

        return scored

    def _evaluate_confidence(
        self,
        scored: list[ResolutionCandidate],
    ) -> tuple[bool, ResolutionCandidate | None]:
        """Returns (requires_disambiguation, best_candidate)."""
        if not scored:
            return True, None

        best = scored[0]

        # Low confidence
        if best.overall_score < self.DISAMBIGUATION_THRESHOLD:
            return True, best

        # Small score gap between top-2
        if len(scored) >= 2:
            gap = best.overall_score - scored[1].overall_score
            if gap < self.SCORE_GAP_THRESHOLD:
                return True, best

        # Medium confidence
        if best.overall_score < self.HIGH_THRESHOLD:
            return True, best

        return False, best

    def _build_context(
        self, request: ResolveRequest, sir: StructuredIntermediateRepresentation
    ) -> dict:
        ctx: dict = {}

        # Dataset hint from request or SIR scope
        if request.dataset_context:
            ctx["dataset_hint"] = request.dataset_context
        elif sir.scope and sir.scope.dataset_hint:
            ctx["dataset_hint"] = sir.scope.dataset_hint

        # Domain hint
        if request.domain_context:
            ctx["domain_hint"] = request.domain_context
        elif sir.scope and sir.scope.domain_hint:
            ctx["domain_hint"] = sir.scope.domain_hint

        # Operator
        if sir.operator:
            ctx["operator"] = sir.operator

        return ctx
