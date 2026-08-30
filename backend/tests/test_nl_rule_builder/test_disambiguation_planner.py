"""Tests for F124 P02 ambiguity detector and question planner."""

from __future__ import annotations

import uuid

from app.schemas.disambiguation import (
    AmbiguityCategory,
    AmbiguityItem,
    AmbiguityOption,
    AmbiguitySeverity,
)
from app.schemas.nl_rule_builder import RuleType, SIREntity, StructuredIntermediateRepresentation
from app.schemas.resolution import EntityResolution, ResolutionCandidate
from app.services.nl_rule_builder.disambiguation_detector import DisambiguationDetector
from app.services.nl_rule_builder.disambiguation_planner import QuestionPlanner


def _candidate(name: str, score: float) -> ResolutionCandidate:
    return ResolutionCandidate(
        asset_id=uuid.uuid4(),
        column_name=name,
        overall_score=score,
        confidence_band="medium",
    )


def _sir(
    confidence: float = 0.6, requires_disambiguation: bool = True
) -> StructuredIntermediateRepresentation:
    return StructuredIntermediateRepresentation(
        rule_type=RuleType.NOT_NULL,
        subject=SIREntity(raw_text="email"),
        operator="is_not_null",
        confidence=confidence,
        requires_disambiguation=requires_disambiguation,
    )


def test_detector_emits_entity_ambiguity_from_resolution_tie():
    detector = DisambiguationDetector()
    sir = _sir()

    resolution = EntityResolution(
        raw_text="email",
        requires_disambiguation=True,
        candidates=[
            _candidate("email_address", 0.78),
            _candidate("email", 0.75),
        ],
        best_candidate=_candidate("email_address", 0.78),
    )

    items = detector.detect(sir=sir, subject_resolution=resolution)

    entity_items = [i for i in items if i.category == AmbiguityCategory.ENTITY]
    assert len(entity_items) == 1
    assert entity_items[0].reason_code == "candidate_tie"
    assert len(entity_items[0].alternatives) == 2


def test_detector_emits_operator_ambiguity_when_missing_operator():
    detector = DisambiguationDetector()
    sir = StructuredIntermediateRepresentation(
        rule_type=RuleType.NOT_NULL,
        subject=SIREntity(raw_text="email"),
        operator=None,
        confidence=0.92,
        requires_disambiguation=False,
    )

    items = detector.detect(sir=sir)
    operator_items = [i for i in items if i.category == AmbiguityCategory.OPERATOR]
    assert len(operator_items) == 1
    assert operator_items[0].severity == AmbiguitySeverity.BLOCKING


def test_planner_orders_questions_deterministically():
    planner = QuestionPlanner()

    ambiguities = [
        AmbiguityItem(
            ambiguity_id="b",
            category=AmbiguityCategory.CHECK_TYPE,
            severity=AmbiguitySeverity.MAJOR,
            reason_code="low_parse_confidence",
            confidence=0.40,
        ),
        AmbiguityItem(
            ambiguity_id="a",
            category=AmbiguityCategory.ENTITY,
            severity=AmbiguitySeverity.BLOCKING,
            reason_code="candidate_tie",
            confidence=0.75,
            alternatives=[
                AmbiguityOption(option_id="1", label="hr.email", value="1"),
                AmbiguityOption(option_id="2", label="crm.email", value="2"),
            ],
        ),
    ]

    questions = planner.plan_questions(ambiguities, max_questions=2)

    assert len(questions) == 2
    assert questions[0].ambiguity_id == "a"
    assert questions[0].answer_type.value == "single_select"
    assert questions[1].ambiguity_id == "b"
    assert questions[1].answer_type.value == "free_text"
