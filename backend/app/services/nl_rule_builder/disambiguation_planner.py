"""Question planning for multi-stage disambiguation (F124 P02)."""

from __future__ import annotations

from app.schemas.disambiguation import (
    AmbiguityCategory,
    AmbiguityItem,
    AmbiguitySeverity,
    ClarificationAnswerType,
    ClarificationQuestion,
)


class QuestionPlanner:
    """Builds deterministic question sets from ambiguity items."""

    _SEVERITY_RANK: dict[AmbiguitySeverity, int] = {
        AmbiguitySeverity.BLOCKING: 0,
        AmbiguitySeverity.MAJOR: 1,
        AmbiguitySeverity.MINOR: 2,
    }

    _CATEGORY_RANK: dict[AmbiguityCategory, int] = {
        AmbiguityCategory.ENTITY: 0,
        AmbiguityCategory.DATASET_SCOPE: 1,
        AmbiguityCategory.OPERATOR: 2,
        AmbiguityCategory.CHECK_TYPE: 3,
        AmbiguityCategory.THRESHOLD: 4,
    }

    def plan_questions(
        self,
        ambiguities: list[AmbiguityItem],
        max_questions: int = 3,
    ) -> list[ClarificationQuestion]:
        ordered = sorted(
            ambiguities,
            key=lambda a: (
                self._SEVERITY_RANK.get(a.severity, 99),
                a.confidence,
                self._CATEGORY_RANK.get(a.category, 99),
                a.ambiguity_id,
            ),
        )

        questions: list[ClarificationQuestion] = []
        for ambiguity in ordered[: max(1, max_questions)]:
            answer_type = ClarificationAnswerType.FREE_TEXT
            options = []
            if ambiguity.alternatives:
                answer_type = ClarificationAnswerType.SINGLE_SELECT
                options = ambiguity.alternatives

            questions.append(
                ClarificationQuestion(
                    question_id=f"q_{ambiguity.ambiguity_id}",
                    ambiguity_id=ambiguity.ambiguity_id,
                    prompt=self._build_prompt(ambiguity),
                    answer_type=answer_type,
                    options=options,
                    required=ambiguity.severity
                    in {AmbiguitySeverity.BLOCKING, AmbiguitySeverity.MAJOR},
                    rationale=self._build_rationale(ambiguity),
                )
            )

        return questions

    @staticmethod
    def _build_prompt(ambiguity: AmbiguityItem) -> str:
        if ambiguity.category == AmbiguityCategory.ENTITY:
            target = ambiguity.entity_key or "field"
            return (
                f"Which {target} did you mean for '{ambiguity.evidence.get('raw_text', target)}'?"
            )
        if ambiguity.category == AmbiguityCategory.OPERATOR:
            return "Which comparison operator should be used for this rule?"
        if ambiguity.category == AmbiguityCategory.CHECK_TYPE:
            return "What kind of data quality check did you intend for this rule?"
        if ambiguity.category == AmbiguityCategory.THRESHOLD:
            return "What threshold should be used for this validation?"
        if ambiguity.category == AmbiguityCategory.DATASET_SCOPE:
            return "Which dataset scope should be used for this rule?"
        return "Please clarify the intended rule configuration."

    @staticmethod
    def _build_rationale(ambiguity: AmbiguityItem) -> str:
        return (
            f"Asked because {ambiguity.reason_code} "
            f"(category={ambiguity.category.value}, confidence={ambiguity.confidence:.2f})."
        )
