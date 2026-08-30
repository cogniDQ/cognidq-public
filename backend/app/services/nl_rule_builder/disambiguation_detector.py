"""Ambiguity detection for multi-stage disambiguation (F124 P02)."""

from __future__ import annotations

from app.schemas.disambiguation import (
    AmbiguityCategory,
    AmbiguityItem,
    AmbiguityOption,
    AmbiguitySeverity,
)
from app.schemas.nl_rule_builder import StructuredIntermediateRepresentation
from app.schemas.resolution import EntityResolution


class DisambiguationDetector:
    """Detects ambiguous parse/resolve outcomes and emits structured items."""

    LOW_CONFIDENCE_THRESHOLD = 0.70

    def detect(
        self,
        sir: StructuredIntermediateRepresentation,
        subject_resolution: EntityResolution | None = None,
        object_resolution: EntityResolution | None = None,
    ) -> list[AmbiguityItem]:
        ambiguities: list[AmbiguityItem] = []

        # Parse-level ambiguity from confidence and parse-level disambiguation flag.
        if sir.requires_disambiguation or sir.confidence < self.LOW_CONFIDENCE_THRESHOLD:
            ambiguities.append(
                AmbiguityItem(
                    ambiguity_id="parse_confidence",
                    category=AmbiguityCategory.CHECK_TYPE,
                    severity=AmbiguitySeverity.MAJOR,
                    reason_code="low_parse_confidence",
                    confidence=max(0.0, min(1.0, sir.confidence)),
                    evidence={
                        "rule_type": sir.rule_type.value,
                        "warnings": sir.parse_warnings,
                    },
                )
            )

        # Operator required for most actionable checks.
        if sir.rule_type.value != "unknown" and not sir.operator:
            ambiguities.append(
                AmbiguityItem(
                    ambiguity_id="missing_operator",
                    category=AmbiguityCategory.OPERATOR,
                    severity=AmbiguitySeverity.BLOCKING,
                    reason_code="operator_missing",
                    confidence=max(0.0, min(1.0, sir.confidence)),
                    evidence={"subject": sir.subject.raw_text},
                )
            )

        ambiguities.extend(self._entity_ambiguities("subject", subject_resolution))
        ambiguities.extend(self._entity_ambiguities("object", object_resolution))

        return ambiguities

    def _entity_ambiguities(
        self,
        entity_key: str,
        resolution: EntityResolution | None,
    ) -> list[AmbiguityItem]:
        if resolution is None or not resolution.requires_disambiguation:
            return []

        options: list[AmbiguityOption] = []
        for candidate in resolution.candidates[:5]:
            option_id = str(candidate.asset_id)
            label = candidate.column_name
            if candidate.dataset_name:
                label = f"{candidate.dataset_name}.{candidate.column_name}"
            options.append(
                AmbiguityOption(
                    option_id=option_id,
                    label=label,
                    value=option_id,
                    metadata={
                        "score": candidate.overall_score,
                        "confidence_band": candidate.confidence_band,
                    },
                )
            )

        return [
            AmbiguityItem(
                ambiguity_id=f"{entity_key}_candidate_tie",
                category=AmbiguityCategory.ENTITY,
                severity=AmbiguitySeverity.BLOCKING,
                reason_code="candidate_tie",
                entity_key=entity_key,
                confidence=resolution.best_candidate.overall_score
                if resolution.best_candidate
                else 0.0,
                alternatives=options,
                evidence={
                    "raw_text": resolution.raw_text,
                    "candidate_count": len(resolution.candidates),
                },
            )
        ]
