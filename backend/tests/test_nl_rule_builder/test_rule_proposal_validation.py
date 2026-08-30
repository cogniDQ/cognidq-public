"""
Tests for the NL Rule Builder Reliability spec hard gate
(`RuleProposalValidationService`).

These tests cover the acceptance scenarios defined in §18 of the spec:
- A1 — valid simple rule
- A2 — missing dataset
- A3 — unknown column
- A4 — type-incompatible check
- A5 — missing required parameter (allowed_values)
- A6 — unsupported check-type / unknown intent
- A7 — compound rule where one obligation fails
"""

from __future__ import annotations

import uuid

import pytest
from app.schemas.nl_rule_builder import (
    CheckConfigOutput,
    RuleType,
    SIREntity,
    StructuredIntermediateRepresentation,
    ThresholdConfig,
)
from app.services.nl_rule_builder.dataset_metadata import ColumnMeta, DatasetMeta
from app.services.nl_rule_builder.rule_proposal_validation import (
    RuleProposalValidationService,
)


@pytest.fixture
def customers_meta() -> DatasetMeta:
    """Synthetic dataset with mixed-type columns used across scenarios."""
    return DatasetMeta(
        dataset_id=str(uuid.uuid4()),
        dataset_name="customers",
        schema_name="public",
        description="Customer master data",
        business_domain="customer",
        columns=[
            ColumnMeta(
                name="customer_id",
                data_type="varchar",
                nullable=False,
                description="primary id",
                is_key_candidate=True,
            ),
            ColumnMeta(
                name="email",
                data_type="varchar",
                nullable=True,
                description="contact email",
            ),
            ColumnMeta(
                name="age",
                data_type="integer",
                nullable=True,
                description="age in years",
            ),
            ColumnMeta(
                name="status",
                data_type="varchar",
                nullable=True,
                description="status code",
            ),
        ],
    )


def _thresholds() -> ThresholdConfig:
    return ThresholdConfig(
        threshold_pass=1.0,
        threshold_warn=0.95,
        null_handling="skip",
        include_empty_strings=False,
    )


def _sir(
    rule_type: str,
    column: str,
    *,
    dimension: str | None = None,
    subtype: str | None = None,
    confidence: float = 0.95,
    operator: str | None = None,
) -> StructuredIntermediateRepresentation:
    return StructuredIntermediateRepresentation(
        schema_version="1.0",
        rule_type=RuleType(rule_type),
        subject=SIREntity(raw_text=column, resolved_column=column),
        operator=operator,
        conditions=[],
        constraints=[],
        confidence=confidence,
        requires_disambiguation=False,
        parse_warnings=[],
        check_dimension=dimension,
        check_subtype=subtype,
    )


def _cc(
    dimension: str, subtype: str, columns: list[str], dataset_id, config: dict | None = None
) -> CheckConfigOutput:
    return CheckConfigOutput(
        check_dimension=dimension,
        check_subtype=subtype,
        columns=columns,
        dataset_id=str(dataset_id),
        dataset_name="customers",
        config=config or {},
        thresholds=_thresholds(),
        severity="medium",
        rule_name=f"test_{dimension}_{subtype}",
    )


class TestRuleProposalValidationService:
    def setup_method(self) -> None:
        self.svc = RuleProposalValidationService()

    # ── A1 — valid simple null check ──
    def test_valid_not_null_passes(self, customers_meta):
        sir = _sir("not_null", "email", dimension="completeness", subtype="not_null")
        cc = _cc("completeness", "not_null", ["email"], customers_meta.dataset_id)
        validation, refinement, proposal = self.svc.validate(sir, customers_meta, [cc])

        assert validation.dq_flow_convertible is True
        assert refinement is None
        assert proposal is not None
        assert proposal["dq_flow_convertible"] is True
        assert proposal["column_name"] == "email"
        assert proposal["dataset_name"] == "customers"

    # ── A2 — missing dataset ──
    def test_missing_dataset_blocks(self, customers_meta):
        sir = _sir("not_null", "email", dimension="completeness", subtype="not_null")
        validation, refinement, proposal = self.svc.validate(sir, None, None)

        assert validation.dq_flow_convertible is False
        assert validation.dataset_exists is False
        assert proposal is None
        assert refinement is not None
        assert refinement.reason == "missing_dataset"

    # ── A3 — unknown column ──
    def test_unknown_column_blocks_and_suggests(self, customers_meta):
        sir = _sir("not_null", "emial", dimension="completeness", subtype="not_null")
        validation, refinement, proposal = self.svc.validate(sir, customers_meta, None)

        assert validation.dq_flow_convertible is False
        assert validation.column_exists is False
        assert proposal is None
        assert refinement is not None
        assert refinement.reason in {"unknown_column", "ambiguous_column"}
        # difflib should suggest the close match "email"
        sugg_values = [s.value for s in (refinement.suggestions or [])]
        assert "email" in sugg_values

    # ── A4 — type-incompatible check (numeric range on a string column) ──
    def test_type_incompatible_blocks(self, customers_meta):
        sir = _sir(
            "numeric_range",
            "email",
            dimension="validity",
            subtype="range",
            operator="between",
        )
        cc = _cc(
            "validity",
            "range",
            ["email"],
            customers_meta.dataset_id,
            config={"min_value": 0, "max_value": 100},
        )
        validation, refinement, proposal = self.svc.validate(sir, customers_meta, [cc])

        assert validation.dq_flow_convertible is False
        assert validation.type_compatible is False
        assert proposal is None
        assert refinement is not None
        assert refinement.reason == "type_incompatible"

    # ── A5 — missing allowed_values for value_in_list ──
    def test_value_in_list_missing_allowed_values_blocks(self, customers_meta):
        sir = _sir("value_in_list", "status", dimension="validity", subtype="allowed_values")
        cc = _cc(
            "validity",
            "allowed_values",
            ["status"],
            customers_meta.dataset_id,
            config={},  # missing allowed_values
        )
        validation, refinement, proposal = self.svc.validate(sir, customers_meta, [cc])

        assert validation.dq_flow_convertible is False
        assert validation.required_params_present is False
        assert proposal is None
        assert refinement is not None
        assert refinement.reason in {"missing_allowed_values", "missing_threshold"}

    # ── A6 — unknown rule type ──
    def test_unknown_rule_type_blocks(self, customers_meta):
        sir = _sir("unknown", "email")
        validation, refinement, proposal = self.svc.validate(sir, customers_meta, None)

        assert validation.dq_flow_convertible is False
        assert validation.check_type_supported is False
        assert proposal is None
        assert refinement is not None
        assert refinement.reason == "unsupported_check_type"

    # ── A7 — compound rule where one obligation is invalid ──
    def test_compound_one_obligation_invalid_blocks(self, customers_meta):
        good = _sir("not_null", "email", dimension="completeness", subtype="not_null")
        bad = _sir("not_null", "nonexistent_col", dimension="completeness", subtype="not_null")
        compound = StructuredIntermediateRepresentation(
            schema_version="1.0",
            rule_type=RuleType("not_null"),
            subject=SIREntity(raw_text="multiple"),
            conditions=[],
            constraints=[],
            confidence=0.9,
            requires_disambiguation=False,
            parse_warnings=[],
            is_compound=True,
            obligation_logic="AND",
            obligations=[good, bad],
        )

        validation, refinement, proposal = self.svc.validate(compound, customers_meta, None)

        assert validation.dq_flow_convertible is False
        assert proposal is None
        assert refinement is not None
        # message should reference the failing obligation
        assert "Obligation" in refinement.message or "obligation" in refinement.message.lower()
