"""Session service for disambiguation answer application and resume logic (F124 P03)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.schemas.disambiguation import (
    ClarificationAnswer,
    ClarificationAnswerType,
    ClarificationQuestion,
    DisambiguationSession,
)


@dataclass
class ApplyAnswersResult:
    session_id: UUID
    can_resume_pipeline: bool
    pending_required_question_ids: list[str]
    answered_question_ids: list[str]


class DisambiguationSessionService:
    """Manages in-memory disambiguation sessions and answer application."""

    def __init__(self) -> None:
        self._sessions: dict[UUID, DisambiguationSession] = {}

    def save_session(self, session: DisambiguationSession) -> DisambiguationSession:
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: UUID) -> DisambiguationSession | None:
        return self._sessions.get(session_id)

    def apply_answers(
        self,
        session_id: UUID,
        answers: list[ClarificationAnswer],
    ) -> ApplyAnswersResult:
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError("disambiguation session not found")

        question_map = {q.question_id: q for q in session.questions}
        answered_ids: list[str] = []

        for answer in answers:
            question = question_map.get(answer.question_id)
            if question is None:
                raise ValueError(f"unknown question_id: {answer.question_id}")

            self._validate_answer(question, answer)
            session.register_answer(answer)
            answered_ids.append(answer.question_id)

        pending_required = [
            q.question_id
            for q in session.questions
            if q.required and q.question_id not in session.answers
        ]

        if not pending_required:
            session.resolve()

        return ApplyAnswersResult(
            session_id=session.session_id,
            can_resume_pipeline=not pending_required,
            pending_required_question_ids=pending_required,
            answered_question_ids=answered_ids,
        )

    @staticmethod
    def _validate_answer(question: ClarificationQuestion, answer: ClarificationAnswer) -> None:
        answer_type = question.answer_type

        if answer_type in {
            ClarificationAnswerType.SINGLE_SELECT,
            ClarificationAnswerType.MULTI_SELECT,
        }:
            if not answer.selected_option_ids:
                raise ValueError(
                    f"selected_option_ids required for question {question.question_id}"
                )

            valid_option_ids = {o.option_id for o in question.options}
            invalid = [opt for opt in answer.selected_option_ids if opt not in valid_option_ids]
            if invalid:
                raise ValueError(
                    f"invalid option id(s) for question {question.question_id}: {invalid}"
                )

            if (
                answer_type == ClarificationAnswerType.SINGLE_SELECT
                and len(answer.selected_option_ids) != 1
            ):
                raise ValueError(
                    f"single_select question {question.question_id} requires exactly one option"
                )

        elif answer_type == ClarificationAnswerType.FREE_TEXT:
            text = (answer.value_text or "").strip()
            if question.required and not text:
                raise ValueError(f"value_text required for question {question.question_id}")

        elif answer_type == ClarificationAnswerType.NUMERIC:
            if answer.value_number is None:
                raise ValueError(f"value_number required for question {question.question_id}")
