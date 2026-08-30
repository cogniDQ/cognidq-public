"""API-level tests for F124 disambiguation endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from app.schemas.disambiguation import (
    ClarificationAnswer,
    DisambiguationAnswerRequest,
    DisambiguationStartRequest,
)
from app.schemas.nl_rule_builder import RuleType, SIREntity, StructuredIntermediateRepresentation
from app.schemas.resolution import EntityResolution, ResolutionCandidate
from app.services.nl_rule_builder.disambiguation_sessions import DisambiguationSessionService
from fastapi import HTTPException


class TestDisambiguationEndpoints:
    def _sir(self) -> StructuredIntermediateRepresentation:
        return StructuredIntermediateRepresentation(
            rule_type=RuleType.NOT_NULL,
            subject=SIREntity(raw_text="email"),
            operator="is_not_null",
            confidence=0.62,
            requires_disambiguation=True,
        )

    def _resolution(self) -> EntityResolution:
        candidate = ResolutionCandidate(
            asset_id=uuid.uuid4(),
            column_name="email_address",
            overall_score=0.72,
            confidence_band="medium",
        )
        return EntityResolution(
            raw_text="email",
            requires_disambiguation=True,
            candidates=[candidate],
            best_candidate=candidate,
        )

    def test_start_answer_get_cancel_flow(self):
        from app.api.v1.endpoints import rule_builder as rb

        rb._disambiguation_session_service = DisambiguationSessionService()

        current_user = MagicMock(id=uuid.uuid4())
        workspace_id = uuid.uuid4()

        start = rb.start_disambiguation(
            workspace_id=workspace_id,
            request=DisambiguationStartRequest(
                request_text="email must not be null",
                parsed_rule=self._sir(),
                subject_resolution=self._resolution(),
            ),
            current_user=current_user,
        )

        assert start.session.workspace_id == workspace_id
        assert len(start.next_questions) >= 1

        answer = rb.answer_disambiguation(
            workspace_id=workspace_id,
            session_id=start.session.session_id,
            request=DisambiguationAnswerRequest(
                answers=[
                    ClarificationAnswer(
                        question_id=start.next_questions[0].question_id,
                        selected_option_ids=[start.next_questions[0].options[0].option_id]
                        if start.next_questions[0].options
                        else [],
                        value_text="is_not_null" if not start.next_questions[0].options else None,
                    )
                ]
            ),
            current_user=current_user,
        )

        assert answer.session_id == start.session.session_id

        session_read = rb.get_disambiguation_session(
            workspace_id=workspace_id,
            session_id=start.session.session_id,
            current_user=current_user,
        )
        assert session_read.session.session_id == start.session.session_id

        cancelled = rb.cancel_disambiguation_session(
            workspace_id=workspace_id,
            session_id=start.session.session_id,
            current_user=current_user,
        )
        assert cancelled.session.status.value == "cancelled"

    def test_answer_unknown_session_returns_404(self):
        from app.api.v1.endpoints import rule_builder as rb

        rb._disambiguation_session_service = DisambiguationSessionService()

        with pytest.raises(HTTPException) as exc:
            rb.answer_disambiguation(
                workspace_id=uuid.uuid4(),
                session_id=uuid.uuid4(),
                request=DisambiguationAnswerRequest(answers=[]),
                current_user=MagicMock(id=uuid.uuid4()),
            )

        assert exc.value.status_code == 404
