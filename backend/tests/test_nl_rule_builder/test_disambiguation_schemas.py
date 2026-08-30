"""Tests for F124 P01 disambiguation schemas and session model."""

from __future__ import annotations

import uuid

import pytest
from app.schemas.disambiguation import (
    AmbiguityCategory,
    AmbiguityItem,
    AmbiguityOption,
    AmbiguitySeverity,
    ClarificationAnswer,
    ClarificationAnswerType,
    ClarificationQuestion,
    DisambiguationSession,
    DisambiguationSessionStatus,
)


def _option(option_id: str) -> AmbiguityOption:
    return AmbiguityOption(
        option_id=option_id,
        label=f"Option {option_id}",
        value=option_id,
    )


def test_ambiguity_item_schema():
    item = AmbiguityItem(
        ambiguity_id="amb-1",
        category=AmbiguityCategory.ENTITY,
        severity=AmbiguitySeverity.BLOCKING,
        reason_code="candidate_tie",
        confidence=0.61,
        alternatives=[_option("a"), _option("b")],
    )

    assert item.category == AmbiguityCategory.ENTITY
    assert item.severity == AmbiguitySeverity.BLOCKING
    assert len(item.alternatives) == 2


def test_select_question_requires_options():
    with pytest.raises(ValueError):
        ClarificationQuestion(
            question_id="q1",
            ambiguity_id="amb-1",
            prompt="Which dataset did you mean?",
            answer_type=ClarificationAnswerType.SINGLE_SELECT,
            options=[],
        )


def test_free_text_question_allows_empty_options():
    question = ClarificationQuestion(
        question_id="q2",
        ambiguity_id="amb-2",
        prompt="Please provide expected threshold",
        answer_type=ClarificationAnswerType.FREE_TEXT,
        options=[],
    )

    assert question.answer_type == ClarificationAnswerType.FREE_TEXT


def test_disambiguation_session_lifecycle_and_answers():
    session = DisambiguationSession(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        request_text="Check customer phone uniqueness",
        ambiguities=[
            AmbiguityItem(
                ambiguity_id="amb-1",
                category=AmbiguityCategory.CHECK_TYPE,
                severity=AmbiguitySeverity.MAJOR,
                reason_code="check_type_uncertain",
                confidence=0.55,
            )
        ],
    )

    assert session.status == DisambiguationSessionStatus.OPEN

    answer = ClarificationAnswer(
        question_id="q1",
        selected_option_ids=["opt-1"],
    )
    session.register_answer(answer)

    assert "q1" in session.answers

    session.resolve()
    assert session.status == DisambiguationSessionStatus.RESOLVED


def test_disambiguation_session_cancel():
    session = DisambiguationSession(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        request_text="Check email completeness",
    )

    session.cancel()
    assert session.status == DisambiguationSessionStatus.CANCELLED
