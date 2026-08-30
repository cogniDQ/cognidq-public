"""
Tests for F099 — NL Rule Parsing Service
Covers SIR schema validation, parser service, API endpoint, and integration.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.schemas.nl_rule_builder import (
    ParseRuleRequest,
    ParseRuleResponse,
    RuleType,
    SIRCondition,
    SIREntity,
    SIRScope,
    StructuredIntermediateRepresentation,
)
from app.services.nl_rule_builder.glossary_loader import GlossaryPromptTerm
from app.services.nl_rule_builder.parser import (
    DISAMBIGUATION_THRESHOLD,
    NLRuleParserService,
)
from app.services.nl_rule_builder.prompts import (
    NL_VARIATIONS,
    build_parse_prompt,
    detect_rule_type_hint,
)

# ============================================================
# SIR Schema Validation Tests (P02)
# ============================================================


class TestSIRSchema:
    """Tests for Structured Intermediate Representation schema."""

    def test_valid_column_comparison(self):
        sir = StructuredIntermediateRepresentation(
            rule_type=RuleType.COLUMN_COMPARISON,
            subject=SIREntity(raw_text="shipping date"),
            operator="greater_than",
            object=SIREntity(raw_text="order date"),
            confidence=0.92,
        )
        assert sir.rule_type == RuleType.COLUMN_COMPARISON
        assert sir.subject.raw_text == "shipping date"
        assert sir.object.raw_text == "order date"
        assert sir.confidence == 0.92
        assert sir.schema_version == "1.0"

    def test_valid_not_null(self):
        sir = StructuredIntermediateRepresentation(
            rule_type=RuleType.NOT_NULL,
            subject=SIREntity(raw_text="customer email"),
            operator="is_not_null",
            confidence=0.95,
        )
        assert sir.rule_type == RuleType.NOT_NULL
        assert sir.object is None

    def test_valid_value_in_list(self):
        sir = StructuredIntermediateRepresentation(
            rule_type=RuleType.VALUE_IN_LIST,
            subject=SIREntity(raw_text="order status"),
            operator="in",
            constraints=["OPEN", "CLOSED", "PENDING"],
            confidence=0.96,
        )
        assert sir.constraints == ["OPEN", "CLOSED", "PENDING"]

    def test_valid_conditional_rule(self):
        sir = StructuredIntermediateRepresentation(
            rule_type=RuleType.CONDITIONAL_RULE,
            subject=SIREntity(raw_text="shipping_date"),
            operator="is_not_null",
            conditions=[
                SIRCondition(
                    field=SIREntity(raw_text="status"),
                    operator="equals",
                    value="SHIPPED",
                )
            ],
            confidence=0.91,
        )
        assert len(sir.conditions) == 1
        assert sir.conditions[0].value == "SHIPPED"

    def test_valid_reference_lookup(self):
        sir = StructuredIntermediateRepresentation(
            rule_type=RuleType.REFERENCE_LOOKUP,
            subject=SIREntity(raw_text="supplier ID"),
            operator="exists_in",
            object=SIREntity(raw_text="supplier master"),
            confidence=0.89,
        )
        assert sir.rule_type == RuleType.REFERENCE_LOOKUP

    def test_valid_numeric_threshold(self):
        sir = StructuredIntermediateRepresentation(
            rule_type=RuleType.NUMERIC_THRESHOLD,
            subject=SIREntity(raw_text="customer age"),
            operator="between",
            constraints=[18, 120],
            confidence=0.94,
        )
        assert sir.constraints == [18, 120]

    def test_invalid_missing_subject(self):
        with pytest.raises(Exception):
            StructuredIntermediateRepresentation(
                rule_type=RuleType.NOT_NULL,
                operator="is_not_null",
                confidence=0.9,
            )

    def test_invalid_confidence_too_high(self):
        # F128: confidence > 1.0 is clamped to 1.0 (not rejected)
        sir = StructuredIntermediateRepresentation(
            rule_type=RuleType.NOT_NULL,
            subject=SIREntity(raw_text="email"),
            confidence=1.5,
        )
        assert sir.confidence == 1.0

    def test_invalid_confidence_negative(self):
        # F128: confidence < 0.0 is clamped to 0.0 (not rejected)
        sir = StructuredIntermediateRepresentation(
            rule_type=RuleType.NOT_NULL,
            subject=SIREntity(raw_text="email"),
            confidence=-0.1,
        )
        assert sir.confidence == 0.0

    def test_scope_defaults(self):
        sir = StructuredIntermediateRepresentation(
            rule_type=RuleType.NOT_NULL,
            subject=SIREntity(raw_text="email"),
            confidence=0.9,
        )
        assert sir.scope.dataset_hint is None
        assert sir.scope.domain_hint is None

    def test_schema_version_default(self):
        sir = StructuredIntermediateRepresentation(
            rule_type=RuleType.NOT_NULL,
            subject=SIREntity(raw_text="email"),
            confidence=0.9,
        )
        assert sir.schema_version == "1.0"

    def test_all_rule_types_exist(self):
        expected = {
            "null_check",
            "not_null",
            "column_comparison",
            "numeric_threshold",
            "date_comparison",
            "value_in_list",
            "regex_format",
            "length_check",
            "uniqueness",
            "composite_uniqueness",
            "reference_lookup",
            "conditional_rule",
            "arithmetic_comparison",
            "unknown",
        }
        actual = {rt.value for rt in RuleType}
        # RuleType has expanded over multiple phases; ensure legacy/core values are still present.
        assert expected.issubset(actual)


# ============================================================
# Parse Request Schema Tests (P02)
# ============================================================


class TestParseRequestSchema:
    """Tests for ParseRuleRequest validation."""

    def test_valid_with_all_fields(self):
        req = ParseRuleRequest(
            rule_text="email must not be null",
            dataset_id="3fa85f64-5717-4562-b3fc-2c963f66afa6",
            domain="Orders",
            source_system="SAP",
            rule_category="completeness",
            severity="high",
            tags=["validation"],
        )
        assert req.rule_text == "email must not be null"

    def test_valid_with_only_required(self):
        req = ParseRuleRequest(rule_text="email must not be null")
        assert req.dataset_id is None
        assert req.domain is None

    def test_invalid_empty_rule_text(self):
        with pytest.raises(Exception):
            ParseRuleRequest(rule_text="")

    def test_invalid_whitespace_rule_text(self):
        with pytest.raises(Exception):
            ParseRuleRequest(rule_text="   ")

    def test_rule_text_stripped(self):
        req = ParseRuleRequest(rule_text="  email must not be null  ")
        assert req.rule_text == "email must not be null"

    def test_invalid_severity(self):
        with pytest.raises(Exception):
            ParseRuleRequest(rule_text="test", severity="extreme")

    def test_valid_severity_values(self):
        for sev in ("critical", "high", "medium", "low", "info"):
            req = ParseRuleRequest(rule_text="test", severity=sev)
            assert req.severity == sev

    def test_too_many_tags(self):
        with pytest.raises(Exception):
            ParseRuleRequest(rule_text="test", tags=["t"] * 21)

    def test_tag_too_long(self):
        with pytest.raises(Exception):
            ParseRuleRequest(rule_text="test", tags=["x" * 51])


# ============================================================
# LLM Prompt Tests (P02)
# ============================================================


class TestLLMPrompts:
    """Tests for LLM prompt construction."""

    def test_prompt_includes_rule_text(self):
        prompt = build_parse_prompt("email must not be null")
        assert "email must not be null" in prompt

    def test_prompt_includes_schema(self):
        prompt = build_parse_prompt("test rule")
        assert "schema_version" in prompt
        assert "rule_type" in prompt

    def test_prompt_includes_examples(self):
        prompt = build_parse_prompt("test rule")
        assert "Example 1" in prompt
        assert "customer email must not be null" in prompt

    def test_prompt_includes_context(self):
        prompt = build_parse_prompt("test rule", {"domain": "Orders", "dataset_id": "ds-123"})
        assert "Domain: Orders" in prompt
        assert "Dataset context: ds-123" in prompt

    def test_prompt_prohibits_code(self):
        prompt = build_parse_prompt("test rule")
        assert "MUST NOT produce SQL" in prompt or "Never output code" in prompt

    def test_prompt_without_context(self):
        prompt = build_parse_prompt("test rule")
        assert "Additional context" not in prompt

    def test_prompt_includes_glossary_section_when_provided(self):
        prompt = build_parse_prompt(
            "email must not be null",
            {
                "glossary_section": "BUSINESS GLOSSARY (relevant terms):\n1. Business Name: Employee Email",
                "available_datasets": ["hr_employees"],
            },
        )
        assert "BUSINESS GLOSSARY" in prompt
        assert "Employee Email" in prompt


# ============================================================
# NL Normalization Tests (P02)
# ============================================================


class TestNLNormalization:
    """Tests for NL variation detection."""

    def test_not_empty_maps_to_not_null(self):
        assert detect_rule_type_hint("email must not be empty") == "not_null"

    def test_cannot_be_blank_maps_to_not_null(self):
        assert detect_rule_type_hint("field cannot be blank") == "not_null"

    def test_is_required_maps_to_not_null(self):
        assert detect_rule_type_hint("email is required") == "not_null"

    def test_must_be_unique_maps_to_uniqueness(self):
        assert detect_rule_type_hint("employee ID must be unique") == "uniqueness"

    def test_must_exist_in_maps_to_reference(self):
        assert detect_rule_type_hint("supplier must exist in master") == "reference_lookup"

    def test_must_be_null_maps_to_null_check(self):
        assert detect_rule_type_hint("archived_date must be null") == "null_check"

    def test_no_duplicates_maps_to_uniqueness(self):
        assert detect_rule_type_hint("no duplicates allowed") == "uniqueness"

    def test_unknown_phrase_returns_none(self):
        assert detect_rule_type_hint("some random text") is None


# ============================================================
# Parser Service Tests (P03)
# ============================================================


def _mock_llm_response(
    rule_type, subject, operator="is_not_null", obj=None, confidence=0.92, **kwargs
):
    """Helper to create a mock LLM response dict."""
    result = {
        "schema_version": "1.0",
        "rule_type": rule_type,
        "subject": {"raw_text": subject},
        "operator": operator,
        "object": {"raw_text": obj} if obj else None,
        "scope": {"dataset_hint": None, "domain_hint": None, "source_system_hint": None},
        "conditions": kwargs.get("conditions", []),
        "constraints": kwargs.get("constraints", []),
        "confidence": confidence,
        "requires_disambiguation": kwargs.get("requires_disambiguation", False),
        "parse_warnings": kwargs.get("parse_warnings", []),
    }
    return result


class TestNLRuleParserService:
    """Tests for the NLRuleParserService."""

    @pytest.fixture(autouse=True)
    def _patch_subtype_clarifications(self):
        """Suppress _ensure_subtype_clarifications for all parser unit tests.

        These tests exercise SIR parsing and status logic; subtype-config
        completeness validation is a separate concern and would inject
        clarifying questions that change status to 'needs_clarification',
        masking the behaviour under test.
        """
        with patch.object(NLRuleParserService, "_ensure_subtype_clarifications"):
            yield

    def _make_db_mock(self):
        db = MagicMock()
        db.add = MagicMock()
        db.flush = MagicMock()
        db.commit = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_parse_column_comparison(self):
        service = NLRuleParserService()
        db = self._make_db_mock()
        llm_response = _mock_llm_response(
            "column_comparison", "shipping date", "greater_than", "order date", 0.92
        )

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="shipping date must be after order date"),
                uuid.uuid4(),
            )

        assert result.status == "parsed"
        assert result.parsed_rule.rule_type == RuleType.COLUMN_COMPARISON
        assert result.parsed_rule.subject.raw_text == "shipping date"

    @pytest.mark.asyncio
    async def test_parse_not_null(self):
        service = NLRuleParserService()
        db = self._make_db_mock()
        llm_response = _mock_llm_response(
            "not_null", "customer email", "is_not_null", confidence=0.95
        )

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="customer email must not be null"),
                uuid.uuid4(),
            )

        assert result.status == "parsed"
        assert result.parsed_rule.rule_type == RuleType.NOT_NULL

    @pytest.mark.asyncio
    async def test_parse_value_in_list(self):
        service = NLRuleParserService()
        db = self._make_db_mock()
        llm_response = _mock_llm_response(
            "value_in_list",
            "order status",
            "in",
            confidence=0.96,
            constraints=["OPEN", "CLOSED", "PENDING"],
        )

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="status must be one of OPEN, CLOSED, PENDING"),
                uuid.uuid4(),
            )

        assert result.status == "parsed"
        assert result.parsed_rule.rule_type == RuleType.VALUE_IN_LIST
        assert "OPEN" in result.parsed_rule.constraints

    @pytest.mark.asyncio
    async def test_parse_numeric_threshold(self):
        service = NLRuleParserService()
        db = self._make_db_mock()
        llm_response = _mock_llm_response(
            "numeric_threshold", "customer age", "between", confidence=0.94, constraints=[18, 120]
        )

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="customer age must be between 18 and 120"),
                uuid.uuid4(),
            )

        assert result.status == "parsed"
        assert result.parsed_rule.rule_type == RuleType.NUMERIC_THRESHOLD

    @pytest.mark.asyncio
    async def test_parse_conditional_rule(self):
        service = NLRuleParserService()
        db = self._make_db_mock()
        llm_response = _mock_llm_response(
            "conditional_rule",
            "shipping_date",
            "is_not_null",
            confidence=0.91,
            conditions=[
                {"field": {"raw_text": "status"}, "operator": "equals", "value": "SHIPPED"}
            ],
        )

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(
                    rule_text="if status = SHIPPED then shipping_date must not be null"
                ),
                uuid.uuid4(),
            )

        assert result.status == "parsed"
        assert result.parsed_rule.rule_type == RuleType.CONDITIONAL_RULE
        assert len(result.parsed_rule.conditions) == 1

    @pytest.mark.asyncio
    async def test_parse_reference_lookup(self):
        service = NLRuleParserService()
        db = self._make_db_mock()
        llm_response = _mock_llm_response(
            "reference_lookup", "supplier ID", "exists_in", "supplier master", 0.89
        )

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="supplier ID must exist in supplier master"),
                uuid.uuid4(),
            )

        assert result.status == "parsed"
        assert result.parsed_rule.rule_type == RuleType.REFERENCE_LOOKUP

    @pytest.mark.asyncio
    async def test_parse_cannot_interpret(self):
        service = NLRuleParserService()
        db = self._make_db_mock()
        llm_response = _mock_llm_response("unknown", "", confidence=0.1)

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="make the data better"),
                uuid.uuid4(),
            )

        assert result.status == "cannot_interpret"
        assert result.parsed_rule is None
        assert len(result.suggestions) > 0

    @pytest.mark.asyncio
    async def test_parse_llm_invalid_json_retry_success(self):
        service = NLRuleParserService()
        db = self._make_db_mock()
        good_response = _mock_llm_response("not_null", "email", confidence=0.95)

        # First call returns None (invalid JSON), second call succeeds
        with patch.object(
            service, "_invoke_llm", new_callable=AsyncMock, side_effect=[None, good_response]
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="email must not be null"),
                uuid.uuid4(),
            )

        assert result.status == "parsed"

    @pytest.mark.asyncio
    async def test_parse_llm_invalid_json_retry_fail(self):
        service = NLRuleParserService()
        db = self._make_db_mock()

        with patch.object(
            service,
            "_invoke_llm",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="email must not be null"),
                uuid.uuid4(),
            )

        assert result.status == "parse_error"

    @pytest.mark.asyncio
    async def test_parse_llm_timeout(self):
        service = NLRuleParserService()
        db = self._make_db_mock()

        with patch.object(
            service,
            "_invoke_llm_with_retry",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="email must not be null"),
                uuid.uuid4(),
            )

        assert result.status == "parse_error"

    @pytest.mark.asyncio
    async def test_confidence_high(self):
        service = NLRuleParserService()
        db = self._make_db_mock()
        llm_response = _mock_llm_response("not_null", "email", confidence=0.95)

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="email must not be null"),
                uuid.uuid4(),
            )

        assert result.parsed_rule.confidence >= 0.90
        assert result.parsed_rule.requires_disambiguation is False

    @pytest.mark.asyncio
    async def test_confidence_medium_no_disambiguation(self):
        service = NLRuleParserService()
        db = self._make_db_mock()
        llm_response = _mock_llm_response("not_null", "email", confidence=0.75)

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="email should not be empty"),
                uuid.uuid4(),
            )

        assert 0.70 <= result.parsed_rule.confidence < 0.90
        assert result.parsed_rule.requires_disambiguation is False

    @pytest.mark.asyncio
    async def test_confidence_low_triggers_disambiguation(self):
        service = NLRuleParserService()
        db = self._make_db_mock()
        llm_response = _mock_llm_response("not_null", "status", confidence=0.45)

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="status must be valid"),
                uuid.uuid4(),
            )

        assert result.parsed_rule.confidence < DISAMBIGUATION_THRESHOLD
        assert result.parsed_rule.requires_disambiguation is True

    @pytest.mark.asyncio
    async def test_persistence_request_created(self):
        service = NLRuleParserService()
        db = self._make_db_mock()
        llm_response = _mock_llm_response("not_null", "email", confidence=0.95)

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="email must not be null"),
                uuid.uuid4(),
            )

        # Verify db.add was called (for request and result)
        assert db.add.call_count >= 2
        assert db.commit.called

    @pytest.mark.asyncio
    async def test_persistence_result_linked(self):
        service = NLRuleParserService()
        db = self._make_db_mock()
        llm_response = _mock_llm_response("not_null", "email", confidence=0.95)

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="email must not be null"),
                uuid.uuid4(),
            )

        # Check that NLRuleParseResult was added with a request_id
        added_objects = [call.args[0] for call in db.add.call_args_list]
        from app.models.nl_rule import NLRuleParseResult as NLRuleParseResultModel
        from app.models.nl_rule import NLRuleRequest as NLRuleRequestModel

        requests = [o for o in added_objects if isinstance(o, NLRuleRequestModel)]
        results = [o for o in added_objects if isinstance(o, NLRuleParseResultModel)]
        assert len(requests) == 1
        assert len(results) == 1
        assert results[0].request_id == requests[0].id

    @pytest.mark.asyncio
    async def test_parse_with_dataset_context(self):
        service = NLRuleParserService()
        db = self._make_db_mock()
        llm_response = _mock_llm_response("not_null", "email", confidence=0.95)

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(
                    rule_text="email must not be null",
                    dataset_id="3fa85f64-5717-4562-b3fc-2c963f66afa6",
                    domain="Customers",
                ),
                uuid.uuid4(),
            )

        assert result.status == "parsed"
        assert result.parsed_rule.scope.dataset_hint == "3fa85f64-5717-4562-b3fc-2c963f66afa6"
        assert result.parsed_rule.scope.domain_hint == "Customers"
        assert result.trust_summary is not None
        assert result.trust_summary.confidence_band == "high"
        assert len(result.explainability) >= 2

    @pytest.mark.asyncio
    async def test_parse_falls_back_to_dataset_context_when_glossary_empty(self):
        service = NLRuleParserService()
        service.glossary_loader.load_glossary_for_rule = MagicMock(return_value=[])
        service.glossary_loader.format_glossary_for_prompt = MagicMock(return_value="")

        db = self._make_db_mock()
        llm_response = _mock_llm_response("not_null", "email", "is_not_null", confidence=0.71)

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="email must not be null", domain="HR"),
                uuid.uuid4(),
            )

        assert result.status == "parsed"
        assert result.parsed_rule.rule_type == RuleType.NOT_NULL
        assert result.parsed_rule.glossary_context == []
        assert result.trust_summary is not None
        assert "parsed without glossary-backed term match" in result.trust_summary.assumptions
        service.glossary_loader.load_glossary_for_rule.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_boosts_confidence_when_valid_glossary_match_exists(self):
        service = NLRuleParserService()
        term_id = str(uuid.uuid4())
        service.glossary_loader.load_glossary_for_rule = MagicMock(
            return_value=[
                GlossaryPromptTerm(
                    term_id=uuid.UUID(term_id),
                    business_name="Employee Email Address",
                    technical_name="employee_email",
                    synonyms=["email"],
                    definition="Official employee email",
                    data_type="string",
                    domain="HR",
                    linked_asset_ids=["dataset:hr_employees", "column:email_address"],
                    relevance_score=0.93,
                )
            ]
        )
        service.glossary_loader.format_glossary_for_prompt = MagicMock(
            return_value="BUSINESS GLOSSARY"
        )

        db = self._make_db_mock()
        llm_response = _mock_llm_response("not_null", "email", "is_not_null", confidence=0.65)
        llm_response["subject"]["matched_glossary_term_id"] = term_id

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="employee email must not be null", domain="HR"),
                uuid.uuid4(),
            )

        # 0.65 + 0.10 boost = 0.75, above disambiguation threshold.
        assert result.status == "parsed"
        assert result.parsed_rule.confidence >= 0.75
        assert result.parsed_rule.requires_disambiguation is False
        assert len(result.parsed_rule.glossary_context) == 1
        assert result.parsed_rule.subject.matched_glossary_term_id == term_id

    @pytest.mark.asyncio
    async def test_invalid_glossary_match_id_is_cleared(self):
        service = NLRuleParserService()
        valid_term_id = uuid.uuid4()
        invalid_term_id = str(uuid.uuid4())
        service.glossary_loader.load_glossary_for_rule = MagicMock(
            return_value=[
                GlossaryPromptTerm(
                    term_id=valid_term_id,
                    business_name="Employee Email Address",
                    technical_name="employee_email",
                    synonyms=["email"],
                    definition="Official employee email",
                    data_type="string",
                    domain="HR",
                    linked_asset_ids=[],
                    relevance_score=0.93,
                )
            ]
        )
        service.glossary_loader.format_glossary_for_prompt = MagicMock(
            return_value="BUSINESS GLOSSARY"
        )

        db = self._make_db_mock()
        llm_response = _mock_llm_response("not_null", "email", "is_not_null", confidence=0.60)
        llm_response["subject"]["matched_glossary_term_id"] = invalid_term_id

        with patch.object(
            service, "_invoke_llm_with_retry", new_callable=AsyncMock, return_value=llm_response
        ):
            result = await service.parse_rule(
                db,
                uuid.uuid4(),
                ParseRuleRequest(rule_text="employee email must not be null", domain="HR"),
                uuid.uuid4(),
            )

        assert result.status == "parsed"
        assert result.parsed_rule.subject.matched_glossary_term_id is None
        assert result.parsed_rule.glossary_context == []


# ============================================================
# Model Instantiation Tests (P01)
# ============================================================


class TestNLRuleModels:
    """Tests for ORM model instantiation."""

    def test_create_nl_rule_request(self):
        from app.models.nl_rule import NLRuleRequest as NLRuleRequestModel

        req = NLRuleRequestModel(
            id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            rule_text="email must not be null",
            context={"domain": "Orders"},
            status="pending",
            created_by=uuid.uuid4(),
        )
        assert req.rule_text == "email must not be null"
        assert req.status == "pending"

    def test_create_nl_rule_parse_result(self):
        from app.models.nl_rule import NLRuleParseResult as NLRuleParseResultModel

        result = NLRuleParseResultModel(
            id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            sir_json={"rule_type": "not_null"},
            rule_type="not_null",
            confidence=0.95,
            requires_disambiguation=False,
            model_version="gpt-4o",
            schema_version="1.0",
        )
        assert result.confidence == 0.95
        assert result.rule_type == "not_null"

    def test_nl_rule_request_repr(self):
        from app.models.nl_rule import NLRuleRequest as NLRuleRequestModel

        req = NLRuleRequestModel(id=uuid.uuid4(), status="parsed")
        assert "NLRuleRequest" in repr(req)

    def test_nl_rule_parse_result_repr(self):
        from app.models.nl_rule import NLRuleParseResult as NLRuleParseResultModel

        result = NLRuleParseResultModel(id=uuid.uuid4(), rule_type="not_null", confidence=0.9)
        assert "NLRuleParseResult" in repr(result)
