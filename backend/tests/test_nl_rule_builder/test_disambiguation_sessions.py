"""Tests for F124 P03 answer application and resume flow."""

from __future__ import annotations

import uuid

import pytest
from app.schemas.disambiguation import (
    AmbiguityOption,
    ClarificationAnswer,
    ClarificationAnswerType,
    ClarificationQuestion,
    DisambiguationSession,
    DisambiguationSessionStatus,
)
from app.services.nl_rule_builder.disambiguation_sessions import DisambiguationSessionService


def _option(option_id: str) -> AmbiguityOption:
    return AmbiguityOption(option_id=option_id, label=option_id, value=option_id)


def _session_with_questions() -> DisambiguationSession:
    return DisambiguationSession(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        request_text="check customer email",
        questions=[
            ClarificationQuestion(
                question_id="q_entity",
                ambiguity_id="amb_entity",
                prompt="Which column?",
                answer_type=ClarificationAnswerType.SINGLE_SELECT,
                options=[_option("a"), _option("b")],
                required=True,
            ),
            ClarificationQuestion(
                question_id="q_threshold",
                ambiguity_id="amb_threshold",
                prompt="Provide threshold",
                answer_type=ClarificationAnswerType.NUMERIC,
                required=True,
            ),
        ],
    )


def test_apply_answers_partial_keeps_session_open():
    service = DisambiguationSessionService()
    session = service.save_session(_session_with_questions())

    result = service.apply_answers(
        session.session_id,
        [ClarificationAnswer(question_id="q_entity", selected_option_ids=["a"])],
    )

    assert result.can_resume_pipeline is False
    assert result.pending_required_question_ids == ["q_threshold"]
    assert session.status == DisambiguationSessionStatus.OPEN


def test_apply_answers_all_required_resolves_session():
    service = DisambiguationSessionService()
    session = service.save_session(_session_with_questions())

    result = service.apply_answers(
        session.session_id,
        [
            ClarificationAnswer(question_id="q_entity", selected_option_ids=["b"]),
            ClarificationAnswer(question_id="q_threshold", value_number=98.5),
        ],
    )

    assert result.can_resume_pipeline is True
    assert result.pending_required_question_ids == []
    assert session.status == DisambiguationSessionStatus.RESOLVED


def test_apply_answers_rejects_invalid_option_id():
    service = DisambiguationSessionService()
    session = service.save_session(_session_with_questions())

    with pytest.raises(ValueError):
        service.apply_answers(
            session.session_id,
            [ClarificationAnswer(question_id="q_entity", selected_option_ids=["x"])],
        )


def test_apply_answers_rejects_unknown_question():
    service = DisambiguationSessionService()
    session = service.save_session(_session_with_questions())

    with pytest.raises(ValueError):
        service.apply_answers(
            session.session_id,
            [ClarificationAnswer(question_id="q_unknown", value_text="hello")],
        )
