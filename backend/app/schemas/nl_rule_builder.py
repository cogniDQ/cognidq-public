"""
NL Rule Builder Pydantic Schemas
Structured Intermediate Representation (SIR) and API request/response schemas.
"""

import enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RuleType(str, enum.Enum):
    """Supported NL rule types — maps to dq_expected_results check dimensions."""

    # Completeness
    NOT_NULL = "not_null"
    NULL_CHECK = "null_check"
    EMPTY_CHECK = "empty_check"
    PLACEHOLDER_CHECK = "placeholder_check"
    MULTI_FIELD_COMPLETENESS = "multi_field_completeness"
    CONDITIONAL_COMPLETENESS = "conditional_completeness"
    GROUP_COMPLETENESS = "group_completeness"
    POPULATION_COMPLETENESS = "population_completeness"
    # Uniqueness
    UNIQUENESS = "uniqueness"
    COMPOSITE_UNIQUENESS = "composite_uniqueness"
    SCOPED_UNIQUENESS = "scoped_uniqueness"
    FUZZY_UNIQUENESS = "fuzzy_uniqueness"
    TEMPORAL_UNIQUENESS = "temporal_uniqueness"
    # Conformity
    REGEX_FORMAT = "regex_format"
    LENGTH_CHECK = "length_check"
    CASE_CHECK = "case_check"
    CHARSET_CHECK = "charset_check"
    STANDARD_FORMAT = "standard_format"
    STRUCTURAL_PATTERN = "structural_pattern"
    # Consistency
    COLUMN_COMPARISON = "column_comparison"
    FORMULA_CHECK = "formula_check"
    TEMPORAL_CONSISTENCY = "temporal_consistency"
    INTER_RECORD = "inter_record"
    AGGREGATION_CONSISTENCY = "aggregation_consistency"
    # Validity
    VALUE_IN_LIST = "value_in_list"
    NUMERIC_RANGE = "numeric_range"
    DATE_LOGIC = "date_logic"
    REFERENCE_LOOKUP = "reference_lookup"
    BUSINESS_RULE = "business_rule"
    CROSS_FIELD = "cross_field"
    NEGATIVE_PATTERN = "negative_pattern"
    REGEX_VALIDATION = "regex_validation"
    # Accuracy
    REFERENCE_COMPARISON = "reference_comparison"
    TOLERATED_DEVIATION = "tolerated_deviation"
    STATISTICAL_OUTLIER = "statistical_outlier"
    DERIVED_VALUE = "derived_value"
    # Timeliness
    FRESHNESS = "freshness"
    RECORD_AGE = "record_age"
    LATENCY = "latency"
    PROCESSING_DELAY = "processing_delay"
    DELIVERY_WINDOW = "delivery_window"
    HEARTBEAT = "heartbeat"
    # Reconciliation
    RECORD_COUNT = "record_count"
    ONE_TO_ONE = "one_to_one"
    FIELD_LEVEL_RECON = "field_level_recon"
    AGGREGATE_RECON = "aggregate_recon"
    TOLERANCE_RECON = "tolerance_recon"
    MISSING_EXTRA = "missing_extra"
    # Backward compat aliases
    DATE_COMPARISON = "date_comparison"
    NUMERIC_THRESHOLD = "numeric_threshold"
    CONDITIONAL_RULE = "conditional_rule"
    ARITHMETIC_COMPARISON = "arithmetic_comparison"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# F128 — Typed condition value (replaces Any)
# ---------------------------------------------------------------------------

# Scalar or flat-list value for SIRCondition — nested objects not allowed.
ConditionValue = Union[str, int, float, list[str | int | float]]


def _max_nesting_depth(conditions: list, depth: int = 0) -> int:
    """Recursively compute the maximum nesting depth of a condition list."""
    if not conditions:
        return depth
    return max(_max_nesting_depth(c.nested_conditions, depth + 1) for c in conditions)


# ---------------------------------------------------------------------------
# F128 — SIRConstraint discriminated union
# ---------------------------------------------------------------------------


class ValueInListConstraint(BaseModel):
    constraint_type: Literal["value_in_list"] = "value_in_list"
    allowed_values: list[str | int | float] = Field(..., description="Allowed values for the check")
    case_sensitive: bool = True


class RangeConstraint(BaseModel):
    constraint_type: Literal["range"] = "range"
    min: float | None = None
    max: float | None = None
    inclusive: bool = True


class RegexConstraint(BaseModel):
    constraint_type: Literal["regex"] = "regex"
    pattern: str = Field(..., description="Regex pattern string")


class LengthConstraint(BaseModel):
    constraint_type: Literal["length"] = "length"
    min_length: int | None = None
    max_length: int | None = None


class GenericConstraint(BaseModel):
    """Catch-all for constraint shapes not yet explicitly modeled."""

    model_config = ConfigDict(extra="allow")
    constraint_type: str = "generic"
    data: dict[str, Any] = Field(default_factory=dict)


# Discriminated union — infer_constraint_type helper adds discriminator at parse boundary
SIRConstraint = Union[
    Annotated[ValueInListConstraint, Field(discriminator="constraint_type")],
    Annotated[RangeConstraint, Field(discriminator="constraint_type")],
    Annotated[RegexConstraint, Field(discriminator="constraint_type")],
    Annotated[LengthConstraint, Field(discriminator="constraint_type")],
    GenericConstraint,
]


def _infer_constraint_type(d: dict) -> str:
    """Infer constraint_type from dict keys for backward compatibility."""
    if "allowed_values" in d:
        return "value_in_list"
    if "pattern" in d and "min_length" not in d and "max_length" not in d:
        return "regex"
    if "min_length" in d or "max_length" in d:
        return "length"
    if "min" in d or "max" in d:
        return "range"
    return "generic"


# ---------------------------------------------------------------------------
# F128 — DecompositionSummary (typed; replaces Optional[dict] on ParseRuleResponse)
# ---------------------------------------------------------------------------


class DecompositionSummary(BaseModel):
    """Summary of compound rule decomposition output."""

    count: int = Field(..., ge=1, description="Number of obligations detected")
    logic: str | None = Field(
        None, description="AND | OR | INDEPENDENT — logic connecting obligations"
    )
    obligations: list[str] = Field(
        default_factory=list, description="List of obligation subject descriptions"
    )


# ---------------------------------------------------------------------------
# Core entity/scope models
# ---------------------------------------------------------------------------


class SIREntity(BaseModel):
    """An entity reference extracted from NL text."""

    raw_text: str = Field(..., description="Original text from the NL input")
    resolved_column: str | None = Field(
        None, description="Physical column name (set by resolution engine, not parser)"
    )
    resolved_dataset: str | None = Field(
        None, description="Physical dataset/table (set by resolution engine)"
    )
    column_id: str | None = Field(None, description="Platform column ID (set by resolution engine)")
    dataset_id: str | None = Field(
        None, description="Platform dataset ID (set by resolution engine)"
    )
    matched_glossary_term_id: str | None = Field(
        None, description="Glossary term ID matched during parsing"
    )


class GlossaryContextItem(BaseModel):
    """Glossary term details attached to parse output when a match is found."""

    term_id: str = Field(..., description="Glossary term UUID")
    business_name: str = Field(..., description="Business glossary term name")
    match_reason: str = Field(..., description="Where the match was detected")


class SIRScope(BaseModel):
    """Scope clues extracted from context."""

    dataset_hint: str | None = Field(None, description="Dataset ID or name hint")
    domain_hint: str | None = Field(None, description="Business domain hint")
    source_system_hint: str | None = Field(None, description="Source system hint")


class SIRCondition(BaseModel):
    """A condition clause for conditional rules."""

    field: SIREntity = Field(..., description="The field to check in the condition")
    operator: str = Field(..., description="Condition operator (equals, not_equals, in, etc.)")
    value: Any = Field(..., description="Expected value(s) for the condition")
    logic_operator: str | None = Field(
        None, description="AND | OR joining this condition to the next"
    )
    nested_conditions: list["SIRCondition"] = Field(
        default_factory=list,
        description="Inner conditions for nested IF-THEN patterns (max 3 levels)",
    )

    @field_validator("value", mode="before")
    @classmethod
    def _validate_condition_value(cls, v: Any) -> Any:
        if isinstance(v, dict):
            raise ValueError(
                "SIRCondition.value must be a scalar (str/int/float) or flat list, not a dict object"
            )
        if isinstance(v, list):
            for item in v:
                if isinstance(item, (dict, list)):
                    raise ValueError(
                        "SIRCondition.value list items must be scalar (str, int, or float), not nested"
                    )
        return v

    @field_validator("nested_conditions", mode="after")
    @classmethod
    def _validate_depth(cls, v: list["SIRCondition"]) -> list["SIRCondition"]:
        if _max_nesting_depth(v) > 3:
            raise ValueError("nested_conditions exceeds maximum depth of 3 levels")
        return v


SIRCondition.model_rebuild()


class ClarifyingQuestion(BaseModel):
    """A question the LLM needs answered to parse the rule accurately."""

    field: str = Field(
        ...,
        description="What the question is about: dataset, column, check_type, threshold, scope, etc.",
    )
    question: str = Field(..., description="Human-readable question for the user")
    options: list[str] = Field(
        default_factory=list, description="Suggested options (empty if free-text)"
    )
    required: bool = Field(default=True, description="Whether the answer is required to proceed")
    # E1 — typed clarifying questions
    answer_type: Literal["single_select", "multi_select", "free_text", "numeric"] = Field(
        default="free_text",
        description="How the user should answer: single_select | multi_select | free_text | numeric",
    )
    min_value: float | None = Field(None, description="Inclusive lower bound for numeric answers")
    max_value: float | None = Field(None, description="Inclusive upper bound for numeric answers")
    rationale: str | None = Field(
        None, description="Why this question is being asked (parser explanation)"
    )


class ClarificationTurn(BaseModel):
    """F1 — one Q/A pair in the multi-turn clarification history."""

    field: str = Field(..., description="Field key the question was asked about")
    question: str = Field(..., description="The question text the parser asked")
    answer: str = Field(..., description="The user's answer to that question")
    answered_at: str | None = Field(
        None, description="ISO-8601 timestamp the answer was submitted (client-supplied)"
    )


class StructuredIntermediateRepresentation(BaseModel):
    """The core SIR schema — constrained parse output from LLM."""

    schema_version: str = Field(default="1.0", description="SIR schema version")
    rule_type: RuleType = Field(..., description="Classified rule type")
    # Subtype capture — populated either directly by the LLM (preferred) or
    # derived from rule_type via RULE_TYPE_MAP. Persisted in sir_json so the
    # compiler / flow generator can build a fully configured check node.
    check_dimension: str | None = Field(
        None,
        description="DQ dimension (completeness, validity, conformity, …). When None, derived from rule_type.",
    )
    check_subtype: str | None = Field(
        None,
        description="DQ subtype within the dimension (e.g. null, range, regex, scoped). When None, derived from rule_type.",
    )
    subtype_config: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Subtype-specific configuration captured during parsing (e.g. min_value/max_value for "
            "validity/range, allowed_values for validity/allowed_values, scope_columns for "
            "uniqueness/scoped). Keys must use snake_case and match `subtype_schema.SUBTYPE_INVENTORY`."
        ),
    )
    subject: SIREntity = Field(..., description="Primary entity (left side)")
    operator: str | None = Field(None, description="Comparison/check operator")
    object: SIREntity | None = Field(
        None, description="Secondary entity (right side, for comparisons)"
    )
    scope: SIRScope = Field(default_factory=SIRScope, description="Scope context clues")
    conditions: list[SIRCondition] = Field(default_factory=list, description="Conditional clauses")
    constraints: list[Any] = Field(
        default_factory=list, description="Additional constraints (value lists, ranges, etc.)"
    )
    confidence: float = Field(..., description="Parse confidence score")
    requires_disambiguation: bool = Field(
        default=False, description="Whether user confirmation is needed"
    )
    parse_warnings: list[str] = Field(
        default_factory=list, description="Warnings about parse quality"
    )
    clarifying_questions: list[ClarifyingQuestion] = Field(
        default_factory=list, description="Questions the LLM needs answered"
    )
    clarification_context: str | None = Field(
        None, description="Explanation of what the parser tried and why it is asking again"
    )
    clarification_answers: dict[str, Any] | None = Field(
        None,
        description="Answers to previously-emitted clarifying_questions, keyed by ClarifyingQuestion.field. "
        "Populated by the confirm endpoint when the user supplies adjustment values for clarifier fields.",
    )
    glossary_context: list[GlossaryContextItem] = Field(
        default_factory=list, description="Matched glossary terms from parser stage"
    )
    is_compound: bool = Field(
        default=False, description="True if input contains multiple obligations"
    )
    obligation_logic: str | None = Field(
        None, description="AND | OR | INDEPENDENT — logic connecting obligations"
    )
    obligations: list["StructuredIntermediateRepresentation"] = Field(
        default_factory=list,
        description="Atomic SIRs when is_compound=True. Empty for single-obligation inputs.",
    )
    # F126 inline extraction results (populated by _apply_inline_extraction)
    inline_severity: str | None = Field(
        None, description="Severity extracted from inline NL text (e.g. 'with severity critical')"
    )
    threshold_pass: float | None = Field(
        None, ge=0, le=100, description="Pass threshold % extracted inline"
    )
    threshold_warn: float | None = Field(
        None, ge=0, le=100, description="Warn threshold % extracted inline"
    )

    # F128 — rule_type normalization + confidence clamping
    @field_validator("rule_type", mode="before")
    @classmethod
    def _normalize_rule_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            lowered = v.lower().strip()
            # Try matching by enum value (canonical form)
            for member in RuleType:
                if member.value == lowered:
                    return lowered
            # Try matching by enum name (e.g. "NOT_NULL" → RuleType.NOT_NULL → value "not_null")
            upper = v.upper().strip()
            for member in RuleType:
                if member.name == upper:
                    return member.value
            # Return as-is and let Pydantic raise
            return lowered
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: Any) -> Any:
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
        return v

    @field_validator("constraints", mode="before")
    @classmethod
    def _normalize_constraints(cls, v: Any) -> Any:
        """Add constraint_type discriminator to dicts that lack it (backward compat)."""
        if not isinstance(v, list):
            return v
        result = []
        for item in v:
            if isinstance(item, dict) and "constraint_type" not in item:
                item = {**item, "constraint_type": _infer_constraint_type(item)}
            result.append(item)
        return result


StructuredIntermediateRepresentation.model_rebuild()


# --- API Request/Response Schemas ---


class ParseRuleRequest(BaseModel):
    """Request body for POST /rule-builder/parse."""

    rule_text: str = Field(
        ..., min_length=1, max_length=2000, description="Natural language rule text"
    )
    dataset_id: str | None = Field(None, description="Optional dataset context UUID")
    domain: str | None = Field(None, max_length=200, description="Optional business domain")
    source_system: str | None = Field(None, max_length=200, description="Optional source system")
    rule_category: str | None = Field(None, max_length=100, description="Optional rule category")
    severity: str | None = Field(None, description="Optional severity level")
    tags: list[str] | None = Field(None, max_length=20, description="Optional tags")
    clarification_answers: dict[str, str] | None = Field(
        None, description="Answers to previous clarifying questions, keyed by field name"
    )
    # F1 — multi-turn clarification history (oldest → newest)
    clarification_history: list[ClarificationTurn] | None = Field(
        None,
        description="Prior Q/A turns from this clarification thread (oldest first)",
    )

    @field_validator("rule_text")
    @classmethod
    def validate_rule_text(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("rule_text must not be empty or whitespace-only")
        return stripped

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str | None) -> str | None:
        if v is not None and v not in ("critical", "high", "medium", "low", "info"):
            raise ValueError("severity must be one of: critical, high, medium, low, info")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            if len(v) > 20:
                raise ValueError("Maximum 20 tags allowed")
            for tag in v:
                if len(tag) > 50:
                    raise ValueError("Each tag must be at most 50 characters")
        return v


class ThresholdConfig(BaseModel):
    """Threshold configuration for a check."""

    threshold_pass: float = Field(default=100, ge=0, le=100)
    threshold_warn: float = Field(default=95, ge=0, le=100)
    null_handling: str = Field(default="skip", description="skip|fail|impute")
    include_empty_strings: bool = Field(default=False)


class CheckConfigOutput(BaseModel):
    """Full check node config matching dq_expected_results structure."""

    check_dimension: str = Field(
        ..., description="Check dimension (completeness, uniqueness, etc.)"
    )
    check_subtype: str = Field(..., description="Subtype (null, empty, exact, regex, etc.)")
    columns: list[str] = Field(default_factory=list, description="Target column(s)")
    dataset_id: str | None = Field(None, description="Resolved dataset UUID")
    dataset_name: str | None = Field(None, description="Dataset name")
    config: dict[str, Any] = Field(default_factory=dict, description="Full node-specific config")
    thresholds: ThresholdConfig = Field(
        default_factory=lambda: ThresholdConfig(), description="Threshold configuration"
    )
    severity: str = Field(default="medium")
    rule_name: str = Field(default="", description="Auto-generated rule name")
    description: str | None = Field(None)


class DetectedDataset(BaseModel):
    """A dataset detected from the rule text."""

    dataset_id: str | None = Field(None)
    dataset_name: str = Field(...)
    data_source_name: str | None = Field(None, description="Data source the dataset belongs to")
    match_score: float = Field(default=0.0, ge=0.0, le=1.0)
    match_reason: str = Field(default="")


class DetectedColumn(BaseModel):
    """A column detected from the rule text."""

    raw_text: str = Field(...)
    resolved_name: str | None = Field(None)
    dataset_id: str | None = Field(None)
    dataset_name: str | None = Field(None)
    data_type: str | None = Field(None)
    role: str = Field(default="subject", description="subject|object|condition|scope")


class ParseExplanationItem(BaseModel):
    """Business-facing explanation entry for parser decisions."""

    topic: str = Field(..., description="Decision topic: rule_type, subject, scope, glossary, etc.")
    decision: str = Field(..., description="What was decided")
    evidence: list[str] = Field(
        default_factory=list, description="Signals/evidence used for this decision"
    )
    confidence_impact: float = Field(0.0, ge=-1.0, le=1.0)
    caveat: str | None = None


class ParseTrustSummary(BaseModel):
    """Compact trust indicator payload for parser outputs."""

    confidence_band: str = Field(..., description="high|medium|low")
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    caveats: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    recommendation: str = Field(default="")


class RefinementSuggestion(BaseModel):
    """A single suggested refinement candidate (column, dataset, check type, etc.)."""

    type: str = Field(..., description="dataset | column | check_type | operator | value")
    value: str = Field(..., description="The suggested value")
    label: str | None = Field(None, description="Display label, defaults to value")
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    rationale: str | None = None


class RefinementGuidance(BaseModel):
    """Structured response when the parser cannot produce a valid rule proposal."""

    reason: str = Field(
        ...,
        description=(
            "Machine-readable refinement reason: missing_dataset | ambiguous_dataset | "
            "unknown_dataset | missing_column | unknown_column | ambiguous_column | "
            "unsupported_check_type | missing_threshold | missing_allowed_values | "
            "type_incompatible | invalid_operator | low_confidence | unknown_intent | "
            "invalid_rule_structure"
        ),
    )
    message: str = Field(..., description="Human-readable explanation for the user")
    suggestions: list[RefinementSuggestion] = Field(
        default_factory=list,
        description="Ranked alternative values the user can pick from",
    )
    next_question: str | None = Field(
        None,
        description="The single next question the UI should foreground",
    )
    field: str | None = Field(
        None,
        description="Which field of the rule the refinement targets (dataset, column, check_type, threshold, allowed_values…)",
    )


class ProposalValidation(BaseModel):
    """Hard-gate validation result. The proposal can only be persisted/submitted
    when ``dq_flow_convertible`` is True. Mirrored on the frontend's "Create Rule"
    button enable-state."""

    dataset_exists: bool = False
    column_exists: bool = False
    check_type_supported: bool = False
    operator_supported: bool = True
    type_compatible: bool = True
    required_params_present: bool = False
    dq_flow_convertible: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    incompatible_fields: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ParseRuleResponse(BaseModel):
    """Response body for POST /rule-builder/parse."""

    request_id: str = Field(..., description="Parse request UUID")
    parse_result_id: str | None = Field(
        None, description="Parse result UUID (used for validate/create-flow)"
    )
    parsed_rule: StructuredIntermediateRepresentation | None = Field(
        None, description="Parsed SIR (null if cannot_interpret)"
    )
    status: str = Field(
        ..., description="Parse status: parsed, needs_clarification, cannot_interpret, parse_error"
    )
    # Spec §10/§11 — top-level refinement contract.
    proposal_status: str | None = Field(
        None,
        description="High-level proposal status: valid_rule_proposal | needs_refinement | invalid_request",
    )
    rule_proposal: dict[str, Any] | None = Field(
        None,
        description=(
            "Flat, frontend-ready rule proposal payload (dataset_id, column_name, "
            "check_type, operator, severity, …) — only populated when "
            "proposal_status == 'valid_rule_proposal'."
        ),
    )
    validation: ProposalValidation | None = Field(
        None,
        description="Structural validation result. dq_flow_convertible must be True before persistence.",
    )
    refinement: RefinementGuidance | None = Field(
        None,
        description="Populated when proposal_status != 'valid_rule_proposal'.",
    )
    reason: str | None = Field(None, description="Reason for cannot_interpret or parse_error")
    suggestions: list[str] = Field(default_factory=list, description="Suggestions for the user")
    clarifying_questions: list[ClarifyingQuestion] = Field(
        default_factory=list, description="Questions the user should answer before re-parsing"
    )
    clarification_context: str | None = Field(
        None, description="Explanation of what the parser tried and why it is asking again"
    )
    check_configs: list[CheckConfigOutput] | None = Field(
        None, description="Generated check node configs matching dq_expected_results"
    )
    detected_datasets: list[DetectedDataset] | None = Field(
        None, description="Auto-detected datasets from rule text"
    )
    detected_columns: list[DetectedColumn] | None = Field(
        None, description="Detected columns from rule text"
    )
    explainability: list[ParseExplanationItem] = Field(default_factory=list)
    trust_summary: ParseTrustSummary | None = None
    decomposition_summary: DecompositionSummary | None = Field(
        None, description="Always present. count, logic, obligations list describing decomposition."
    )


class ValidateParseRequest(BaseModel):
    """Request to validate a parse result."""

    parse_result_id: str = Field(..., description="Parse result UUID to validate")
    validated: bool = Field(default=True, description="Whether the parse is accepted")
    adjustments: dict[str, Any] | None = Field(
        None, description="User adjustments to the parse output"
    )


class ValidateParseResponse(BaseModel):
    """Response after validating a parse result."""

    parse_result_id: str
    validated: bool
    validated_at: str
    check_configs: list[CheckConfigOutput]
    rule_id: str | None = Field(None, description="Created DQ rule ID if validated")


class SavedParseEntry(BaseModel):
    """A saved parse entry for listing."""

    request_id: str
    parse_result_id: str
    rule_text: str
    rule_type: str
    confidence: float
    status: str
    validated: bool
    check_configs: list[CheckConfigOutput] | None = None
    created_at: str
    validated_at: str | None = None


class SavedParsesListResponse(BaseModel):
    """List response for saved parses."""

    items: list[SavedParseEntry]
    total: int
    page: int
    page_size: int
