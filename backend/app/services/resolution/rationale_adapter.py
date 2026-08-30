"""Business-facing rationale adapter for resolution signal evidence (F125 P03)."""

from __future__ import annotations

from app.schemas.resolution import SignalBreakdown

_SIGNAL_LABELS = {
    "lexical_match": "name similarity",
    "glossary_match": "glossary alignment",
    "dataset_context": "dataset context",
    "domain_context": "domain context",
    "profile_compatibility": "type/profile compatibility",
    "lineage_proximity": "lineage proximity",
    "co_occurrence": "historical co-occurrence",
    "historical_usage": "historical usage",
    "ownership": "ownership/profile quality",
}


class ResolverRationaleAdapter:
    """Converts raw signal breakdown into concise, deterministic rationale text."""

    def build_candidate_rationale(
        self,
        raw_text: str,
        candidate_name: str,
        overall_score: float,
        confidence_band: str,
        signal_breakdown: list[SignalBreakdown],
    ) -> list[str]:
        rationale: list[str] = [
            (
                f"Resolved '{raw_text}' to '{candidate_name}' with "
                f"{confidence_band} confidence ({overall_score:.2f})."
            )
        ]

        positive = [s for s in signal_breakdown if s.available and s.score >= 0.6]
        positive.sort(key=lambda s: (-s.score, s.signal_name))

        for s in positive[:3]:
            label = _SIGNAL_LABELS.get(s.signal_name, s.signal_name.replace("_", " "))
            evidence = s.evidence or "signal evidence available"
            rationale.append(f"Strong {label} signal ({s.score:.2f}): {evidence}.")

        unavailable = [s for s in signal_breakdown if not s.available and s.reason]
        if unavailable:
            names = ", ".join(sorted(s.signal_name for s in unavailable))
            rationale.append(
                f"Some metadata signals were unavailable ({names}); neutral fallback was applied."
            )

        return rationale
