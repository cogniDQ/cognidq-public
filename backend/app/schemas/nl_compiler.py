"""
NL Rule Compiler Pydantic Schemas.
CompileRequest, CompileResponse, CompiledCheckConfig, etc.
"""

from __future__ import annotations

import enum
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.nl_rule_builder import StructuredIntermediateRepresentation


class CompilationStatus(str, enum.Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class FallbackSuggestion(BaseModel):
    suggested_type: str = Field(..., description="Nearest supported check type")
    reason: str = Field(..., description="Why this is suggested")
    confidence: float = Field(..., ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# F128 — CompilationOptions (replaces Dict[str, Any] on CompileRequest)
# ---------------------------------------------------------------------------


class CompilationOptions(BaseModel):
    """Typed compilation overrides. Extra keys are rejected (extra='forbid')."""

    model_config = ConfigDict(extra="forbid")

    # Compiler-level thresholds / behaviour (used by NLRuleCompiler)
    severity: str = "medium"
    threshold_pass: float | None = Field(None, ge=0, le=100)
    threshold_warn: float | None = Field(None, ge=0, le=100)
    null_handling: str | None = None

    # F128 typed options
    force_dimension: str | None = None
    skip_canonical_bridge: bool = False
    override_severity: str | None = None
    dry_run: bool = False

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-compatible get for backward compatibility with compiler service code."""
        val = getattr(self, key, None)
        return default if val is None else val


# ---------------------------------------------------------------------------
# F128 — Typed check dimension config models (replaces Dict[str, Any] on config field)
# ---------------------------------------------------------------------------


class BaseCheckConfig(BaseModel):
    """Base for all dimension config models. Extra fields are captured (backward compat)."""

    model_config = ConfigDict(extra="allow")

    check_dimension: str = "generic"

    def __getitem__(self, key: str) -> Any:
        dump = self.model_dump()
        if key in dump:
            return dump[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Allow post-construction dict-style mutation (used by _handle_conditional)."""
        if key in self.__class__.model_fields:
            object.__setattr__(self, key, value)
        else:
            if self.__pydantic_extra__ is None:
                object.__setattr__(self, "__pydantic_extra__", {})
            self.__pydantic_extra__[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.model_dump().get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.model_dump()


class CompletenessConfig(BaseCheckConfig):
    check_dimension: Literal["completeness"] = "completeness"
    null_handling: str = "skip"
    include_empty_strings: bool = False
    filter_expression: str | None = None


class ValidityConfig(BaseCheckConfig):
    check_dimension: Literal["validity"] = "validity"
    validation_type: str = "value_in_list"
    allowed_values: list[str | int | float] | None = None
    pattern: str | None = None


class UniquenessCheckConfig(BaseCheckConfig):
    check_dimension: Literal["uniqueness"] = "uniqueness"
    uniqueness_mode: str = "single"
    scope_columns: list[str] | None = None


class ConformityConfig(BaseCheckConfig):
    check_dimension: Literal["conformity"] = "conformity"
    conformity_type: str = "regex"
    standard: str | None = None
    pattern: str | None = None


class ConsistencyConfig(BaseCheckConfig):
    check_dimension: Literal["consistency"] = "consistency"
    consistency_type: str = "cross_field"
    reference_field: str | None = None
    tolerance: float | None = None


class TimelinessConfig(BaseCheckConfig):
    check_dimension: Literal["timeliness"] = "timeliness"
    timeliness_type: str = "freshness"
    max_age: str | None = None
    date_column: str | None = None


class AccuracyConfig(BaseCheckConfig):
    check_dimension: Literal["accuracy"] = "accuracy"
    accuracy_type: str = "numeric"
    reference_column: str | None = None
    tolerance: float | None = None


class ReconciliationConfig(BaseCheckConfig):
    check_dimension: Literal["reconciliation"] = "reconciliation"
    recon_type: str = "count"
    target_dataset_id: str | None = None
    target_column: str | None = None


class GenericCheckConfig(BaseCheckConfig):
    """Catch-all for dimension configs not explicitly modeled."""

    check_dimension: str = "generic"


# Dimension-to-config-class mapping (used by the coercion validator)
_DIM_CONFIG_MAP: dict[str, type] = {
    "completeness": CompletenessConfig,
    "validity": ValidityConfig,
    "uniqueness": UniquenessCheckConfig,
    "conformity": ConformityConfig,
    "consistency": ConsistencyConfig,
    "timeliness": TimelinessConfig,
    "accuracy": AccuracyConfig,
    "reconciliation": ReconciliationConfig,
}

# Union type (no Pydantic discriminator — GenericCheckConfig has str not Literal)
CheckTypeConfig = Union[
    CompletenessConfig,
    ValidityConfig,
    UniquenessCheckConfig,
    ConformityConfig,
    ConsistencyConfig,
    TimelinessConfig,
    AccuracyConfig,
    ReconciliationConfig,
    GenericCheckConfig,
]


def _coerce_check_config(v: Any) -> Any:
    """Coerce a dict to the appropriate CheckTypeConfig subclass."""
    if isinstance(v, dict):
        dim = v.get("check_dimension", "generic")
        cfg_cls = _DIM_CONFIG_MAP.get(dim, GenericCheckConfig)
        return cfg_cls(**v)
    return v


# ---------------------------------------------------------------------------
# F128 — CanonicalRuleOutput (replaces Optional[Dict[str, Any]] on canonical_rule)
# ---------------------------------------------------------------------------


class CanonicalRuleOutput(BaseModel):
    """Typed canonical rule bridge output (F128). Backward-compat via __getitem__."""

    model_config = ConfigDict(extra="allow")

    # F128 typed fields
    rule_type: str | None = None
    subject: str | None = None
    operator: str | None = None
    severity: str = "medium"
    threshold_pass: float | None = None
    threshold_warn: float | None = None
    tags: list[str] = Field(default_factory=list)

    def __getitem__(self, key: str) -> Any:
        """Dict-style access for backward compatibility (e.g. canonical_rule['dimension'])."""
        dump = self.model_dump()
        if key in dump:
            return dump[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self.model_dump().get(key, default)


# ---------------------------------------------------------------------------
# Core compiler output models
# ---------------------------------------------------------------------------


class CompiledCheckConfig(BaseModel):
    check_type: str = Field(..., description="DQ dimension (completeness, validity, etc.)")
    subtype: str = Field(..., description="Dimension subtype (null, range, regex, etc.)")
    dataset_id: str | None = Field(None, description="Resolved dataset UUID")
    rule_name: str = Field(..., description="Auto-generated rule name from NL text")
    severity: str = Field(default="medium", description="Rule severity")
    description: str | None = Field(None, description="Human-readable description")
    config: CheckTypeConfig = Field(
        default_factory=GenericCheckConfig, description="Check-specific config (typed)"
    )
    canonical_rule: CanonicalRuleOutput | None = Field(
        None, description="Canonical rule definition for RuleCompiler"
    )
    obligation_group_id: str | None = Field(
        None, description="Shared UUID grouping related obligations in a compound rule"
    )
    obligation_logic: str | None = Field(
        None, description="AND | OR | INDEPENDENT — logic connecting obligations in the group"
    )
    rule_id: str | None = Field(
        None,
        description=(
            "Originating rule UUID. When set the flow generator stamps it on the "
            "produced check node so rule↔flow bidirectional sync can find the node."
        ),
    )

    @field_validator("config", mode="before")
    @classmethod
    def _coerce_config(cls, v: Any) -> Any:
        return _coerce_check_config(v)

    @field_validator("canonical_rule", mode="before")
    @classmethod
    def _coerce_canonical_rule(cls, v: Any) -> Any:
        if isinstance(v, dict):
            return CanonicalRuleOutput(**v)
        return v


class ValidationError(BaseModel):
    field: str = Field(..., description="Field that failed validation")
    message: str = Field(..., description="Error message")
    code: str = Field(..., description="Error code")


class CompileRequest(BaseModel):
    resolved_rule: StructuredIntermediateRepresentation = Field(
        ..., description="SIR with resolved entities"
    )
    compilation_options: CompilationOptions = Field(
        default_factory=CompilationOptions, description="Typed compilation overrides"
    )

    @field_validator("compilation_options", mode="before")
    @classmethod
    def _coerce_options(cls, v: Any) -> Any:
        """Accept plain dicts for backward compatibility — will be validated as CompilationOptions."""
        if isinstance(v, dict):
            return CompilationOptions(**v)
        return v


class CompileResponse(BaseModel):
    status: CompilationStatus = Field(..., description="Compilation result status")
    compiled_configs: list[CompiledCheckConfig] = Field(
        default_factory=list, description="Compiled check configs"
    )
    warnings: list[str] = Field(default_factory=list, description="Non-fatal compilation warnings")
    validation_errors: list[ValidationError] = Field(
        default_factory=list, description="Validation errors if status is error"
    )
    fallback_suggestions: list[FallbackSuggestion] = Field(
        default_factory=list, description="Suggestions if unsupported"
    )
    rejection_reason: str | None = Field(None, description="Reason for rejection if unsupported")
