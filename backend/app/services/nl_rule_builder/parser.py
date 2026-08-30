"""
NL Rule Parser Service
Core service that orchestrates LLM-based parsing of natural language rules
into Structured Intermediate Representations (SIR) with full check node configs.
"""

import json
import logging
import uuid
from typing import Any

from openai import (
    APIConnectionError,
    AsyncOpenAI,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
)
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.nl_rule import NLRuleParseResult, NLRuleRequest
from app.schemas.nl_rule_builder import (
    CheckConfigOutput,
    DecompositionSummary,
    DetectedColumn,
    DetectedDataset,
    GlossaryContextItem,
    ParseRuleRequest,
    ParseRuleResponse,
    RefinementGuidance,
    RuleType,
    SIREntity,
    SIRScope,
    StructuredIntermediateRepresentation,
    ThresholdConfig,
)
from app.services.nl_compiler.mappings import DIMENSION_DEFAULTS, RULE_TYPE_MAP
from app.services.nl_compiler.subtype_schema import (
    SUBTYPE_INVENTORY,
    get_subtype_meta,
    get_subtypes,
    validate_subtype_config,
)
from app.services.nl_rule_builder.dataset_metadata import (
    DatasetMeta,
    load_dataset_meta,
)
from app.services.nl_rule_builder.glossary_loader import GlossaryPromptTerm, GlossaryTermLoader
from app.services.nl_rule_builder.parse_explainability import ParseExplainabilityService
from app.services.nl_rule_builder.prompts import build_parse_prompt, detect_rule_type_hint
from app.services.nl_rule_builder.rule_proposal_validation import (
    RuleProposalValidationService,
)

logger = logging.getLogger(__name__)

# Confidence thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.90
DISAMBIGUATION_THRESHOLD = 0.70

# Supported rule types whitelist
SUPPORTED_RULE_TYPES = {rt.value for rt in RuleType}
# Also accept any rule type that maps to a known dimension
SUPPORTED_RULE_TYPES.update(RULE_TYPE_MAP.keys())


# E5 — per-question rationale fallback (used when LLM omits the rationale field).
def _default_rationale(field: str, answer_type: str) -> str:
    field_l = (field or "general").lower()
    if answer_type == "numeric":
        if "threshold" in field_l or "pct" in field_l or "percent" in field_l:
            return "We need a numeric threshold to evaluate pass/fail."
        if "days" in field_l or "hours" in field_l:
            return "Asking for a time bound to apply the rule consistently."
        return "A numeric value is required to compile this check."
    if answer_type in ("single_select", "multi_select"):
        return "Multiple interpretations were possible; please pick one."
    # free_text
    if field_l in ("dataset", "table", "scope"):
        return "We could not unambiguously identify the dataset or table."
    if field_l in ("column", "field", "subject"):
        return "We could not unambiguously identify the column."
    return "We need this detail to complete the rule definition."


class NLRuleParserService:
    """Service for parsing natural language rules into structured representations."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL
        self.temperature = 0.0
        self.max_tokens = settings.OPENAI_MAX_TOKENS
        self.glossary_loader = GlossaryTermLoader()
        self.explainability_service = ParseExplainabilityService(
            high_confidence_threshold=HIGH_CONFIDENCE_THRESHOLD,
            disambiguation_threshold=DISAMBIGUATION_THRESHOLD,
        )
        self.proposal_validator = RuleProposalValidationService()

    def _apply_workspace_llm_config(self, db: Session, workspace_id: uuid.UUID) -> None:
        """Override LLM settings with workspace-level config if available."""
        try:
            from app.services.data_sources.credential_service import decrypt_string
            from app.services.workspaces.settings_repository import find_by_workspace_id

            ws_settings = find_by_workspace_id(db, workspace_id, tenant_id=None)
            if ws_settings and ws_settings.llm_config:
                lc = ws_settings.llm_config
                if lc.api_key_encrypted:
                    decrypted_key = decrypt_string(lc.api_key_encrypted)
                    self.client = AsyncOpenAI(api_key=decrypted_key)
                    self.model = lc.model
                    self.temperature = lc.temperature
                    self.max_tokens = lc.max_tokens
                    logger.info(
                        "Using workspace-level LLM config for workspace %s (provider=%s, model=%s)",
                        workspace_id,
                        lc.provider,
                        lc.model,
                    )
        except Exception as e:
            logger.warning(
                "Failed to load workspace LLM config for %s, falling back to global: %s",
                workspace_id,
                e,
            )

    @staticmethod
    def _map_llm_exception_to_reason(exc: Exception) -> str:
        """Map provider exceptions to actionable parse failure reasons."""
        if isinstance(exc, AuthenticationError):
            return "LLM authentication failed: invalid API key or missing permissions"
        if isinstance(exc, RateLimitError):
            return "LLM rate limit/quota exceeded: please retry later or adjust plan limits"
        if isinstance(exc, NotFoundError):
            return "LLM model not found or not accessible with current credentials"
        if isinstance(exc, APIConnectionError):
            return "LLM connection failed: provider endpoint is unreachable"
        return f"LLM request failed: {type(exc).__name__}"

    async def parse_rule(
        self,
        db: Session,
        workspace_id: uuid.UUID,
        request: ParseRuleRequest,
        user_id: uuid.UUID,
    ) -> ParseRuleResponse:
        """Parse a natural language rule into a Structured Intermediate Representation.

        Args:
            db: Database session.
            workspace_id: Target workspace UUID.
            request: Parse request with rule_text and optional context.
            user_id: Authenticated user UUID.

        Returns:
            ParseRuleResponse with parsed SIR or error status.
        """
        # Build context dict from request
        context = self._build_context(request)

        # Fetch available dataset names to give LLM awareness of the workspace
        dataset_names = self._fetch_workspace_dataset_names(db, workspace_id)
        if dataset_names:
            if context is None:
                context = {}
            context["available_datasets"] = dataset_names

        # Spec §4.1 — when a dataset is selected, ground the parser in its
        # full schema (columns + types + nullability + descriptions). This
        # lets the LLM reject hallucinated columns and pick correct types.
        selected_dataset_meta: DatasetMeta | None = None
        if request.dataset_id:
            try:
                selected_dataset_meta = load_dataset_meta(
                    db, workspace_id, uuid.UUID(str(request.dataset_id))
                )
            except (ValueError, TypeError):
                selected_dataset_meta = None
        if selected_dataset_meta is not None:
            if context is None:
                context = {}
            context["dataset_name"] = selected_dataset_meta.dataset_name
            context["available_columns"] = selected_dataset_meta.column_names()
            context["selected_dataset_block"] = selected_dataset_meta.to_prompt_block()

        # Load glossary terms for parser enrichment (fail-open).
        glossary_terms = self.glossary_loader.load_glossary_for_rule(
            db=db,
            workspace_id=workspace_id,
            rule_text=request.rule_text,
            max_terms=20,
        )
        if context is None:
            context = {}
        if glossary_terms:
            context["glossary_section"] = self.glossary_loader.format_glossary_for_prompt(
                glossary_terms
            )
            context["glossary_terms"] = [
                {
                    "term_id": str(t.term_id),
                    "business_name": t.business_name,
                    "technical_name": t.technical_name,
                    "synonyms": t.synonyms,
                    "domain": t.domain,
                    "linked_asset_ids": t.linked_asset_ids,
                    "relevance_score": t.relevance_score,
                }
                for t in glossary_terms
            ]
        else:
            # Explicitly keep dataset-only context path available.
            context["glossary_section"] = None
            context["glossary_terms"] = []

        # Apply workspace-level LLM config if available
        self._apply_workspace_llm_config(db, workspace_id)

        # Create parse request record
        nl_request = NLRuleRequest(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            rule_text=request.rule_text,
            context=context,
            status="pending",
            created_by=user_id,
        )
        db.add(nl_request)
        db.flush()

        # Update status to parsing
        nl_request.status = "parsing"
        db.flush()

        try:
            # Build constrained LLM prompt
            prompt = build_parse_prompt(request.rule_text, context)

            # Invoke LLM with retry
            raw_output = await self._invoke_llm_with_retry(prompt)

            if raw_output is None:
                # LLM completely failed
                nl_request.status = "parse_error"
                db.commit()
                return ParseRuleResponse(
                    request_id=str(nl_request.id),
                    parsed_rule=None,
                    status="parse_error",
                    proposal_status="invalid_request",
                    reason="LLM service unavailable or returned invalid response after retry",
                    suggestions=["Please try again later"],
                )

            # Validate and build SIR
            sir = self._validate_and_build_sir(raw_output, request.rule_text, context)

            if sir is None:
                # Could not interpret
                nl_request.status = "cannot_interpret"

                # Persist a minimal parse result
                parse_result = NLRuleParseResult(
                    id=uuid.uuid4(),
                    request_id=nl_request.id,
                    sir_json=raw_output,
                    rule_type="unknown",
                    confidence=0.0,
                    requires_disambiguation=True,
                    parse_warnings=[
                        "Could not confidently interpret the input as a data quality rule"
                    ],
                    model_version=self.model,
                    schema_version="1.0",
                )
                db.add(parse_result)
                db.commit()

                return ParseRuleResponse(
                    request_id=str(nl_request.id),
                    parse_result_id=str(parse_result.id),
                    parsed_rule=None,
                    status="cannot_interpret",
                    proposal_status="needs_refinement",
                    refinement=RefinementGuidance(
                        reason="unknown_intent",
                        message=(
                            "I could not interpret this as a data quality rule. "
                            "Please specify a column and a check condition."
                        ),
                        next_question="What exactly should be checked?",
                        field="rule_text",
                    ),
                    reason="No actionable data quality rule detected",
                    suggestions=[
                        "Try specifying a column and condition",
                        "Example: 'email must not be null'",
                        "Example: 'shipping date must be after order date'",
                    ],
                )

            # Attach validated glossary matches and apply confidence boost first.
            sir = self._attach_glossary_matches(sir, raw_output, glossary_terms)
            sir = self._boost_confidence_for_glossary_match(sir)

            # F126: Detect compound obligations and decompose into atomic SIRs
            sir = self._detect_and_decompose(sir, raw_output)

            # F126: Apply inline extraction (operator, threshold, allowed_values, etc.)
            if sir.is_compound and sir.obligations:
                obligations_raw = raw_output.get("obligations") or []
                for i, obligation in enumerate(sir.obligations):
                    ob_raw = obligations_raw[i] if i < len(obligations_raw) else {}
                    if isinstance(ob_raw, dict):
                        sir.obligations[i] = self._apply_inline_extraction(obligation, ob_raw)
            else:
                sir = self._apply_inline_extraction(sir, raw_output)

            # Apply confidence and disambiguation logic
            sir = self._apply_confidence_logic(sir)

            # Subtype-aware clarifying questions: ambiguous subtype OR missing
            # required config fields → emit additional questions before
            # downstream config building so the user can fill the gaps.
            if sir.is_compound and sir.obligations:
                for ob in sir.obligations:
                    self._merge_clarification_answers_into_subtype(
                        ob, request.clarification_answers
                    )
                    self._ensure_subtype_clarifications(ob)
            else:
                self._merge_clarification_answers_into_subtype(sir, request.clarification_answers)
                self._ensure_subtype_clarifications(sir)

            # Extract clarification_context from LLM output (explains what it tried)
            sir.clarification_context = raw_output.get("clarification_context") or None

            # If clarification answers were provided and LLM returned no new questions,
            # the answers were accepted — boost confidence
            if request.clarification_answers and not sir.clarifying_questions:
                sir.requires_disambiguation = False
                sir.confidence = max(sir.confidence, DISAMBIGUATION_THRESHOLD)

            # Build check configs from LLM output or SIR
            check_configs = self._build_check_configs(sir, raw_output, request)

            # Detect datasets from rule text
            detected_datasets = self._detect_datasets(db, workspace_id, sir, raw_output)

            # F129: Auto-resolve dataset_id from detected_datasets when the
            # caller did not explicitly select one. If exactly one detected
            # dataset has a workspace UUID and a high enough match score, we
            # promote it to selected_dataset_meta and propagate its id onto
            # every check config. This unblocks the proposal validator's
            # "No dataset selected or resolved" gate for prompts that
            # mentioned the dataset by name.
            if selected_dataset_meta is None and detected_datasets:
                resolved = [
                    d for d in detected_datasets if d.dataset_id and (d.match_score or 0.0) >= 0.7
                ]
                if len(resolved) == 1:
                    try:
                        selected_dataset_meta = load_dataset_meta(
                            db, workspace_id, uuid.UUID(str(resolved[0].dataset_id))
                        )
                    except (ValueError, TypeError):
                        selected_dataset_meta = None

            # Once we have a dataset_meta (whether user-supplied or
            # auto-resolved above), propagate its id/name onto every check
            # config that is missing them, and try to fuzzy-resolve any
            # column names that are not present verbatim on the dataset.
            if selected_dataset_meta is not None and check_configs:
                self._bind_dataset_to_checks(check_configs, selected_dataset_meta)

            # Detect columns
            detected_columns = self._detect_columns(sir)

            # Persist parse result
            parse_result = NLRuleParseResult(
                id=uuid.uuid4(),
                request_id=nl_request.id,
                sir_json=sir.model_dump(mode="json"),
                rule_type=sir.rule_type.value,
                confidence=sir.confidence,
                requires_disambiguation=sir.requires_disambiguation,
                parse_warnings=sir.parse_warnings if sir.parse_warnings else None,
                model_version=self.model,
                schema_version=sir.schema_version,
                check_configs=[cc.model_dump(mode="json") for cc in check_configs]
                if check_configs
                else None,
                detected_datasets=[dd.model_dump(mode="json") for dd in detected_datasets]
                if detected_datasets
                else None,
                detected_columns=[dc.model_dump(mode="json") for dc in detected_columns]
                if detected_columns
                else None,
            )
            db.add(parse_result)

            # Update request status
            nl_request.status = "parsed"
            db.commit()

            # Determine response status based on clarifying questions
            has_questions = bool(sir.clarifying_questions)
            response_status = "needs_clarification" if has_questions else "parsed"
            explainability = self.explainability_service.build_parse_explainability(
                sir, request.rule_text
            )
            trust_summary = self.explainability_service.build_parse_trust_summary(sir)

            # F126: Build decomposition_summary (AC-016 — always present)
            # F128: construct typed DecompositionSummary instead of raw dict
            if sir.is_compound and sir.obligations:
                decomposition_summary = DecompositionSummary(
                    count=len(sir.obligations),
                    logic=sir.obligation_logic,
                    obligations=[o.subject.raw_text for o in sir.obligations],
                )
            else:
                decomposition_summary = DecompositionSummary(
                    count=1,
                    logic=None,
                    obligations=[sir.subject.raw_text],
                )

            # Spec §7/§11/§12 — run the hard "no proposal until valid" gate.
            validation, refinement, rule_proposal = self.proposal_validator.validate(
                sir=sir,
                dataset_meta=selected_dataset_meta,
                check_configs=check_configs,
            )
            if validation.dq_flow_convertible:
                proposal_status = "valid_rule_proposal"
            elif has_questions or (
                refinement
                and refinement.reason
                in {
                    "missing_dataset",
                    "ambiguous_dataset",
                    "unknown_dataset",
                    "missing_column",
                    "unknown_column",
                    "ambiguous_column",
                    "missing_threshold",
                    "missing_allowed_values",
                    "low_confidence",
                }
            ):
                proposal_status = "needs_refinement"
            else:
                proposal_status = "invalid_request"

            return ParseRuleResponse(
                request_id=str(nl_request.id),
                parse_result_id=str(parse_result.id),
                parsed_rule=sir,
                status=response_status,
                proposal_status=proposal_status,
                rule_proposal=rule_proposal,
                validation=validation,
                refinement=refinement,
                suggestions=[],
                clarifying_questions=sir.clarifying_questions if has_questions else [],
                clarification_context=sir.clarification_context if has_questions else None,
                check_configs=check_configs,
                detected_datasets=detected_datasets if detected_datasets else None,
                detected_columns=detected_columns if detected_columns else None,
                explainability=explainability,
                trust_summary=trust_summary,
                decomposition_summary=decomposition_summary,
            )

        except Exception as e:
            logger.error(f"Parse error for request {nl_request.id}: {e}", exc_info=True)
            # F129: When the LLM returns a structurally valid response that
            # nevertheless fails our Pydantic schema (e.g. on a vague prompt
            # like "salary should be reasonable"), surface this as a
            # graceful "needs_refinement" instead of a hard parse_error so
            # the UI can prompt the user for clarification rather than a
            # red error toast.
            try:
                from pydantic import ValidationError as _PydValidationError
            except Exception:  # pragma: no cover
                _PydValidationError = ()  # type: ignore[assignment]
            if isinstance(e, _PydValidationError):
                nl_request.status = "cannot_interpret"
                db.commit()
                return ParseRuleResponse(
                    request_id=str(nl_request.id),
                    parsed_rule=None,
                    status="cannot_interpret",
                    proposal_status="needs_refinement",
                    refinement=RefinementGuidance(
                        reason="ambiguous_prompt",
                        message=(
                            "I could not extract a precise data quality "
                            "rule from this prompt. Please be more specific "
                            "about the column, the condition, and any "
                            "thresholds or allowed values."
                        ),
                        next_question=(
                            "Which column and what specific condition should the rule check?"
                        ),
                        field="rule_text",
                    ),
                    reason="Prompt is too vague to produce a structured rule",
                    suggestions=[
                        "Name the dataset and column explicitly",
                        "State the condition (e.g. 'greater than 0', "
                        "'one of ACTIVE/INACTIVE', 'must not be null')",
                    ],
                )
            nl_request.status = "parse_error"
            db.commit()
            return ParseRuleResponse(
                request_id=str(nl_request.id),
                parsed_rule=None,
                status="parse_error",
                proposal_status="invalid_request",
                reason=self._map_llm_exception_to_reason(e),
                suggestions=["Please try again"],
            )

    async def _invoke_llm_with_retry(self, prompt: str) -> dict | None:
        """Invoke LLM with one retry on invalid JSON.

        Returns parsed dict or None on complete failure.
        """
        last_exception: Exception | None = None
        for attempt in range(2):
            try:
                raw_json = await self._invoke_llm(prompt)
                if raw_json is not None:
                    return raw_json
                # Invalid JSON — retry with stricter prompt note
                if attempt == 0:
                    prompt += "\n\nIMPORTANT: Your previous response was not valid JSON. Output ONLY a valid JSON object."
                    logger.warning("LLM returned invalid JSON, retrying with stricter prompt")
            except Exception as e:
                logger.error(f"LLM invocation attempt {attempt + 1} failed: {e}")
                last_exception = e
                if attempt == 0:
                    continue
        if last_exception is not None:
            raise last_exception
        return None

    async def _invoke_llm(self, prompt: str) -> dict | None:
        """Invoke the LLM and parse the response as JSON.

        Returns parsed dict or None if response is not valid JSON.
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a data quality rule parser. Output ONLY valid JSON matching the provided schema. Never output code, SQL, or explanations.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
                timeout=10.0,
            )

            raw_content = response.choices[0].message.content
            if not raw_content:
                return None

            return json.loads(raw_content)

        except json.JSONDecodeError:
            logger.warning("LLM response was not valid JSON")
            return None
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    def _validate_and_build_sir(
        self,
        raw_output: dict,
        rule_text: str,
        context: dict | None,
    ) -> StructuredIntermediateRepresentation | None:
        """Validate LLM output and build a typed SIR object.

        Returns None if the output represents an uninterpretable rule.
        """
        try:
            # Check for unknown/uninterpretable
            rule_type_str = raw_output.get("rule_type", "unknown")
            if rule_type_str == "unknown" or rule_type_str not in SUPPORTED_RULE_TYPES:
                # Try to map using NL variations
                hint = detect_rule_type_hint(rule_text)
                if hint and hint in SUPPORTED_RULE_TYPES:
                    raw_output["rule_type"] = hint
                elif rule_type_str not in SUPPORTED_RULE_TYPES:
                    return None

            # Handle the case where rule_type is still "unknown" after hint check
            if raw_output.get("rule_type") == "unknown":
                confidence = raw_output.get("confidence", 0.0)
                if confidence < 0.3:
                    return None

            # Build subject entity
            subject_data = raw_output.get("subject", {})
            if not subject_data or not subject_data.get("raw_text"):
                return None

            subject = SIREntity(
                raw_text=subject_data["raw_text"],
                matched_glossary_term_id=subject_data.get("matched_glossary_term_id"),
            )

            # Build object entity (optional)
            obj = None
            object_data = raw_output.get("object")
            if object_data and isinstance(object_data, dict) and object_data.get("raw_text"):
                obj = SIREntity(
                    raw_text=object_data["raw_text"],
                    matched_glossary_term_id=object_data.get("matched_glossary_term_id"),
                )

            # Build scope
            scope_data = raw_output.get("scope", {})
            scope = SIRScope(
                dataset_hint=scope_data.get("dataset_hint")
                or (context.get("dataset_id") if context else None),
                domain_hint=scope_data.get("domain_hint")
                or (context.get("domain") if context else None),
                source_system_hint=scope_data.get("source_system_hint")
                or (context.get("source_system") if context else None),
            )

            # Build conditions
            conditions = []
            for cond_data in raw_output.get("conditions", []):
                if isinstance(cond_data, dict) and cond_data.get("field"):
                    from app.schemas.nl_rule_builder import SIRCondition

                    field_data = cond_data["field"]
                    conditions.append(
                        SIRCondition(
                            field=SIREntity(
                                raw_text=field_data.get("raw_text", ""),
                                matched_glossary_term_id=field_data.get("matched_glossary_term_id"),
                            ),
                            operator=cond_data.get("operator", "equals"),
                            value=cond_data.get("value"),
                        )
                    )

            sir = StructuredIntermediateRepresentation(
                schema_version="1.0",
                rule_type=RuleType(raw_output["rule_type"]),
                subject=subject,
                operator=raw_output.get("operator"),
                object=obj,
                scope=scope,
                conditions=conditions,
                constraints=raw_output.get("constraints", []),
                confidence=max(0.0, min(1.0, float(raw_output.get("confidence", 0.5)))),
                requires_disambiguation=raw_output.get("requires_disambiguation", False),
                parse_warnings=raw_output.get("parse_warnings", []),
                clarifying_questions=self._extract_clarifying_questions(raw_output),
            )

            # Extract & persist check_dimension / check_subtype / subtype_config
            # from the LLM output. The LLM is asked to emit them at top level
            # (preferred), but we also tolerate them inside check_config for
            # backward compatibility.
            self._extract_subtype_into_sir(sir, raw_output)

            return sir

        except Exception as e:
            logger.warning(f"Failed to build SIR from LLM output: {e}")
            return None

    @staticmethod
    def _attach_glossary_matches(
        sir: StructuredIntermediateRepresentation,
        raw_output: dict,
        glossary_terms: list[GlossaryPromptTerm],
    ) -> StructuredIntermediateRepresentation:
        """Attach validated glossary matches to SIR and clear invalid IDs."""
        if not glossary_terms:
            sir.glossary_context = []
            return sir

        valid_ids = {str(t.term_id) for t in glossary_terms}
        by_id = {str(t.term_id): t for t in glossary_terms}
        context_items: list[GlossaryContextItem] = []

        def register_match(term_id: str | None, reason: str) -> bool:
            if not term_id or term_id not in valid_ids:
                return False
            term = by_id[term_id]
            context_items.append(
                GlossaryContextItem(
                    term_id=term_id,
                    business_name=term.business_name,
                    match_reason=reason,
                )
            )
            return True

        if sir.subject:
            matched = register_match(sir.subject.matched_glossary_term_id, "subject")
            if not matched:
                sir.subject.matched_glossary_term_id = None

        if sir.object:
            matched = register_match(sir.object.matched_glossary_term_id, "object")
            if not matched:
                sir.object.matched_glossary_term_id = None

        for cond in sir.conditions:
            if cond.field:
                matched = register_match(cond.field.matched_glossary_term_id, "condition")
                if not matched:
                    cond.field.matched_glossary_term_id = None

        # De-duplicate while preserving order.
        seen = set()
        deduped: list[GlossaryContextItem] = []
        for item in context_items:
            key = (item.term_id, item.match_reason)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        sir.glossary_context = deduped
        return sir

    @staticmethod
    def _boost_confidence_for_glossary_match(
        sir: StructuredIntermediateRepresentation,
    ) -> StructuredIntermediateRepresentation:
        """Boost confidence when parser produced validated glossary matches."""
        if sir.glossary_context:
            sir.confidence = min(1.0, sir.confidence + 0.10)
        return sir

    def _apply_confidence_logic(
        self, sir: StructuredIntermediateRepresentation
    ) -> StructuredIntermediateRepresentation:
        """Apply disambiguation threshold rules to the SIR."""
        if sir.confidence < DISAMBIGUATION_THRESHOLD:
            sir.requires_disambiguation = True
            if not any("low confidence" in w.lower() for w in sir.parse_warnings):
                sir.parse_warnings.append(
                    f"Confidence ({sir.confidence:.2f}) is below threshold ({DISAMBIGUATION_THRESHOLD}). User confirmation recommended."
                )
        return sir

    # ------------------------------------------------------------------ #
    # Subtype capture & clarification (CRITICAL — drives flow generation)  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_subtype_into_sir(
        sir: StructuredIntermediateRepresentation,
        raw_output: dict,
    ) -> None:
        """Persist `check_dimension`, `check_subtype`, `subtype_config` from raw LLM output into the SIR.

        The LLM is asked to emit these at the top level. We also accept them
        inside the `check_config` block for backward compatibility, and finally
        fall back to deriving (dimension, subtype) from `RULE_TYPE_MAP` when
        the LLM omitted them.
        """
        # Top-level (preferred)
        dim = raw_output.get("check_dimension")
        sub = raw_output.get("check_subtype")
        sub_cfg = raw_output.get("subtype_config")

        # Fallback: nested inside check_config
        check_config = raw_output.get("check_config") or {}
        if not dim:
            dim = check_config.get("check_dimension")
        if not sub:
            sub = check_config.get("check_subtype")
        if not isinstance(sub_cfg, dict) or not sub_cfg:
            nested = check_config.get("config")
            if isinstance(nested, dict):
                sub_cfg = nested

        # Final fallback: derive from RULE_TYPE_MAP
        rule_type_str = sir.rule_type.value
        if (not dim or not sub) and rule_type_str in RULE_TYPE_MAP:
            mapped_dim, mapped_sub = RULE_TYPE_MAP[rule_type_str]
            dim = dim or mapped_dim
            sub = sub or mapped_sub

        # Whitelist subtype against the canonical inventory; if invalid, fall
        # back to the RULE_TYPE_MAP-derived subtype.
        if dim and sub:
            valid_subs = set(get_subtypes(dim))
            if valid_subs and sub not in valid_subs:
                if rule_type_str in RULE_TYPE_MAP:
                    mapped_dim, mapped_sub = RULE_TYPE_MAP[rule_type_str]
                    if mapped_dim == dim and mapped_sub in valid_subs:
                        sub = mapped_sub
                if sub not in valid_subs:
                    sir.parse_warnings.append(
                        f"LLM proposed unknown subtype '{sub}' for dimension '{dim}'. Falling back."
                    )
                    # Pick first valid subtype as a last resort so downstream
                    # validation still emits useful clarifying questions
                    sub = next(iter(valid_subs))

        sir.check_dimension = dim
        sir.check_subtype = sub
        if isinstance(sub_cfg, dict):
            # Normalise: drop nested objects we don't expect, keep scalars/lists/strings
            sir.subtype_config = {k: v for k, v in sub_cfg.items() if v is not None}
        else:
            sir.subtype_config = {}

    @staticmethod
    def _merge_clarification_answers_into_subtype(
        sir: StructuredIntermediateRepresentation,
        clarification_answers: dict | None,
    ) -> None:
        """Merge user-supplied clarification answers into the SIR's subtype
        capture (deterministic safety net — independent of the LLM picking
        them up on a re-parse).

        Recognised keys:
            - "check_dimension"    → sets sir.check_dimension
            - "check_subtype"      → sets sir.check_subtype (must be valid for the dimension)
            - any inventory field  → goes into sir.subtype_config[<key>]
        """
        if not clarification_answers:
            return

        # 1) Direct dimension/subtype overrides
        new_dim = clarification_answers.get("check_dimension")
        if isinstance(new_dim, str) and new_dim in SUBTYPE_INVENTORY:
            sir.check_dimension = new_dim

        new_sub = clarification_answers.get("check_subtype")
        if isinstance(new_sub, str) and sir.check_dimension:
            valid = set(get_subtypes(sir.check_dimension))
            if new_sub in valid:
                sir.check_subtype = new_sub

        # 2) Per-config-field answers — only for the active (dim, sub)
        if sir.check_dimension and sir.check_subtype:
            meta = get_subtype_meta(sir.check_dimension, sir.check_subtype)
            if meta:
                inventory_keys = {f[0] for f in meta.get("fields", [])}
                merged = dict(sir.subtype_config or {})
                for key, value in clarification_answers.items():
                    if key in inventory_keys and value not in (None, ""):
                        merged[key] = value
                sir.subtype_config = merged

    def _ensure_subtype_clarifications(
        self,
        sir: StructuredIntermediateRepresentation,
    ) -> None:
        """Emit clarifying questions when the chosen subtype is ambiguous or
        when required subtype-specific config fields are missing.

        Behaviour is governed by two settings (default to env-level config):
            - `NL_PARSER_ALWAYS_ASK_SUBTYPE` (bool): when True, always ask the
              user to confirm the subtype, even at high confidence.
            - `NL_PARSER_CONFIDENCE_THRESHOLD` (float): when the parser's
              confidence is below this threshold, ask a subtype-disambiguation
              question.
        """
        from app.schemas.nl_rule_builder import ClarifyingQuestion

        always_ask = bool(getattr(settings, "NL_PARSER_ALWAYS_ASK_SUBTYPE", False))
        threshold = float(getattr(settings, "NL_PARSER_CONFIDENCE_THRESHOLD", 0.80))

        dim = sir.check_dimension
        sub = sir.check_subtype
        if not dim or not sub:
            return  # _extract_subtype_into_sir already logged a warning

        existing_fields = {(q.field or "").lower() for q in sir.clarifying_questions}

        # 1) Subtype disambiguation question
        should_ask_subtype = always_ask or sir.confidence < threshold
        if should_ask_subtype and "check_subtype" not in existing_fields:
            options = get_subtypes(dim)
            if len(options) > 1:
                option_lines = []
                for s in options:
                    meta = get_subtype_meta(dim, s) or {}
                    label = meta.get("label", s)
                    desc = meta.get("description", "")
                    option_lines.append(f"{s} — {label}: {desc}")
                sir.clarifying_questions.append(
                    ClarifyingQuestion(
                        field="check_subtype",
                        question=(
                            f"Which {dim} subtype best matches your intent?"
                            f" Currently selected: {sub}."
                        ),
                        options=options,
                        answer_type="single_select",
                        required=True,
                        rationale=(
                            "The "
                            f"{dim} dimension has multiple subtypes with different "
                            "configurations. Picking the right one ensures the "
                            "generated check node behaves correctly. Candidates: "
                            + " | ".join(option_lines)
                        ),
                    )
                )
                sir.requires_disambiguation = True

        # 2) Per-required-field clarifications
        missing_fields = validate_subtype_config(dim, sub, sir.subtype_config)
        if not missing_fields:
            return

        meta = get_subtype_meta(dim, sub) or {}
        sub_label = meta.get("label", sub)

        # Index existing config-field-level questions to avoid duplicates
        for key, type_hint, _required, options in missing_fields:
            if key in existing_fields:
                continue
            answer_type, opts_list = self._field_to_question_type(type_hint, options)
            question_text = self._field_to_question_text(dim, sub_label, key, type_hint, options)
            sir.clarifying_questions.append(
                ClarifyingQuestion(
                    field=key,
                    question=question_text,
                    options=opts_list,
                    answer_type=answer_type,
                    required=True,
                    rationale=(
                        f"'{key}' is required to fully configure a "
                        f"{dim}/{sub} check. Without it, the generated flow "
                        "node will be incomplete."
                    ),
                )
            )
            sir.requires_disambiguation = True

    @staticmethod
    def _field_to_question_type(
        type_hint: str,
        options: tuple | None,
    ) -> tuple[str, list]:
        """Map an inventory field type-hint to a ClarifyingQuestion answer_type."""
        if options:
            return "single_select", list(options)
        if type_hint == "number":
            return "numeric", []
        if type_hint in ("list", "columns"):
            return "multi_select", []
        return "free_text", []

    @staticmethod
    def _field_to_question_text(
        dimension: str,
        subtype_label: str,
        key: str,
        type_hint: str,
        options: tuple | None,
    ) -> str:
        """Compose a friendly question for a missing required config field."""
        readable = key.replace("_", " ")
        if options:
            return f"For the {subtype_label} check, which {readable} should we use?"
        if type_hint == "number":
            return f"For the {subtype_label} check, what value should {readable} be?"
        if type_hint in ("column",):
            return f"For the {subtype_label} check, which column should we use as {readable}?"
        if type_hint in ("columns", "list"):
            return f"For the {subtype_label} check, please provide the {readable}."
        if type_hint == "expression":
            return f"For the {subtype_label} check, please provide the {readable} expression."
        return f"For the {subtype_label} check, please provide the {readable}."

    @staticmethod
    def _extract_clarifying_questions(raw_output: dict) -> list:
        """Extract clarifying_questions from LLM output into ClarifyingQuestion models."""
        from app.schemas.nl_rule_builder import ClarifyingQuestion

        questions = []
        raw_qs = raw_output.get("clarifying_questions", [])
        for q in raw_qs:
            if isinstance(q, dict) and q.get("question"):
                # E1 — derive typed answer_type if LLM didn't supply one
                raw_at = (q.get("answer_type") or "").strip().lower()
                allowed = {"single_select", "multi_select", "free_text", "numeric"}
                if raw_at in allowed:
                    answer_type = raw_at
                else:
                    field_l = (q.get("field") or "").lower()
                    if q.get("options"):
                        answer_type = "single_select"
                    elif any(
                        k in field_l
                        for k in (
                            "threshold",
                            "min",
                            "max",
                            "limit",
                            "count",
                            "pct",
                            "percent",
                            "days",
                            "hours",
                        )
                    ):
                        answer_type = "numeric"
                    else:
                        answer_type = "free_text"
                questions.append(
                    ClarifyingQuestion(
                        field=q.get("field", "general"),
                        question=q["question"],
                        options=q.get("options", []),
                        required=q.get("required", True),
                        answer_type=answer_type,
                        min_value=q.get("min_value"),
                        max_value=q.get("max_value"),
                        rationale=q.get("rationale")
                        or _default_rationale(
                            q.get("field", "general"),
                            answer_type,
                        ),
                    )
                )
        return questions

    # ------------------------------------------------------------------ #
    # F126 — Compound Decomposition                                        #
    # ------------------------------------------------------------------ #

    def _detect_and_decompose(
        self,
        sir: StructuredIntermediateRepresentation,
        raw_output: dict,
    ) -> StructuredIntermediateRepresentation:
        """Detect compound obligations from LLM output and decompose into atomic SIRs.

        If LLM set is_compound=True and provided obligations, builds atomic SIR objects
        from each obligation dict and attaches them to the parent SIR.

        Fallback: if is_compound=True but obligations is absent/empty → single-obligation path.
        Validation: if len(obligations) > 10 → requires_disambiguation=True + warning.
        """
        if not raw_output.get("is_compound", False):
            return sir

        obligations_raw = raw_output.get("obligations")
        if not obligations_raw or not isinstance(obligations_raw, list):
            sir.parse_warnings.append(
                "Compound marker set but no obligations extracted — treating as single obligation."
            )
            return sir

        # Validate obligation_logic
        obligation_logic = raw_output.get("obligation_logic")
        valid_logics = {"AND", "OR", "INDEPENDENT"}
        if obligation_logic is not None and obligation_logic not in valid_logics:
            sir.parse_warnings.append(
                f"Unknown obligation logic '{obligation_logic}'. Defaulting to INDEPENDENT."
            )
            obligation_logic = "INDEPENDENT"

        # Reject if count > 10
        if len(obligations_raw) > 10:
            sir.requires_disambiguation = True
            sir.parse_warnings.append("Too many obligations (max 10). Split into separate rules.")
            return sir

        # Build atomic SIRs
        obligations = []
        for ob_raw in obligations_raw:
            if not isinstance(ob_raw, dict):
                continue
            atomic = self._validate_and_build_sir(ob_raw, ob_raw.get("rule_text", ""), None)
            if atomic is not None:
                obligations.append(atomic)

        if not obligations:
            sir.parse_warnings.append(
                "Compound marker set but no obligations extracted — treating as single obligation."
            )
            return sir

        sir.is_compound = True
        sir.obligation_logic = obligation_logic
        sir.obligations = obligations
        return sir

    # ------------------------------------------------------------------ #
    # F126 — Inline Parameter Extraction                                   #
    # ------------------------------------------------------------------ #

    def _apply_inline_extraction(
        self,
        sir: StructuredIntermediateRepresentation,
        raw_output: dict,
    ) -> StructuredIntermediateRepresentation:
        """Deterministic post-processor: extract inline parameters from LLM output
        and normalise them into SIR fields.

        Extracts: operator (via OPERATOR_ALIASES), threshold_pass/warn, allowed_values,
        reference_dataset, inline_severity, conditions logic_operator, nesting depth.

        Never raises — all extraction errors produce parse_warnings.
        """
        from difflib import get_close_matches

        from app.services.nl_compiler.mappings import OPERATOR_ALIASES

        SEVERITY_ALIASES = {"critical", "high", "medium", "low", "info"}

        # ── 1. Operator normalisation ────────────────────────────────────
        raw_op = raw_output.get("operator")
        if raw_op and isinstance(raw_op, str):
            normalised = OPERATOR_ALIASES.get(raw_op.lower(), OPERATOR_ALIASES.get(raw_op, raw_op))
            sir.operator = normalised

        # ── 2. Threshold extraction and validation ───────────────────────
        llm_thresholds = (raw_output.get("check_config") or {}).get("thresholds") or {}

        def _safe_float(val) -> float | None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        def _clamp(v: float) -> float:
            return max(0.0, min(100.0, v))

        # Check_config path
        tp = _safe_float(llm_thresholds.get("threshold_pass"))
        if tp is not None:
            if tp < 0 or tp > 100:
                sir.parse_warnings.append(f"Invalid threshold value {tp}. Clamped to [0, 100].")
            sir.threshold_pass = _clamp(tp)

        tw = _safe_float(llm_thresholds.get("threshold_warn"))
        if tw is not None:
            tw = _clamp(tw)
            if sir.threshold_pass is not None and tw > sir.threshold_pass:
                sir.parse_warnings.append(
                    "Warning threshold exceeds pass threshold. Resetting to pass threshold."
                )
                tw = sir.threshold_pass
            sir.threshold_warn = tw

        # Top-level threshold_pass/warn (simpler LLM extraction path)
        if sir.threshold_pass is None:
            top_tp = _safe_float(raw_output.get("threshold_pass"))
            if top_tp is not None:
                if top_tp < 0 or top_tp > 100:
                    sir.parse_warnings.append(
                        f"Invalid threshold value {top_tp}. Clamped to [0, 100]."
                    )
                sir.threshold_pass = _clamp(top_tp)

        if sir.threshold_warn is None:
            top_tw = _safe_float(raw_output.get("threshold_warn"))
            if top_tw is not None:
                top_tw = _clamp(top_tw)
                if sir.threshold_pass is not None and top_tw > sir.threshold_pass:
                    sir.parse_warnings.append(
                        "Warning threshold exceeds pass threshold. Resetting to pass threshold."
                    )
                    top_tw = sir.threshold_pass
                sir.threshold_warn = top_tw

        # Absolute threshold (when total rows unknown)
        abs_threshold = raw_output.get("threshold_absolute")
        if abs_threshold is not None:
            abs_val = _safe_float(abs_threshold)
            if abs_val is not None:
                sir.parse_warnings.append(
                    "Absolute threshold stored; convert to % when total_rows is available."
                )
                sir.constraints.append({"threshold_absolute": abs_val})

        # ── 3. Allowed values extraction ─────────────────────────────────
        raw_allowed = raw_output.get("allowed_values")
        if raw_allowed is None:
            raw_allowed = (
                (raw_output.get("check_config") or {}).get("config", {}).get("allowedValues")
            )
        if isinstance(raw_allowed, list):
            if not raw_allowed:
                sir.parse_warnings.append("Allowed values list was empty after extraction.")
            else:
                seen: set = set()
                deduped = []
                for v in raw_allowed:
                    if isinstance(v, str):
                        v = v.strip("\"'")
                    key = v.lower() if isinstance(v, str) else v
                    if key not in seen:
                        seen.add(key)
                        deduped.append(v)
                sir.constraints = list(deduped)

        # ── 4. Reference dataset extraction ──────────────────────────────
        ref_ds = raw_output.get("reference_dataset") or (
            (raw_output.get("check_config") or {}).get("config", {}).get("referenceDataset")
        )
        if ref_ds is not None:
            if isinstance(ref_ds, str) and ref_ds.strip():
                if not sir.scope.dataset_hint:
                    sir.scope.dataset_hint = ref_ds.strip()
            elif isinstance(ref_ds, str):
                sir.parse_warnings.append("Reference dataset name was empty after extraction.")

        # ── 5. Inline severity extraction + fuzzy match ───────────────────
        raw_sev = raw_output.get("inline_severity") or raw_output.get("severity")
        if raw_sev and isinstance(raw_sev, str):
            raw_sev_lower = raw_sev.lower().strip()
            if raw_sev_lower in SEVERITY_ALIASES:
                sir.inline_severity = raw_sev_lower
            else:
                matches = get_close_matches(raw_sev_lower, list(SEVERITY_ALIASES), n=1, cutoff=0.7)
                if matches:
                    sir.inline_severity = matches[0]
                    sir.parse_warnings.append(
                        f"Inline severity '{raw_sev}' fuzzy-matched to '{matches[0]}'."
                    )
                else:
                    sir.parse_warnings.append(
                        f"Inline severity '{raw_sev}' not recognized. Using default."
                    )

        # ── 6. Conditions: populate logic_operator and nested_conditions ──
        raw_conditions = raw_output.get("conditions") or []
        if isinstance(raw_conditions, list) and sir.conditions:
            for cond_sir, cond_raw in zip(sir.conditions, raw_conditions):
                if isinstance(cond_raw, dict):
                    logic_op = cond_raw.get("logic_operator")
                    if logic_op:
                        cond_sir.logic_operator = logic_op

        # ── 7. Nesting depth guard (flatten to max 3 levels) ─────────────
        def _nesting_depth(cond, depth: int = 1) -> int:
            if not cond.nested_conditions:
                return depth
            return max(_nesting_depth(c, depth + 1) for c in cond.nested_conditions)

        def _flatten_to(cond, max_depth: int, current: int = 1) -> None:
            if current >= max_depth:
                cond.nested_conditions = []
                return
            for c in cond.nested_conditions:
                _flatten_to(c, max_depth, current + 1)

        for cond in sir.conditions:
            if _nesting_depth(cond) > 3:
                _flatten_to(cond, max_depth=3)
                if not any("too deep" in w.lower() for w in sir.parse_warnings):
                    sir.parse_warnings.append("Condition nesting too deep. Simplified to 3 levels.")

        return sir

    def _build_context(self, request: ParseRuleRequest) -> dict | None:
        """Build context dict from optional fields in the request."""
        context: dict[str, Any] = {}
        if request.dataset_id:
            context["dataset_id"] = request.dataset_id
        if request.domain:
            context["domain"] = request.domain
        if request.source_system:
            context["source_system"] = request.source_system
        if request.rule_category:
            context["rule_category"] = request.rule_category
        if request.severity:
            context["severity"] = request.severity
        if request.tags:
            context["tags"] = request.tags
        if request.clarification_answers:
            context["clarification_answers"] = request.clarification_answers
        if request.clarification_history:
            # F1 — feed prior Q/A turns to the prompt so refinements have context.
            context["clarification_history"] = [
                {
                    "field": t.field,
                    "question": t.question,
                    "answer": t.answer,
                    "answered_at": t.answered_at,
                }
                for t in request.clarification_history
            ]
        return context if context else None

    @staticmethod
    def _fetch_workspace_dataset_names(db: Session, workspace_id: uuid.UUID) -> list[str]:
        """Fetch up to 50 dataset names from the workspace to provide context to the LLM."""
        try:
            from app.services.datasets.models import DatasetListFilters
            from app.services.datasets.repository import DatasetRepository

            repo = DatasetRepository()
            filters = DatasetListFilters(limit=50, offset=0)
            result = repo.list_datasets(db, workspace_id=workspace_id, filters=filters)
            return [m.dataset_name for m in result.items if m.dataset_name]
        except Exception as e:
            logger.warning("Failed to fetch workspace datasets for context: %s", e)
            return []

    def _build_check_configs(
        self,
        sir: StructuredIntermediateRepresentation,
        raw_output: dict,
        request: ParseRuleRequest,
    ) -> list[CheckConfigOutput]:
        """Build full check node configs from the parsed SIR and LLM output.

        This produces the exact config structure needed for check nodes,
        matching dq_expected_results format.
        """
        # F129: when the prompt was compound (e.g. "email must not be null
        # AND country_code must be 2 letters AND name must be ≥ 3 chars"),
        # emit one CheckConfigOutput per obligation rather than collapsing
        # them all into the top-level subject. Each obligation is itself a
        # SIR, so we just recurse per-obligation.
        if sir.is_compound and sir.obligations:
            obligations_raw = raw_output.get("obligations") or []
            configs: list[CheckConfigOutput] = []
            for i, ob in enumerate(sir.obligations):
                ob_raw = obligations_raw[i] if i < len(obligations_raw) else {}
                if not isinstance(ob_raw, dict):
                    ob_raw = {}
                try:
                    sub_configs = self._build_check_configs(ob, ob_raw, request)
                except Exception:  # pragma: no cover — never let one bad ob crash all
                    sub_configs = []
                configs.extend(sub_configs)
            if configs:
                return configs
            # Fall through to atomic build only if all obligations failed.

        rule_type = sir.rule_type.value

        # Get dimension and subtype from mapping
        if rule_type in RULE_TYPE_MAP:
            dimension, subtype = RULE_TYPE_MAP[rule_type]
        else:
            dimension = "completeness"
            subtype = "null"

        # Prefer values explicitly captured on the SIR (populated either by
        # the LLM at parse time or by clarification answers downstream).
        if sir.check_dimension:
            dimension = sir.check_dimension
        if sir.check_subtype:
            subtype = sir.check_subtype

        # Extract check_config from LLM output if available
        llm_check_config = raw_output.get("check_config", {})
        if llm_check_config and not sir.check_dimension:
            dimension = llm_check_config.get("check_dimension", dimension)
        if llm_check_config and not sir.check_subtype:
            subtype = llm_check_config.get("check_subtype", subtype)

        # Normalise subtype: the LLM occasionally emits values that don't match
        # any UI subtype (e.g. "single" for uniqueness). Whitelist against the
        # known set per dimension and fall back to the RULE_TYPE_MAP default.
        _VALID_SUBTYPES: dict[str, set[str]] = {
            "completeness": {
                "null",
                "empty",
                "placeholder",
                "conditional",
                "multi_field",
                "population",
                "group",
            },
            "uniqueness": {"exact", "composite", "scoped", "cross_dataset", "fuzzy", "temporal"},
            "validity": {
                "allowed_values",
                "range",
                "regex",
                "reference_lookup",
                "business_rule",
                "cross_field",
                "date_logic",
                "negative",
            },
            "conformity": {"standard", "regex", "length", "charset", "case", "structural"},
            "consistency": {
                "intra_record",
                "formula",
                "temporal",
                "inter_record",
                "cross_table",
                "aggregation",
            },
            "timeliness": {
                "freshness",
                "record_age",
                "latency",
                "processing_delay",
                "delivery_window",
                "heartbeat",
            },
            "accuracy": {
                "reference_comparison",
                "trusted_source",
                "tolerated_deviation",
                "statistical",
                "derived_value",
            },
            "reconciliation": {
                "record_count",
                "one_to_one",
                "aggregate",
                "field_level",
                "tolerance",
                "missing_extra",
            },
        }
        valid_for_dim = _VALID_SUBTYPES.get(dimension)
        if valid_for_dim and subtype not in valid_for_dim:
            # Fall back to RULE_TYPE_MAP default when available
            if rule_type in RULE_TYPE_MAP:
                _, subtype = RULE_TYPE_MAP[rule_type]
            else:
                subtype = next(iter(valid_for_dim))

        # Build config dict
        config = self._build_node_config(sir, raw_output, dimension, subtype)

        # Mirror form-field keys for the UI (snake_case) alongside the camelCase
        # keys consumed by the runtime check executor. Without these, the
        # check-node config panel renders empty because its schema fields are
        # snake_case (e.g., "allowed_values", "min_value", "scope_columns").
        _CAMEL_TO_SNAKE = {
            "allowedValues": "allowed_values",
            "caseSensitive": "case_sensitive",
            "minValue": "min_value",
            "maxValue": "max_value",
            "inclusiveMin": "inclusive_min",
            "inclusiveMax": "inclusive_max",
            "scopeColumns": "scope_columns",
            "fuzzyAlgorithm": "fuzzy_algorithm",
            "fuzzyThreshold": "fuzzy_threshold",
            "temporalColumn": "temporal_column",
            "temporalWindowValue": "temporal_window_value",
            "temporalWindowUnit": "temporal_window_unit",
            "minLength": "min_length",
            "maxLength": "max_length",
            "expectedCase": "expected_case",
            "allowedCharset": "allowed_charset",
            "standardName": "standard_name",
            "structuralPattern": "structural_pattern",
            "comparisonColumn": "comparison_column",
            "dateOperator": "date_operator",
            "referenceDataset": "reference_dataset",
            "referenceColumn": "reference_column",
            "businessRuleExpression": "business_rule_expression",
            "ruleExpression": "rule_expression",
            "groupByColumns": "group_by_columns",
            "startColumn": "start_column",
            "endColumn": "end_column",
            "aggregateFunction": "aggregate_function",
            "expectedColumn": "expected_column",
            "conditionColumn": "condition_column",
            "conditionOperator": "condition_operator",
            "conditionValue": "condition_value",
            "placeholderValues": "placeholder_values",
            "multiFieldMode": "multi_field_mode",
            "checkMode": "check_mode",
            "uniquenessMode": "uniqueness_mode",
            "validationType": "validation_type",
            "conformityType": "conformity_type",
            "consistencyType": "consistency_type",
        }
        for camel_key, snake_key in _CAMEL_TO_SNAKE.items():
            if camel_key in config and snake_key not in config:
                config[snake_key] = config[camel_key]

        # Build thresholds
        llm_thresholds = llm_check_config.get("thresholds", {}) if llm_check_config else {}
        defaults = DIMENSION_DEFAULTS.get(dimension, {})

        threshold_pass = llm_thresholds.get("threshold_pass", defaults.get("threshold_pass", 100))
        threshold_warn = llm_thresholds.get("threshold_warn", defaults.get("threshold_warn", 95))
        null_handling = llm_thresholds.get("null_handling", defaults.get("null_handling", "skip"))
        include_empty = llm_thresholds.get("include_empty_strings", False)

        # Override from constraints if user specified a threshold
        if sir.constraints:
            for c in sir.constraints:
                if isinstance(c, (int, float)) and 0 < c <= 100 and dimension == "completeness":
                    threshold_pass = c
                    threshold_warn = max(0, c - 5)

        # F126: override from inline-extracted threshold (takes precedence over constraints loop)
        if sir.threshold_pass is not None:
            threshold_pass = sir.threshold_pass
            threshold_warn = (
                sir.threshold_warn
                if sir.threshold_warn is not None
                else max(0.0, threshold_pass - 5)
            )

        # Override from request severity; F126: fall back to inline_severity
        severity = request.severity or sir.inline_severity or "medium"

        subject_col = sir.subject.resolved_column or sir.subject.raw_text
        # Prefer SIR's resolved dataset_id; fall back to the user-supplied
        # dataset selected in the UI (request.dataset_id) when resolution
        # didn't pin a physical dataset.
        dataset_id = sir.subject.dataset_id or request.dataset_id

        # Auto-generate rule name
        rule_name = f"{dimension}_{subtype}_{subject_col}".replace(" ", "_").lower()

        check_config = CheckConfigOutput(
            check_dimension=dimension,
            check_subtype=subtype,
            columns=[subject_col],
            dataset_id=dataset_id,
            dataset_name=sir.subject.resolved_dataset or sir.scope.dataset_hint,
            config=config,
            thresholds=ThresholdConfig(
                threshold_pass=threshold_pass,
                threshold_warn=threshold_warn,
                null_handling=null_handling,
                include_empty_strings=include_empty,
            ),
            severity=severity,
            rule_name=rule_name,
            description=f"Auto-generated from: {sir.subject.raw_text}",
        )

        return [check_config]

    def _build_node_config(
        self,
        sir: StructuredIntermediateRepresentation,
        raw_output: dict,
        dimension: str,
        subtype: str,
    ) -> dict[str, Any]:
        """Build the check-type-specific config dict matching dq_expected_results format."""
        subject_col = sir.subject.resolved_column or sir.subject.raw_text
        llm_config = raw_output.get("check_config", {}).get("config", {})

        # Start with LLM-produced config if available
        if llm_config:
            config = dict(llm_config)
            # Ensure columns is set
            if "columns" not in config:
                config["columns"] = [subject_col]
            # Merge SIR.subtype_config so any keys captured exhaustively by
            # the LLM at top level (or supplied via clarification answers)
            # are present in the node config.
            self._merge_subtype_config(config, sir.subtype_config)
            return config

        # Otherwise build from SIR
        config: dict[str, Any] = {"columns": [subject_col]}

        if dimension == "completeness":
            config["checkMode"] = subtype
            if subtype == "conditional" and sir.conditions:
                cond = sir.conditions[0]
                config["conditionColumn"] = cond.field.raw_text
                config["conditionOperator"] = cond.operator
                config["conditionValue"] = cond.value
            elif subtype == "placeholder" and sir.constraints:
                config["placeholderValues"] = sir.constraints
            elif subtype == "multi_field":
                cols = [subject_col]
                if sir.object and sir.object.raw_text:
                    cols.append(sir.object.raw_text)
                config["columns"] = cols
                config["multiFieldMode"] = "any"
            elif subtype == "group" and sir.object:
                config["groupByColumns"] = [sir.object.raw_text]

        elif dimension == "uniqueness":
            config["uniquenessMode"] = subtype
            if subtype == "composite":
                cols = [subject_col]
                if sir.object and sir.object.raw_text:
                    cols.append(sir.object.raw_text)
                if sir.constraints:
                    for c in sir.constraints:
                        if isinstance(c, str) and c not in cols:
                            cols.append(c)
                config["columns"] = cols
            elif subtype == "scoped" and sir.object:
                config["scopeColumns"] = [sir.object.raw_text]
            elif subtype == "fuzzy":
                config["fuzzyAlgorithm"] = "levenshtein"
                config["fuzzyThreshold"] = 0.8
            elif subtype == "temporal":
                config["temporalColumn"] = sir.object.raw_text if sir.object else "created_at"
                if sir.constraints and len(sir.constraints) >= 2:
                    config["temporalWindowValue"] = sir.constraints[0]
                    config["temporalWindowUnit"] = sir.constraints[1]

        elif dimension == "conformity":
            config["conformityType"] = subtype
            if subtype == "regex" and sir.constraints:
                config["pattern"] = str(sir.constraints[0])
            elif subtype == "length" and sir.constraints:
                if len(sir.constraints) >= 2:
                    config["minLength"] = sir.constraints[0]
                    config["maxLength"] = sir.constraints[1]
                elif len(sir.constraints) == 1:
                    config["maxLength"] = sir.constraints[0]
            elif subtype == "case":
                config["expectedCase"] = (
                    "upper" if sir.operator in ("upper", "uppercase") else "lower"
                )
            elif subtype == "charset":
                config["allowedCharset"] = sir.constraints[0] if sir.constraints else "alpha"
            elif subtype == "standard":
                config["standardName"] = sir.constraints[0] if sir.constraints else "email"
            elif subtype == "structural" and sir.constraints:
                config["structuralPattern"] = str(sir.constraints[0])

        elif dimension == "consistency":
            config["consistencyType"] = subtype
            if subtype == "intra_record" and sir.object:
                config["ruleExpression"] = (
                    f'CASE WHEN "{subject_col}" {sir.operator or ">"} "{sir.object.raw_text}" THEN TRUE ELSE FALSE END'
                )
            elif subtype == "formula":
                if sir.constraints:
                    parts = [f'"{c}"' if isinstance(c, str) else str(c) for c in sir.constraints]
                    config["ruleExpression"] = (
                        " * ".join(parts) if sir.operator == "equals" else " ".join(parts)
                    )
            elif subtype == "temporal" and sir.object:
                config["startColumn"] = subject_col
                config["endColumn"] = sir.object.raw_text
            elif subtype == "inter_record" and sir.object:
                config["groupByColumns"] = [sir.object.raw_text]
            elif subtype == "aggregation" and sir.object:
                config["aggregateFunction"] = "SUM"
                config["expectedColumn"] = sir.object.raw_text

        elif dimension == "validity":
            config["validationType"] = subtype
            if subtype == "allowed_values" and sir.constraints:
                config["allowedValues"] = sir.constraints
            elif subtype == "range" and sir.constraints:
                if len(sir.constraints) >= 2:
                    config["minValue"] = sir.constraints[0]
                    config["maxValue"] = sir.constraints[1]
            elif subtype == "date_logic" and sir.object:
                config["comparisonColumn"] = sir.object.raw_text
                config["dateOperator"] = (
                    "after" if sir.operator in ("greater_than", ">") else "before"
                )
            elif subtype == "reference_lookup" and sir.object:
                config["referenceDataset"] = sir.object.raw_text
                config["referenceColumn"] = sir.object.resolved_column or sir.object.raw_text
            elif subtype == "business_rule":
                if sir.constraints:
                    config["businessRuleExpression"] = str(sir.constraints[0])
            elif subtype == "cross_field" and sir.object:
                config["comparisonColumn"] = sir.object.raw_text
                config["comparisonOperator"] = sir.operator or "greater_equal"
            elif subtype == "negative":
                if sir.constraints:
                    config["negativePattern"] = str(sir.constraints[0])
                    config["negativeMatchMode"] = "regex"
            elif subtype == "regex" and sir.constraints:
                config["pattern"] = str(sir.constraints[0])

        elif dimension == "accuracy":
            config["accuracyType"] = subtype
            if subtype == "reference_comparison" and sir.object:
                config["referenceDataset"] = sir.object.raw_text
                config["joinKeys"] = sir.constraints if sir.constraints else []
            elif subtype == "tolerated_deviation":
                if sir.object:
                    config["referenceDataset"] = sir.object.raw_text
                if sir.constraints:
                    config["toleranceType"] = "absolute"
                    config["toleranceValue"] = sir.constraints[0]
            elif subtype == "statistical":
                config["statisticalMethod"] = "iqr"
                config["outlierThreshold"] = 1.5
            elif subtype == "derived_value":
                if sir.constraints:
                    parts = [f'"{c}"' if isinstance(c, str) else str(c) for c in sir.constraints]
                    config["formula"] = " * ".join(parts)

        elif dimension == "timeliness":
            config["timelinessType"] = subtype
            if subtype == "freshness":
                config["timestampColumn"] = subject_col
                if sir.constraints and len(sir.constraints) >= 2:
                    config["maxAgeValue"] = sir.constraints[0]
                    config["maxAgeUnit"] = sir.constraints[1]
            elif subtype == "record_age":
                config["timestampColumn"] = subject_col
                if sir.constraints and len(sir.constraints) >= 2:
                    config["maxAgeValue"] = sir.constraints[0]
                    config["maxAgeUnit"] = sir.constraints[1]
            elif subtype == "latency" and sir.object:
                config["eventTimestampColumn"] = subject_col
                config["loadTimestampColumn"] = sir.object.raw_text
                if sir.constraints and len(sir.constraints) >= 2:
                    config["maxLatencyValue"] = sir.constraints[0]
                    config["maxLatencyUnit"] = sir.constraints[1]
            elif subtype == "processing_delay" and sir.object:
                config["startTimestampColumn"] = subject_col
                config["endTimestampColumn"] = sir.object.raw_text
                if sir.constraints and len(sir.constraints) >= 2:
                    config["maxDelayValue"] = sir.constraints[0]
                    config["maxDelayUnit"] = sir.constraints[1]
            elif subtype == "delivery_window":
                config["timestampColumn"] = subject_col
                if sir.constraints and len(sir.constraints) >= 2:
                    config["windowStart"] = sir.constraints[0]
                    config["windowEnd"] = sir.constraints[1]
            elif subtype == "heartbeat":
                config["timestampColumn"] = subject_col
                if sir.constraints:
                    config["expectedFrequency"] = str(sir.constraints[0])

        elif dimension == "reconciliation":
            config["reconciliationType"] = subtype
            source = sir.subject.raw_text
            target = sir.object.raw_text if sir.object else ""
            config["sourceDataset"] = source
            config["targetDataset"] = target
            if subtype in ("one_to_one", "field_level", "tolerance", "missing_extra"):
                config["joinKeys"] = sir.constraints if sir.constraints else []
            if subtype == "field_level":
                config["compareColumns"] = sir.constraints if sir.constraints else []
            if subtype == "aggregate":
                config["aggregateFunction"] = "SUM"
                if sir.constraints:
                    config["aggregateColumn"] = str(sir.constraints[0])
            if subtype == "tolerance" and sir.constraints:
                config["toleranceType"] = "absolute"
                config["toleranceValue"] = sir.constraints[-1] if sir.constraints else 0

        # Final merge: SIR.subtype_config (canonical snake_case) is the most
        # authoritative source. Merge it last so values supplied by the LLM at
        # top level OR via clarification answers always take precedence.
        self._merge_subtype_config(config, sir.subtype_config)
        return config

    @staticmethod
    def _merge_subtype_config(
        config: dict[str, Any],
        subtype_config: dict[str, Any] | None,
    ) -> None:
        """Merge `subtype_config` (canonical snake_case) into `config` in place.

        SIR.subtype_config keys win over previously-set keys when they carry
        a non-empty value. Empty strings, empty lists, and None are treated
        as "not provided" and never overwrite existing values.
        """
        if not subtype_config:
            return
        for key, value in subtype_config.items():
            if value is None:
                continue
            if isinstance(value, str) and value.strip() == "":
                continue
            if isinstance(value, (list, tuple, dict)) and len(value) == 0:
                continue
            config[key] = value

    def _bind_dataset_to_checks(
        self,
        check_configs: list[CheckConfigOutput],
        dataset_meta: "DatasetMeta",
    ) -> None:
        """Propagate the resolved dataset id/name onto every check config and
        fuzzy-resolve column names against the dataset's actual schema.

        This is what makes prompts like "names should not be empty in
        customer profiles" actually convert into a valid DQ flow: the parser
        no longer requires the user to first hit the "select dataset"
        dropdown when the rule text already names the dataset.
        """
        ds_id = dataset_meta.dataset_id
        ds_name = dataset_meta.dataset_name
        col_names = dataset_meta.column_names()
        col_lookup = {c.lower(): c for c in col_names}

        for cc in check_configs:
            if not cc.dataset_id:
                cc.dataset_id = ds_id
            if not cc.dataset_name:
                cc.dataset_name = ds_name

            # Split composite uniqueness columns that arrived as one phrase
            # like "customer_id and registration_date" or "a, b, c". Apply
            # whenever the column slot looks like a multi-column phrase, not
            # only for uniqueness/composite, since other compound checks
            # (multi_field, group, scoped, …) suffer the same issue.
            if cc.columns:
                expanded: list[str] = []
                for col in cc.columns:
                    parts = self._split_multi_column(col)
                    expanded.extend(parts if parts else [col])
                # Deduplicate while preserving order
                seen: set[str] = set()
                unique: list[str] = []
                for c in expanded:
                    key = c.strip().lower()
                    if key and key not in seen:
                        seen.add(key)
                        unique.append(c.strip())
                cc.columns = unique

            # Fuzzy-resolve each column to a real dataset field.
            resolved_cols: list[str] = []
            for col in cc.columns or []:
                raw = (col or "").strip()
                if not raw:
                    continue
                if raw.lower() in col_lookup:
                    resolved_cols.append(col_lookup[raw.lower()])
                    continue
                fuzzy = self._fuzzy_match_column(raw, col_names)
                resolved_cols.append(fuzzy or raw)
            if resolved_cols:
                cc.columns = resolved_cols
                # Mirror the resolution onto the node config so the runtime
                # executor sees the real column names.
                if isinstance(cc.config, dict):
                    if cc.config.get("columns"):
                        cc.config["columns"] = resolved_cols
                    if "column" in cc.config and resolved_cols:
                        cc.config["column"] = resolved_cols[0]

    @staticmethod
    def _split_multi_column(raw: str) -> list[str]:
        """Split a phrase like 'a and b' / 'a, b and c' into ['a','b','c']."""
        if not raw or not isinstance(raw, str):
            return []
        # Normalize separators: ',', ';', ' & ', ' and '
        import re

        parts = re.split(r"\s*(?:,|;| and | & )\s*", raw, flags=re.IGNORECASE)
        return [p.strip() for p in parts if p and p.strip()]

    @staticmethod
    def _fuzzy_match_column(candidate: str, columns: list[str]) -> str | None:
        """Return the closest dataset column name for candidate, or None.

        Uses difflib's get_close_matches with a relatively forgiving cutoff so
        that 'names' resolves to 'customer_name' on tie-broken context.
        """
        import difflib

        if not candidate or not columns:
            return None
        cand = candidate.strip().lower()
        # Direct exact (case-insensitive) match.
        for col in columns:
            if col.lower() == cand:
                return col
        # Plural normalization: 'names' -> 'name'.
        cand_stem = cand[:-1] if cand.endswith("s") and len(cand) > 3 else cand
        # Token-based match: split column name on '_' and check if any token
        # equals the candidate or its singular form (handles 'names' ->
        # 'customer_name', 'phone' -> 'phone_number', 'email' -> 'email_addr').
        token_matches: list[str] = []
        for col in columns:
            tokens = [t.lower() for t in col.replace("-", "_").split("_") if t]
            if cand in tokens or cand_stem in tokens:
                token_matches.append(col)
        if len(token_matches) == 1:
            return token_matches[0]
        # Substring match — the candidate is contained in or contains a real
        # column (e.g. 'names' ⊂ 'customer_name').
        substring_matches = [
            col
            for col in columns
            if cand in col.lower() or col.lower() in cand or cand_stem in col.lower()
        ]
        if len(substring_matches) == 1:
            return substring_matches[0]
        # If we have multiple token matches, pick the shortest one (heuristic:
        # closest to the bare token).
        if len(token_matches) > 1:
            return min(token_matches, key=len)
        # difflib similarity fallback.
        names_lower = [c.lower() for c in columns]
        close = difflib.get_close_matches(cand, names_lower, n=1, cutoff=0.6)
        if close:
            idx = names_lower.index(close[0])
            return columns[idx]
        return None

    def _detect_datasets(
        self,
        db: Session,
        workspace_id: uuid.UUID,
        sir: StructuredIntermediateRepresentation,
        raw_output: dict,
    ) -> list[DetectedDataset]:
        """Auto-detect datasets from rule text, SIR scope hints, and workspace metadata."""
        detected = []
        hints = set()

        # Collect dataset hints from SIR
        if sir.scope.dataset_hint:
            hints.add(sir.scope.dataset_hint)
        subject_data = raw_output.get("subject", {})
        if isinstance(subject_data, dict) and subject_data.get("dataset_hint"):
            hints.add(subject_data["dataset_hint"])
        object_data = raw_output.get("object", {})
        if isinstance(object_data, dict) and object_data.get("dataset_hint"):
            hints.add(object_data["dataset_hint"])

        if not hints:
            return []

        # Try to match hints against workspace datasets
        try:
            from app.services.datasets.models import DatasetListFilters
            from app.services.datasets.repository import DatasetRepository

            repo = DatasetRepository()
            for hint in hints:
                filters = DatasetListFilters(search=hint, limit=3, offset=0)
                result = repo.list_datasets(db, workspace_id=workspace_id, filters=filters)
                if result.items:
                    for m in result.items:
                        detected.append(
                            DetectedDataset(
                                dataset_id=str(m.dataset_id) if m.dataset_id else None,
                                dataset_name=m.dataset_name,
                                data_source_name=getattr(m, "data_source_name", None),
                                match_score=1.0 if m.dataset_name.lower() == hint.lower() else 0.7,
                                match_reason=f"Matched dataset hint '{hint}'",
                            )
                        )
                else:
                    # No match found, return the hint as-is for user to resolve
                    detected.append(
                        DetectedDataset(
                            dataset_name=hint,
                            match_score=0.5,
                            match_reason=f"Dataset '{hint}' mentioned but not found in workspace. Please select.",
                        )
                    )
        except Exception as e:
            logger.warning("Dataset detection failed: %s", e)
            for hint in hints:
                detected.append(
                    DetectedDataset(
                        dataset_name=hint,
                        match_score=0.5,
                        match_reason=f"Dataset '{hint}' mentioned in rule text",
                    )
                )

        return detected

    def _detect_columns(self, sir: StructuredIntermediateRepresentation) -> list[DetectedColumn]:
        """Extract detected columns from the SIR."""
        columns = []
        columns.append(
            DetectedColumn(
                raw_text=sir.subject.raw_text,
                resolved_name=sir.subject.resolved_column,
                dataset_id=sir.subject.dataset_id,
                dataset_name=sir.subject.resolved_dataset,
                role="subject",
            )
        )
        if sir.object and sir.object.raw_text:
            columns.append(
                DetectedColumn(
                    raw_text=sir.object.raw_text,
                    resolved_name=sir.object.resolved_column,
                    dataset_id=sir.object.dataset_id,
                    dataset_name=sir.object.resolved_dataset,
                    role="object",
                )
            )
        for cond in sir.conditions:
            if cond.field and cond.field.raw_text:
                columns.append(
                    DetectedColumn(
                        raw_text=cond.field.raw_text,
                        role="condition",
                    )
                )
        return columns
