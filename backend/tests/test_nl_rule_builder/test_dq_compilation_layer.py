"""
Tests for the DQ Rule Compilation Layer — canonical inventory enforcement,
repair pass, and flow compatibility validator.

These cover what the legacy hardcoded `_REQUIRED_PER_SUBTYPE` table missed.
Every previously-silent-pass subtype is now tested.
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
from app.services.nl_compiler.subtype_schema import (
    SUBTYPE_ALIASES,
    apply_subtype_defaults,
    is_canonical_subtype,
    resolve_subtype_alias,
)
from app.services.nl_rule_builder.dataset_metadata import ColumnMeta, DatasetMeta
from app.services.nl_rule_builder.flow_compatibility import (
    FlowCompatibilityValidator,
)
from app.services.nl_rule_builder.rule_config_repair import RuleConfigRepairService
from app.services.nl_rule_builder.rule_proposal_validation import (
    RuleProposalValidationService,
)

# ── fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def orders_meta() -> DatasetMeta:
    return DatasetMeta(
        dataset_id=str(uuid.uuid4()),
        dataset_name="orders",
        schema_name="public",
        columns=[
            ColumnMeta(name="order_id", data_type="varchar", nullable=False, is_key_candidate=True),
            ColumnMeta(name="customer_id", data_type="varchar", nullable=False),
            ColumnMeta(name="status", data_type="varchar", nullable=True),
            ColumnMeta(name="total_amount", data_type="numeric", nullable=False),
            ColumnMeta(name="created_at", data_type="timestamp", nullable=False),
            ColumnMeta(name="updated_at", data_type="timestamp", nullable=True),
        ],
    )


def _thr() -> ThresholdConfig:
    return ThresholdConfig()


def _sir(
    rule_type: str,
    column: str,
    *,
    dimension=None,
    subtype=None,
    operator=None,
    confidence: float = 0.95,
    subtype_config: dict | None = None,
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
        subtype_config=subtype_config or {},
    )


def _cc(
    dimension: str, subtype: str, columns: list[str], dataset_id, config: dict | None = None
) -> CheckConfigOutput:
    return CheckConfigOutput(
        check_dimension=dimension,
        check_subtype=subtype,
        columns=columns,
        dataset_id=str(dataset_id),
        dataset_name="orders",
        config=config or {},
        thresholds=_thr(),
        severity="medium",
        rule_name=f"{dimension}_{subtype}",
    )


# ── canonical inventory enforcement ─────────────────────────────────────


class TestSubtypeAliasResolution:
    def test_alias_not_null_resolves_to_null(self):
        assert resolve_subtype_alias("completeness", "not_null") == "null"

    def test_alias_value_in_list_resolves_to_allowed_values(self):
        assert resolve_subtype_alias("validity", "value_in_list") == "allowed_values"

    def test_canonical_pair_unchanged(self):
        assert resolve_subtype_alias("validity", "range") == "range"

    def test_unknown_pair_unchanged(self):
        # When alias is unknown, return input verbatim so callers can
        # detect the unknown case.
        assert resolve_subtype_alias("validity", "made_up") == "made_up"

    def test_aliases_table_resolves_to_canonical_pairs(self):
        # Every alias in the table must map to a canonical inventory pair.
        for (dim, _alias), canonical in SUBTYPE_ALIASES.items():
            assert is_canonical_subtype(dim, canonical), (
                f"alias maps to non-canonical pair {dim}/{canonical}"
            )


# ── repair service ──────────────────────────────────────────────────────


class TestRuleConfigRepairService:
    def setup_method(self) -> None:
        self.svc = RuleConfigRepairService()

    def test_range_no_bounds_needs_clarification(self, orders_meta):
        result = self.svc.repair(
            "validity",
            "range",
            config={},
            dataset_meta=orders_meta,
            target_column="total_amount",
        )
        assert result.status == "needs_clarification"
        # `inclusive_min` / `inclusive_max` defaults applied even though
        # bounds are still missing.
        assert "inclusive_min" in result.applied
        assert "inclusive_max" in result.applied
        assert "min_value" in result.remaining_missing or "max_value" in result.remaining_missing

    def test_range_with_min_value_is_repaired(self, orders_meta):
        result = self.svc.repair(
            "validity",
            "range",
            config={"min_value": 0},
            dataset_meta=orders_meta,
            target_column="total_amount",
        )
        assert result.status == "repaired"
        assert result.repaired_config["min_value"] == 0
        assert result.repaired_config["inclusive_min"] is True
        assert result.remaining_missing == []

    def test_freshness_infers_single_date_column(self):
        # Dataset where created_at is the only date column besides updated_at;
        # since two date candidates exist we should NOT auto-pick.
        meta_two_dates = DatasetMeta(
            dataset_id=str(uuid.uuid4()),
            dataset_name="orders",
            columns=[
                ColumnMeta(name="id", data_type="varchar", nullable=False),
                ColumnMeta(name="created_at", data_type="timestamp"),
                ColumnMeta(name="updated_at", data_type="timestamp"),
            ],
        )
        result = self.svc.repair(
            "timeliness",
            "freshness",
            config={"max_age_value": 7},
            dataset_meta=meta_two_dates,
            target_column="id",
        )
        assert result.status == "needs_clarification"
        assert "timestamp_column" in result.remaining_missing

        # Now with exactly one date column we expect auto-fill.
        meta_one_date = DatasetMeta(
            dataset_id=str(uuid.uuid4()),
            dataset_name="orders",
            columns=[
                ColumnMeta(name="id", data_type="varchar", nullable=False),
                ColumnMeta(name="created_at", data_type="timestamp"),
            ],
        )
        result2 = self.svc.repair(
            "timeliness",
            "freshness",
            config={"max_age_value": 7},
            dataset_meta=meta_one_date,
            target_column="id",
        )
        assert result2.status == "repaired"
        assert result2.repaired_config["timestamp_column"] == "created_at"
        assert result2.repaired_config["max_age_unit"] == "days"

    def test_unknown_subtype_fails(self):
        result = self.svc.repair("validity", "made_up", {})
        assert result.status == "failed"

    def test_static_defaults_applied(self):
        # apply_subtype_defaults populates conservative defaults
        out = apply_subtype_defaults("validity", "allowed_values", {"allowed_values": ["A"]})
        assert out["case_sensitive"] is True


# ── FlowCompatibilityValidator ─────────────────────────────────────────


class TestFlowCompatibilityValidator:
    def setup_method(self) -> None:
        self.svc = FlowCompatibilityValidator()

    def test_ready_proposal_passes(self):
        proposal = {
            "rule_name": "x",
            "dataset_id": "00000000-0000-0000-0000-000000000001",
            "column_name": "status",
            "check_type": "validity",
            "check_subtype": "allowed_values",
            "allowed_values": ["A", "B"],
        }
        res = self.svc.validate(proposal, merged_config={"allowed_values": ["A", "B"]})
        assert res.can_generate_flow is True
        assert res.simulated_node is not None
        assert res.simulated_node["config"]["check_dimension"] == "validity"

    def test_missing_dataset_id_fails(self):
        res = self.svc.validate(
            {
                "check_type": "validity",
                "check_subtype": "allowed_values",
                "column_name": "x",
                "allowed_values": ["a"],
            },
            merged_config={"allowed_values": ["a"]},
        )
        assert res.can_generate_flow is False
        assert any("dataset_id" in e for e in res.errors)

    def test_unknown_dimension_fails(self):
        res = self.svc.validate(
            {
                "check_type": "made_up",
                "check_subtype": "x",
                "dataset_id": "x",
                "column_name": "y",
            }
        )
        assert res.can_generate_flow is False
        assert any("dimension" in e.lower() for e in res.errors)

    def test_unknown_subtype_fails(self):
        res = self.svc.validate(
            {
                "check_type": "validity",
                "check_subtype": "made_up",
                "dataset_id": "x",
                "column_name": "y",
            }
        )
        assert res.can_generate_flow is False
        assert any("subtype" in e.lower() for e in res.errors)

    def test_missing_required_param_fails(self):
        # validity/regex requires `pattern`
        res = self.svc.validate(
            {
                "check_type": "validity",
                "check_subtype": "regex",
                "dataset_id": "x",
                "column_name": "y",
            },
            merged_config={},
        )
        assert res.can_generate_flow is False
        assert any("pattern" in e for e in res.errors)

    def test_record_count_recon_no_column_required(self):
        # reconciliation/record_count is allowed without a target column
        res = self.svc.validate(
            {
                "check_type": "reconciliation",
                "check_subtype": "record_count",
                "dataset_id": "x",
                "column_name": None,
            },
            merged_config={},
        )
        assert res.can_generate_flow is True


# ── end-to-end through the validator ───────────────────────────────────


class TestValidatorCanonicalEnforcement:
    def setup_method(self) -> None:
        self.svc = RuleProposalValidationService()

    def test_alias_not_null_accepted(self, orders_meta):
        # cc.check_subtype is 'not_null' — must be canonicalised to 'null'
        sir = _sir("not_null", "status", dimension="completeness", subtype="not_null")
        cc = _cc("completeness", "not_null", ["status"], orders_meta.dataset_id)
        v, ref, prop = self.svc.validate(sir, orders_meta, [cc])
        assert v.dq_flow_convertible is True
        assert prop["check_subtype"] == "null"

    def test_unknown_subtype_blocks(self, orders_meta):
        sir = _sir("not_null", "status", dimension="completeness", subtype="made_up")
        cc = _cc("completeness", "made_up", ["status"], orders_meta.dataset_id)
        v, ref, prop = self.svc.validate(sir, orders_meta, [cc])
        assert v.dq_flow_convertible is False
        assert ref is not None
        assert ref.reason == "unsupported_check_type"

    def test_freshness_missing_timestamp_blocks(self, orders_meta):
        # timeliness/freshness requires timestamp_column, max_age_value,
        # max_age_unit — previously the legacy table caught this; now via
        # canonical inventory we still must catch it.
        sir = _sir(
            "freshness",
            "order_id",
            dimension="timeliness",
            subtype="freshness",
            confidence=0.95,
        )
        cc = _cc("timeliness", "freshness", ["order_id"], orders_meta.dataset_id, config={})
        v, ref, prop = self.svc.validate(sir, orders_meta, [cc])
        # Two date columns exist → repair cannot pick one → clarify.
        assert v.dq_flow_convertible is False
        assert ref is not None
        assert "max_age_value" in v.missing_fields or any(
            f.endswith("_column") for f in v.missing_fields
        )

    def test_range_with_only_min_passes_after_repair(self, orders_meta):
        # validity/range with only min_value → repair fills inclusive bounds
        # → should pass.
        sir = _sir(
            "numeric_range",
            "total_amount",
            dimension="validity",
            subtype="range",
            subtype_config={"min_value": 0},
        )
        cc = _cc(
            "validity", "range", ["total_amount"], orders_meta.dataset_id, config={"min_value": 0}
        )
        v, ref, prop = self.svc.validate(sir, orders_meta, [cc])
        assert v.dq_flow_convertible is True
        assert prop["check_subtype"] == "range"
        assert prop["min_value"] == 0

    def test_placeholder_check_requires_placeholder_values(self, orders_meta):
        # completeness/placeholder requires placeholder_values — previously
        # silently passed because no entry in legacy `_REQUIRED_PER_SUBTYPE`.
        sir = _sir(
            "placeholder_check",
            "status",
            dimension="completeness",
            subtype="placeholder",
            subtype_config={},
        )
        cc = _cc("completeness", "placeholder", ["status"], orders_meta.dataset_id, config={})
        v, ref, prop = self.svc.validate(sir, orders_meta, [cc])
        assert v.dq_flow_convertible is False
        assert ref is not None
        assert "placeholder_values" in (v.missing_fields or [])

    def test_business_rule_requires_expression(self, orders_meta):
        sir = _sir(
            "business_rule",
            "status",
            dimension="validity",
            subtype="business_rule",
        )
        cc = _cc("validity", "business_rule", ["status"], orders_meta.dataset_id, config={})
        v, ref, prop = self.svc.validate(sir, orders_meta, [cc])
        assert v.dq_flow_convertible is False
        assert "business_rule_expression" in (v.missing_fields or [])

    def test_full_chain_value_in_list_with_values_passes(self, orders_meta):
        sir = _sir(
            "value_in_list",
            "status",
            dimension="validity",
            subtype="allowed_values",
            subtype_config={"allowed_values": ["NEW", "DONE"]},
        )
        cc = _cc(
            "validity",
            "allowed_values",
            ["status"],
            orders_meta.dataset_id,
            config={"allowed_values": ["NEW", "DONE"]},
        )
        v, ref, prop = self.svc.validate(sir, orders_meta, [cc])
        assert v.dq_flow_convertible is True
        assert ref is None
        # Repair must have filled the case_sensitive default.
        assert prop is not None
