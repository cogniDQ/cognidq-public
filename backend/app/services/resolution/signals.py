"""Signal scoring functions for the 12-signal resolution model (F102).

Each function returns a float in [0, 1]. All functions take:
  - raw_text: the entity raw text to resolve
  - candidate: a MetadataAsset from the search index
  - context: dict with optional keys like dataset_hint, domain_hint, rule_type, terms, etc.
"""

from __future__ import annotations

import math
import re
from difflib import SequenceMatcher

from app.schemas.metadata_search import MetadataAsset, MetadataTermResponse

# ── Type compatibility lookup ─────────────────────────────────────────────

# Map rule_type/operator keywords to compatible data types
_DATE_TYPES = {"date", "datetime", "timestamp", "timestamptz", "time"}
_NUMERIC_TYPES = {
    "int",
    "integer",
    "bigint",
    "smallint",
    "float",
    "double",
    "decimal",
    "numeric",
    "real",
    "number",
}
_STRING_TYPES = {"varchar", "text", "char", "string", "character varying"}

_OPERATOR_TYPE_MAP: dict[str, set] = {
    "greater_than": _NUMERIC_TYPES | _DATE_TYPES,
    "less_than": _NUMERIC_TYPES | _DATE_TYPES,
    "between": _NUMERIC_TYPES | _DATE_TYPES,
    "after": _DATE_TYPES,
    "before": _DATE_TYPES,
    "is_not_null": None,  # any type
    "is_null": None,
    "equals": None,
    "not_equals": None,
    "in_list": None,
    "not_in_list": None,
    "matches_pattern": _STRING_TYPES,
    "contains": _STRING_TYPES,
}


def _normalize(text: str) -> str:
    """Lowercase, strip, replace separators with spaces, collapse whitespace."""
    t = text.lower().strip()
    t = re.sub(r"[_\-./]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t


# ── Signal 1+2: Lexical Match ────────────────────────────────────────────


def score_lexical_match(raw_text: str, candidate: MetadataAsset, context: dict) -> float:
    """Combined exact + normalized name match (Signals 1-2)."""
    raw_lower = raw_text.lower().strip()
    name_lower = candidate.name.lower().strip()

    # Exact match
    if raw_lower == name_lower:
        return 1.0

    # Normalized match
    raw_norm = _normalize(raw_text)
    name_norm = _normalize(candidate.name)

    if raw_norm == name_norm:
        return 0.95

    # Fuzzy ratio
    ratio = SequenceMatcher(None, raw_norm, name_norm).ratio()
    return round(min(ratio, 1.0), 4)


# ── Signal 3+4: Glossary and Synonym Match ───────────────────────────────


def score_glossary_match(raw_text: str, candidate: MetadataAsset, context: dict) -> float:
    """Glossary term + synonym match with fuzzy support (Signals 3-4).

    context["terms"]: list of MetadataTermResponse from the term index.
    """
    terms: list[MetadataTermResponse] = context.get("terms", [])
    if not terms:
        return 0.0

    raw_lower = raw_text.lower().strip()
    raw_norm = _normalize(raw_text)
    asset_id_str = str(candidate.asset_id)

    best = 0.0
    for term in terms:
        match_score = 0.0
        # Check business_name — exact
        bname = term.business_name.lower().strip()
        if bname == raw_lower:
            match_score = 1.0
        else:
            # Fuzzy business_name
            ratio = SequenceMatcher(None, raw_norm, _normalize(term.business_name)).ratio()
            if ratio >= 0.80:
                match_score = max(match_score, ratio * 0.9)

        # Check synonyms
        for syn in term.synonyms:
            syn_lower = syn.lower().strip()
            if syn_lower == raw_lower:
                match_score = max(match_score, 0.95)
                break
            ratio = SequenceMatcher(None, raw_norm, _normalize(syn)).ratio()
            if ratio >= 0.80:
                match_score = max(match_score, ratio * 0.85)

        if match_score <= 0:
            continue

        if asset_id_str in term.linked_asset_ids:
            best = max(best, match_score)
        else:
            # Term matches but no direct link — partial credit
            best = max(best, match_score * 0.3)

    return best


# ── Signal 5: Dataset Context Match ──────────────────────────────────────


def score_dataset_context(raw_text: str, candidate: MetadataAsset, context: dict) -> float:
    """Boost candidates from user's current dataset (Signal 5).

    context["dataset_hint"]: dataset name or ID.
    """
    hint = context.get("dataset_hint")
    if not hint:
        return 0.0

    hint_lower = str(hint).lower().strip()

    # Check parent dataset name (for fields)
    if candidate.asset_type == "field" and candidate.parent_asset_id:
        # If the parent's source_id or name matches hint
        parent_name = context.get("parent_dataset_names", {}).get(
            str(candidate.parent_asset_id), ""
        )
        if parent_name.lower() == hint_lower:
            return 1.0

    # Check candidate's own name for datasets
    if candidate.asset_type == "dataset" and candidate.name.lower() == hint_lower:
        return 1.0

    return 0.0


# ── Signal 6: Domain Context Match ───────────────────────────────────────


def score_domain_context(raw_text: str, candidate: MetadataAsset, context: dict) -> float:
    """Boost candidates matching the rule's business domain (Signal 6).

    context["domain_hint"]: domain string.
    """
    hint = context.get("domain_hint")
    if not hint or not candidate.business_domain:
        return 0.0

    if candidate.business_domain.lower().strip() == hint.lower().strip():
        return 1.0

    return 0.0


# ── Signal 7: Lineage Proximity (stub) ───────────────────────────────────


def score_lineage_proximity(raw_text: str, candidate: MetadataAsset, context: dict) -> float:
    """Lineage proximity boost (Signal 7).

    context["lineage_distance_by_asset"]: {asset_id -> hop distance}, where
    lower distance means stronger affinity.
    """
    lineage = context.get("lineage_distance_by_asset", {})
    distance = lineage.get(str(candidate.asset_id))
    if distance is None:
        return 0.0

    # Exponential decay: 1 hop ~= 0.78, 2 hops ~= 0.61, far hops trend to 0.
    return round(max(0.0, min(1.0, math.exp(-0.25 * float(distance)))), 4)


# ── Signal 8: Co-Occurrence (soft boost, stub) ──────────────────────────


def score_co_occurrence(raw_text: str, candidate: MetadataAsset, context: dict) -> float:
    """Co-occurrence patterns (Signal 8).

    context["cooccurrence_by_asset"]: {asset_id -> normalized score in [0,1]}.
    """
    co_map = context.get("cooccurrence_by_asset", {})
    score = co_map.get(str(candidate.asset_id))
    if score is None:
        return 0.0
    return max(0.0, min(1.0, float(score)))


# ── Signal 9: Data Profile Compatibility ─────────────────────────────────


def score_profile_compatibility(raw_text: str, candidate: MetadataAsset, context: dict) -> float:
    """Data type / profile compatibility (Signal 9).

    context["operator"]: the rule operator from SIR.
    """
    operator = context.get("operator")
    if not operator or not candidate.data_type:
        return 0.5  # neutral when info missing

    compatible_types = _OPERATOR_TYPE_MAP.get(operator)
    if compatible_types is None:
        return 1.0  # operator works with any type

    ctype = candidate.data_type.lower().strip()
    for t in compatible_types:
        if t in ctype:
            return 1.0

    return 0.0


# ── Signal 10: Historical Usage (stub) ───────────────────────────────────


def score_historical_usage(raw_text: str, candidate: MetadataAsset, context: dict) -> float:
    """Historical usage and recency blend (Signal 10).

    context["usage_count_by_asset"]: {asset_id -> usage_count}
    context["recency_days_by_asset"]: {asset_id -> age_in_days}
    """
    usage = context.get("usage_count_by_asset", {})
    recency = context.get("recency_days_by_asset", {})

    count = usage.get(str(candidate.asset_id))
    age_days = recency.get(str(candidate.asset_id))

    if count is None and age_days is None:
        return 0.0

    # Saturating popularity curve: fast gains early, then flatten.
    usage_score = 0.0
    if count is not None:
        usage_score = max(0.0, min(1.0, 1.0 - math.exp(-0.08 * float(count))))

    # Recency half-life around 30 days.
    recency_score = 0.0
    if age_days is not None:
        recency_score = max(0.0, min(1.0, math.exp(-float(age_days) / 30.0)))

    if count is None:
        return round(recency_score, 4)
    if age_days is None:
        return round(usage_score, 4)

    return round((0.65 * usage_score) + (0.35 * recency_score), 4)


# ── Signal 11: Ownership/Stewardship (soft boost, stub) ─────────────────


def score_ownership(raw_text: str, candidate: MetadataAsset, context: dict) -> float:
    """Profile-driven compatibility proxy (Signal 11).

    Uses optional profile stats from context to reduce confidence for poor
    quality columns while keeping fail-open neutrality when unavailable.
    """
    profile = context.get("profile_stats_by_asset", {})
    stats = profile.get(str(candidate.asset_id))
    if not stats:
        return 0.0

    null_rate = stats.get("null_rate")
    cardinality_class = str(stats.get("cardinality_class") or "").lower().strip()

    null_penalty = 0.0
    if null_rate is not None:
        null_penalty = max(0.0, min(1.0, float(null_rate))) * 0.6

    card_boost = 0.0
    if cardinality_class in {"high", "medium"}:
        card_boost = 0.15
    elif cardinality_class == "low":
        card_boost = 0.05

    score = 0.7 - null_penalty + card_boost
    return round(max(0.0, min(1.0, score)), 4)


# ── Signal 12: Check-Type Compatibility (hard filter) ────────────────────


def is_type_compatible(candidate: MetadataAsset, operator: str | None) -> bool:
    """Hard filter: returns False if candidate is definitely incompatible.

    Used as a pre-ranking filter (Signal 12).
    """
    if not operator or not candidate.data_type:
        return True  # can't determine — keep candidate

    compatible_types = _OPERATOR_TYPE_MAP.get(operator)
    if compatible_types is None:
        return True  # operator accepts any type

    ctype = candidate.data_type.lower().strip()
    for t in compatible_types:
        if t in ctype:
            return True

    return False


# ── Aggregate scorer ─────────────────────────────────────────────────────

# Default signal weights (sum = 1.0)
DEFAULT_WEIGHTS = {
    "lexical_match": 0.20,
    "glossary_match": 0.20,
    "dataset_context": 0.15,
    "domain_context": 0.10,
    "lineage_proximity": 0.10,
    "profile_compatibility": 0.10,
    "historical_usage": 0.05,
    "co_occurrence": 0.05,
    "ownership": 0.05,
}

# Map signal name to scoring function
SIGNAL_FUNCTIONS = {
    "lexical_match": score_lexical_match,
    "glossary_match": score_glossary_match,
    "dataset_context": score_dataset_context,
    "domain_context": score_domain_context,
    "lineage_proximity": score_lineage_proximity,
    "profile_compatibility": score_profile_compatibility,
    "historical_usage": score_historical_usage,
    "co_occurrence": score_co_occurrence,
    "ownership": score_ownership,
}


def compute_weighted_score(
    raw_text: str,
    candidate: MetadataAsset,
    context: dict,
    weights: dict[str, float] | None = None,
) -> tuple[float, list[dict]]:
    """Compute weighted overall score and per-signal breakdown.

    Returns (overall_score, [{"signal_name": ..., "score": ..., "evidence": ...}])
    """
    w = weights or DEFAULT_WEIGHTS
    total = 0.0
    breakdown = []

    for signal_name, weight in w.items():
        fn = SIGNAL_FUNCTIONS.get(signal_name)
        if not fn:
            continue

        available = True
        reason = None
        if signal_name == "lineage_proximity":
            lineage = context.get("lineage_distance_by_asset")
            if not lineage or str(candidate.asset_id) not in lineage:
                available = False
                reason = "lineage_unavailable"
        elif signal_name == "co_occurrence":
            co_map = context.get("cooccurrence_by_asset")
            if not co_map or str(candidate.asset_id) not in co_map:
                available = False
                reason = "cooccurrence_unavailable"
        elif signal_name == "historical_usage":
            usage = context.get("usage_count_by_asset") or {}
            recency = context.get("recency_days_by_asset") or {}
            if str(candidate.asset_id) not in usage and str(candidate.asset_id) not in recency:
                available = False
                reason = "history_unavailable"
        elif signal_name == "ownership":
            profiles = context.get("profile_stats_by_asset") or {}
            if str(candidate.asset_id) not in profiles:
                available = False
                reason = "profile_unavailable"

        raw_score = fn(raw_text, candidate, context)
        if not available and signal_name in {
            "lineage_proximity",
            "co_occurrence",
            "historical_usage",
            "ownership",
        }:
            # Neutral fallback for missing metadata-based signals.
            raw_score = 0.5
        raw_score = max(0.0, min(1.0, raw_score))
        weighted = raw_score * weight
        total += weighted
        breakdown.append(
            {
                "signal_name": signal_name,
                "score": round(raw_score, 4),
                "available": available,
                "reason": reason,
                "evidence": f"{signal_name}: {raw_score:.2f} × {weight:.2f} = {weighted:.4f}",
            }
        )

    return round(min(total, 1.0), 4), breakdown
