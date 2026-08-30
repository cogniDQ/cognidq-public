"""Parse explainability and trust summary builder (F125 P02)."""

from __future__ import annotations

from app.schemas.nl_rule_builder import (
    ParseExplanationItem,
    ParseTrustSummary,
    StructuredIntermediateRepresentation,
)


class ParseExplainabilityService:
    """Builds deterministic explainability payloads from SIR output."""

    def __init__(
        self,
        high_confidence_threshold: float,
        disambiguation_threshold: float,
    ) -> None:
        self._high_confidence_threshold = high_confidence_threshold
        self._disambiguation_threshold = disambiguation_threshold

    def build_parse_explainability(
        self,
        sir: StructuredIntermediateRepresentation,
        rule_text: str,
    ) -> list[ParseExplanationItem]:
        items: list[ParseExplanationItem] = []

        items.append(
            ParseExplanationItem(
                topic="rule_type",
                decision=f"Interpreted rule as '{sir.rule_type.value}'",
                evidence=[f"Input: {rule_text[:200]}"],
                confidence_impact=round((sir.confidence - 0.5), 4),
                caveat="requires clarification" if sir.requires_disambiguation else None,
            )
        )

        items.append(
            ParseExplanationItem(
                topic="subject",
                decision=f"Primary entity interpreted as '{sir.subject.raw_text}'",
                evidence=[
                    f"dataset_hint={sir.subject.dataset_id or sir.scope.dataset_hint or '-'}",
                    f"glossary_matches={len(sir.glossary_context)}",
                ],
                confidence_impact=0.1 if sir.subject.matched_glossary_term_id else 0.0,
                caveat="no glossary term matched" if not sir.glossary_context else None,
            )
        )

        if sir.clarifying_questions:
            items.append(
                ParseExplanationItem(
                    topic="clarification",
                    decision="Clarification questions were generated",
                    evidence=[f"question_count={len(sir.clarifying_questions)}"],
                    confidence_impact=-0.15,
                    caveat=sir.clarification_context or "additional user input required",
                )
            )

        return items

    def build_parse_trust_summary(
        self,
        sir: StructuredIntermediateRepresentation,
    ) -> ParseTrustSummary:
        band = "low"
        if sir.confidence >= self._high_confidence_threshold:
            band = "high"
        elif sir.confidence >= self._disambiguation_threshold:
            band = "medium"

        caveats = list(sir.parse_warnings)
        assumptions: list[str] = []
        if not sir.glossary_context:
            assumptions.append("parsed without glossary-backed term match")
        if sir.scope and not sir.scope.dataset_hint:
            assumptions.append("dataset inferred without explicit dataset_hint")
        if sir.requires_disambiguation:
            caveats.append("parser requested clarification before safe execution")

        recommendation = "ready_for_review"
        if sir.requires_disambiguation:
            recommendation = "answer_clarifying_questions"
        elif band == "low":
            recommendation = "manual_verification_required"

        return ParseTrustSummary(
            confidence_band=band,
            confidence_score=sir.confidence,
            caveats=caveats,
            assumptions=assumptions,
            recommendation=recommendation,
        )
