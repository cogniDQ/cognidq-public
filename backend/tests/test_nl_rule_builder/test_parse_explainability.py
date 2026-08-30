import uuid

from app.schemas.nl_rule_builder import (
    ClarifyingQuestion,
    RuleType,
    SIREntity,
    SIRScope,
    StructuredIntermediateRepresentation,
)
from app.services.nl_rule_builder.parse_explainability import ParseExplainabilityService


def _sir(
    confidence: float, requires_disambiguation: bool, with_glossary: bool
) -> StructuredIntermediateRepresentation:
    glossary = []
    matched_term_id = None
    if with_glossary:
        matched_term_id = str(uuid.uuid4())

    return StructuredIntermediateRepresentation(
        rule_type=RuleType.NOT_NULL,
        subject=SIREntity(
            raw_text="email",
            canonical_name="email",
            entity_type="column",
            matched_glossary_term_id=matched_term_id,
        ),
        operation={"operator": "is_not_null"},
        confidence=confidence,
        scope=SIRScope(),
        glossary_context=glossary,
        requires_disambiguation=requires_disambiguation,
        clarifying_questions=[
            ClarifyingQuestion(
                field="subject",
                question="Which email column?",
                options=["email", "work_email"],
                required=True,
            )
        ]
        if requires_disambiguation
        else [],
        clarification_context="subject column unclear" if requires_disambiguation else None,
    )


def test_build_trust_summary_confidence_bands_and_recommendation():
    service = ParseExplainabilityService(
        high_confidence_threshold=0.85, disambiguation_threshold=0.70
    )

    high = service.build_parse_trust_summary(_sir(0.90, False, True))
    medium = service.build_parse_trust_summary(_sir(0.75, False, False))
    low = service.build_parse_trust_summary(_sir(0.60, True, False))

    assert high.confidence_band == "high"
    assert high.recommendation == "ready_for_review"

    assert medium.confidence_band == "medium"
    assert "parsed without glossary-backed term match" in medium.assumptions

    assert low.confidence_band == "low"
    assert low.recommendation == "answer_clarifying_questions"
    assert "parser requested clarification before safe execution" in low.caveats


def test_build_parse_explainability_contains_core_topics():
    service = ParseExplainabilityService(
        high_confidence_threshold=0.85, disambiguation_threshold=0.70
    )
    sir = _sir(0.72, True, False)

    items = service.build_parse_explainability(sir, "email must not be null")
    topics = [item.topic for item in items]

    assert "rule_type" in topics
    assert "subject" in topics
    assert "clarification" in topics
