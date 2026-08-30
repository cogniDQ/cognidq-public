"""Pydantic schemas for Metadata Resolution and Ranking (F102)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.nl_rule_builder import StructuredIntermediateRepresentation

# ── Signal breakdown ──────────────────────────────────────────────────────


class SignalBreakdown(BaseModel):
    """Individual signal score with evidence."""

    signal_name: str
    score: float = Field(..., ge=0.0, le=1.0)
    available: bool = True
    reason: str | None = None
    evidence: str = ""


# ---------------------------------------------------------------------------
# F128 — ResolutionEvidence (replaces Dict[str, Any] on ResolveResponse)
# ---------------------------------------------------------------------------


class ResolutionEvidence(BaseModel):
    """Typed evidence summary from the resolution engine (F128).

    Uses extra='allow' so legacy dict keys (subject_candidates_count, weights_used,
    etc.) are preserved for backward compatibility.
    """

    model_config = ConfigDict(extra="allow")

    subject_signals: list[SignalBreakdown] = Field(default_factory=list)
    object_signals: list[SignalBreakdown] | None = None
    glossary_contribution: float = 0.0
    metadata_contribution: float = 0.0
    notes: list[str] = Field(default_factory=list)

    def __contains__(self, key: str) -> bool:
        """Support 'key in evidence' dict-like checks (backward compat)."""
        return key in self.model_dump()

    def __getitem__(self, key: str) -> Any:
        dump = self.model_dump()
        if key in dump:
            return dump[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self.model_dump().get(key, default)


# ── Resolution candidate ─────────────────────────────────────────────────


class ResolutionCandidate(BaseModel):
    """A candidate column/asset with ranked score."""

    asset_id: UUID
    column_name: str
    dataset_name: str | None = None
    dataset_id: UUID | None = None
    data_type: str | None = None
    overall_score: float = Field(0.0, ge=0.0, le=1.0)
    confidence_band: str = "low"  # high, medium, low
    signal_breakdown: list[SignalBreakdown] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)


# ── Entity resolution result ─────────────────────────────────────────────


class EntityResolution(BaseModel):
    """Resolution result for a single entity (subject or object)."""

    raw_text: str
    candidates: list[ResolutionCandidate] = Field(default_factory=list)
    best_candidate: ResolutionCandidate | None = None
    requires_disambiguation: bool = False


# ── Request / Response ────────────────────────────────────────────────────


class ResolveRequest(BaseModel):
    """Request body for the resolve endpoint."""

    parsed_rule: StructuredIntermediateRepresentation
    dataset_context: str | None = Field(None, max_length=500)
    domain_context: str | None = Field(None, max_length=100)
    selected_candidates: dict[str, str] | None = None  # entity_key -> asset_id override

    @field_validator("dataset_context", "domain_context", mode="before")
    @classmethod
    def strip_optional(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v


class GlossaryMatch(BaseModel):
    """A glossary term that matched during resolution."""

    term_id: UUID
    business_name: str
    technical_name: str | None = None
    domain: str | None = None
    definition: str | None = None
    match_score: float = Field(0.0, ge=0.0, le=1.0)
    match_type: str = "exact"  # exact, synonym, fuzzy
    matched_on: str = ""  # what text matched


class ResolveResponse(BaseModel):
    """Response from the resolve endpoint."""

    resolved_rule: StructuredIntermediateRepresentation
    subject_resolution: EntityResolution
    object_resolution: EntityResolution | None = None
    overall_confidence: float = Field(0.0, ge=0.0, le=1.0)
    requires_disambiguation: bool = False
    resolution_evidence: ResolutionEvidence = Field(default_factory=ResolutionEvidence)
    glossary_matches: list[GlossaryMatch] = Field(default_factory=list)
