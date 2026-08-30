"""
NL Rule Builder API Endpoints
F099 — Natural Language Rule Parsing Service
F102 — Metadata Resolution and Ranking
F104 — NL Rule Compiler
F105 — NL Rule Flow Generator
F106 — NL Rule Audit Trail
F107 — NL Rule Test Preview
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.nl_rule import NLRuleParseResult, NLRuleRequest
from app.models.rule import DQRule
from app.models.user import User
from app.schemas.disambiguation import (
    DisambiguationAnswerRequest,
    DisambiguationAnswerResponse,
    DisambiguationSessionResponse,
    DisambiguationStartRequest,
    DisambiguationStartResponse,
)
from app.schemas.nl_audit import (
    AuditListResponse,
    AuditRecordCreate,
    AuditRecordResponse,
    ExplainabilityResponse,
    FeedbackCreate,
    FeedbackResponse,
)
from app.schemas.nl_compiler import CompiledCheckConfig, CompileRequest, CompileResponse
from app.schemas.nl_flow_generator import GenerateFlowRequest, GenerateFlowResponse
from app.schemas.nl_rule_builder import (
    CheckConfigOutput,
    ParseRuleRequest,
    ParseRuleResponse,
    SavedParseEntry,
    SavedParsesListResponse,
    ValidateParseRequest,
    ValidateParseResponse,
)
from app.schemas.nl_rule_test import TestPreviewRequest, TestPreviewResponse
from app.schemas.resolution import ResolveRequest, ResolveResponse
from app.services.auth.jwt import get_current_user
from app.services.nl_audit.service import NLAuditService
from app.services.nl_compiler.compiler import NLRuleCompiler
from app.services.nl_flow_generator.generator import NLFlowGenerator
from app.services.nl_rule_builder.dataset_metadata import load_dataset_meta
from app.services.nl_rule_builder.disambiguation_detector import DisambiguationDetector
from app.services.nl_rule_builder.disambiguation_planner import QuestionPlanner
from app.services.nl_rule_builder.disambiguation_sessions import DisambiguationSessionService
from app.services.nl_rule_builder.parser import NLRuleParserService
from app.services.nl_rule_builder.rule_proposal_validation import (
    RuleProposalValidationService,
)
from app.services.nl_rule_test.preview import NLRuleTestPreview
from app.services.resolution.engine import ResolutionEngine

router = APIRouter()

_parser_service = NLRuleParserService()
_resolution_engine = ResolutionEngine()
_disambiguation_detector = DisambiguationDetector()
_question_planner = QuestionPlanner()
_disambiguation_session_service = DisambiguationSessionService()
_compiler = NLRuleCompiler()
_flow_generator = NLFlowGenerator()
_audit_service = NLAuditService()
_test_preview = NLRuleTestPreview()
_proposal_validator = RuleProposalValidationService()


def _revalidate_parse_result(
    db: Session,
    workspace_id: UUID,
    parse_result: NLRuleParseResult,
):
    """Re-run RuleProposalValidationService against a saved parse_result.

    Returns (validation, refinement, rule_proposal). Used by /validate and
    /create-flow to enforce the spec §12 hard gate on the server side, even
    if the parse was created before validation was wired in.
    """
    from app.schemas.nl_rule_builder import (
        CheckConfigOutput,
        StructuredIntermediateRepresentation,
    )

    sir = None
    if parse_result.sir_json:
        try:
            sir = StructuredIntermediateRepresentation(**parse_result.sir_json)
        except Exception:
            sir = None
    check_configs = None
    if parse_result.check_configs:
        try:
            check_configs = [CheckConfigOutput(**cc) for cc in parse_result.check_configs]
        except Exception:
            check_configs = None
    # Locate dataset_id from any check_config — fall back to subject scope
    dataset_id = None
    if check_configs:
        for cc in check_configs:
            if cc.dataset_id:
                dataset_id = cc.dataset_id
                break
    if dataset_id is None and sir is not None and sir.subject and sir.subject.dataset_id:
        dataset_id = sir.subject.dataset_id
    dataset_meta = None
    if dataset_id:
        try:
            dataset_meta = load_dataset_meta(db, workspace_id, UUID(str(dataset_id)))
        except (ValueError, TypeError):
            dataset_meta = None
    return _proposal_validator.validate(
        sir=sir, dataset_meta=dataset_meta, check_configs=check_configs
    )


@router.post(
    "/workspaces/{workspace_id}/rule-builder/parse",
    response_model=ParseRuleResponse,
    status_code=status.HTTP_200_OK,
    summary="Parse a natural language data quality rule",
    description="Converts natural language rule text into a Structured Intermediate Representation (SIR). "
    "The LLM output is constrained to a strict JSON schema and never produces executable code.",
    tags=["rule-builder"],
)
async def parse_rule(
    workspace_id: UUID,
    request: ParseRuleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ParseRuleResponse:
    """Parse a natural language rule into a structured representation.

    Requires rules:create permission in the target workspace.
    """
    # Permission check — require rules:create
    # The current_user dependency already validates authentication.
    # For workspace-level permission, we check the user has access.
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    # Validate workspace_id format is handled by FastAPI UUID type
    # Additional workspace existence check could be added here
    # but is deferred to the service layer for consistency

    result = await _parser_service.parse_rule(
        db=db,
        workspace_id=workspace_id,
        request=request,
        user_id=current_user.id,
    )

    return result


# ── Saved Parses: List, Validate, Adjust ──


@router.get(
    "/workspaces/{workspace_id}/rule-builder/parses",
    response_model=SavedParsesListResponse,
    summary="List saved rule parses for a workspace",
    tags=["rule-builder"],
)
def list_parses(
    workspace_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    validated_only: bool | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SavedParsesListResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    query = (
        db.query(NLRuleRequest)
        .filter(NLRuleRequest.workspace_id == workspace_id)
        .order_by(NLRuleRequest.created_at.desc())
    )

    if validated_only is not None:
        query = query.join(NLRuleParseResult).filter(NLRuleParseResult.validated == validated_only)

    total = query.count()
    requests = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for req in requests:
        pr = req.parse_result
        items.append(
            SavedParseEntry(
                request_id=str(req.id),
                parse_result_id=str(pr.id) if pr else "",
                rule_text=req.rule_text,
                rule_type=pr.rule_type if pr else "unknown",
                confidence=pr.confidence if pr else 0.0,
                status=req.status,
                validated=pr.validated if pr else False,
                check_configs=[CheckConfigOutput(**cc) for cc in pr.check_configs]
                if pr and pr.check_configs
                else None,
                created_at=req.created_at.isoformat(),
                validated_at=pr.validated_at.isoformat() if pr and pr.validated_at else None,
            )
        )

    return SavedParsesListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post(
    "/workspaces/{workspace_id}/rule-builder/parses/{parse_result_id}/validate",
    response_model=ValidateParseResponse,
    summary="Validate or reject a parse result, optionally with adjustments",
    tags=["rule-builder"],
)
def validate_parse(
    workspace_id: UUID,
    parse_result_id: str,
    request: ValidateParseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValidateParseResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    parse_result = (
        db.query(NLRuleParseResult)
        .filter(
            NLRuleParseResult.id == parse_result_id,
        )
        .first()
    )

    if not parse_result:
        raise HTTPException(status_code=404, detail="Parse result not found")

    # Verify workspace ownership
    nl_request = (
        db.query(NLRuleRequest)
        .filter(
            NLRuleRequest.id == parse_result.request_id,
            NLRuleRequest.workspace_id == workspace_id,
        )
        .first()
    )
    if not nl_request:
        raise HTTPException(status_code=404, detail="Parse result not found in this workspace")

    # Spec §12 — backend gate: cannot mark a parse as user-validated unless
    # the proposal can be converted into a valid executable DQ flow.
    if request.validated:
        validation, refinement, _ = _revalidate_parse_result(db, workspace_id, parse_result)
        if not validation.dq_flow_convertible:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "rule_proposal_invalid",
                    "message": (
                        refinement.message
                        if refinement is not None
                        else "Rule proposal is not convertible to a valid DQ flow."
                    ),
                    "validation": validation.model_dump(),
                    "refinement": refinement.model_dump() if refinement else None,
                },
            )

    now = datetime.now(UTC)
    parse_result.validated = request.validated
    parse_result.validated_at = now
    parse_result.validated_by = current_user.id

    # Apply user adjustments if provided
    if request.adjustments:
        parse_result.user_adjustments = request.adjustments
        # Update check_configs if adjustments contain them
        if "check_configs" in request.adjustments:
            parse_result.check_configs = request.adjustments["check_configs"]
        if "thresholds" in request.adjustments and parse_result.check_configs:
            for cc in parse_result.check_configs:
                cc["thresholds"] = {**cc.get("thresholds", {}), **request.adjustments["thresholds"]}
        if "severity" in request.adjustments and parse_result.check_configs:
            for cc in parse_result.check_configs:
                cc["severity"] = request.adjustments["severity"]
        if "dataset_id" in request.adjustments and parse_result.check_configs:
            for cc in parse_result.check_configs:
                cc["dataset_id"] = request.adjustments["dataset_id"]
                cc["dataset_name"] = request.adjustments.get("dataset_name", cc.get("dataset_name"))

    db.commit()

    check_configs = (
        [CheckConfigOutput(**cc) for cc in parse_result.check_configs]
        if parse_result.check_configs
        else []
    )

    # NOTE: We intentionally do NOT create a DQRule here. The canonical
    # governance flow is: NL Rule Builder → Submit as Proposal → Confirm in
    # Proposals tab (which creates the DQRule via ProposalEngine.confirm) →
    # Build Flow from one or more confirmed rules.
    return ValidateParseResponse(
        parse_result_id=str(parse_result.id),
        validated=parse_result.validated,
        validated_at=now.isoformat(),
        check_configs=check_configs,
        rule_id=None,
    )


# ── Create Flow from Validated Parse ──


@router.post(
    "/workspaces/{workspace_id}/rule-builder/parses/{parse_result_id}/create-flow",
    response_model=GenerateFlowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Transform a validated parse result into a DQ flow",
    description="Takes a validated parse result and automatically generates "
    "a DQ flow with source and check nodes from its check_configs.",
    tags=["rule-builder"],
)
def create_flow_from_parse(
    workspace_id: UUID,
    parse_result_id: str,
    flow_name: str | None = Query(None, max_length=255, description="Custom flow name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GenerateFlowResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    # Load parse result
    parse_result = (
        db.query(NLRuleParseResult)
        .filter(
            NLRuleParseResult.id == parse_result_id,
        )
        .first()
    )
    if not parse_result:
        raise HTTPException(status_code=404, detail="Parse result not found")

    # Verify workspace ownership
    nl_request = (
        db.query(NLRuleRequest)
        .filter(
            NLRuleRequest.id == parse_result.request_id,
            NLRuleRequest.workspace_id == workspace_id,
        )
        .first()
    )
    if not nl_request:
        raise HTTPException(status_code=404, detail="Parse result not found in this workspace")

    # Auto-validate on create-flow: clicking "Create Flow" in the UI is an
    # explicit user confirmation, so mark the parse validated if not already.
    if not parse_result.validated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Parse result must be validated before creating a flow. "
                "Call POST /rule-builder/parses/{id}/validate first."
            ),
        )

    # Spec §12 — defence-in-depth: re-run the proposal validator before flow
    # construction. Reject if the proposal is no longer convertible.
    validation, refinement, _ = _revalidate_parse_result(db, workspace_id, parse_result)
    if not validation.dq_flow_convertible:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "rule_proposal_invalid",
                "message": (
                    refinement.message
                    if refinement is not None
                    else "Rule proposal is not convertible to a valid DQ flow."
                ),
                "validation": validation.model_dump(),
                "refinement": refinement.model_dump() if refinement else None,
            },
        )

    # Must have check_configs
    if not parse_result.check_configs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parse result has no check configurations",
        )

    # Locate the DQRule that was created by /validate (linked via parse_result_id
    # in meta_data). Surfacing rule_id into each check node config allows the
    # issue creation hook to look up canonical severity from DQRule.canonical_rule.
    linked_rule = (
        db.query(DQRule)
        .filter(
            DQRule.workspace_id == workspace_id,
            DQRule.meta_data.op("->>")("parse_result_id") == str(parse_result.id),
        )
        .order_by(DQRule.created_at.desc())
        .first()
    )
    linked_rule_id = str(linked_rule.id) if linked_rule else None

    # Convert check_configs dicts → CompiledCheckConfig objects
    compiled_configs = []
    for cc in parse_result.check_configs:
        config_payload = {
            **cc.get("config", {}),
            "dataset_name": cc.get("dataset_name"),
            "columns": cc.get("columns", []),
            "thresholds": cc.get("thresholds", {}),
        }
        if linked_rule_id:
            config_payload["rule_id"] = linked_rule_id
        compiled_configs.append(
            CompiledCheckConfig(
                check_type=cc["check_dimension"],
                subtype=cc["check_subtype"],
                dataset_id=cc.get("dataset_id"),
                rule_name=cc.get("rule_name", "NL Rule Check"),
                severity=cc.get("severity", "medium"),
                description=cc.get("description"),
                config=config_payload,
            )
        )

    # Build the generate-flow request
    gen_request = GenerateFlowRequest(
        compiled_configs=compiled_configs,
        flow_name=flow_name or f"NL: {nl_request.rule_text[:80]}",
        flow_description=f"Auto-generated from NL rule: {nl_request.rule_text}",
        nl_rule_text=nl_request.rule_text,
        parse_request_id=str(nl_request.id),
    )

    return _flow_generator.generate(db, workspace_id, current_user.id, gen_request)


# ── E3: Test-on-sample from a saved parse result ──


@router.post(
    "/workspaces/{workspace_id}/rule-builder/parses/{parse_result_id}/test",
    response_model=TestPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Test-preview a parsed rule against actual sample data",
    description=(
        "Reads a saved parse result, picks the requested check_index "
        "(default 0), reconstructs a CompiledCheckConfig, and runs the "
        "F107 test-preview engine against the actual dataset rows."
    ),
    tags=["rule-builder"],
)
def test_preview_from_parse(
    workspace_id: UUID,
    parse_result_id: str,
    check_index: int = Query(0, ge=0, description="Which check_config to test"),
    sample_size: int = Query(50, ge=1, le=1000),
    violation_limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TestPreviewResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    parse_result = (
        db.query(NLRuleParseResult)
        .filter(
            NLRuleParseResult.id == parse_result_id,
        )
        .first()
    )
    if not parse_result:
        raise HTTPException(status_code=404, detail="Parse result not found")

    nl_request = (
        db.query(NLRuleRequest)
        .filter(
            NLRuleRequest.id == parse_result.request_id,
            NLRuleRequest.workspace_id == workspace_id,
        )
        .first()
    )
    if not nl_request:
        raise HTTPException(status_code=404, detail="Parse result not found in this workspace")

    if not parse_result.check_configs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parse result has no check configurations to test",
        )

    if check_index >= len(parse_result.check_configs):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"check_index {check_index} out of range; "
                f"parse has {len(parse_result.check_configs)} check configs"
            ),
        )

    cc = parse_result.check_configs[check_index]
    config_payload = {
        **(cc.get("config") or {}),
        "dataset_name": cc.get("dataset_name"),
        "columns": cc.get("columns", []),
        "thresholds": cc.get("thresholds", {}),
    }
    compiled = CompiledCheckConfig(
        check_type=cc["check_dimension"],
        subtype=cc["check_subtype"],
        dataset_id=cc.get("dataset_id"),
        rule_name=cc.get("rule_name", "NL Rule Check"),
        severity=cc.get("severity", "medium"),
        description=cc.get("description"),
        config=config_payload,
    )

    request = TestPreviewRequest(
        compiled_config=compiled,
        sample_size=sample_size,
        violation_limit=violation_limit,
    )
    return _test_preview.preview(db, workspace_id, request)


@router.post(
    "/workspaces/{workspace_id}/rule-builder/resolve",
    response_model=ResolveResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve SIR entity references to physical metadata",
    description="Takes an unresolved SIR and resolves raw_text entity references to physical columns "
    "using a 12-signal weighted scoring model.",
    tags=["rule-builder"],
)
def resolve_rule(
    workspace_id: UUID,
    request: ResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResolveResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return _resolution_engine.resolve(db, workspace_id, request)


@router.post(
    "/workspaces/{workspace_id}/rule-builder/compile",
    response_model=CompileResponse,
    status_code=status.HTTP_200_OK,
    summary="Compile a resolved SIR into check node configuration",
    description="Transforms a validated SIR with resolved metadata into an executable "
    "data quality check configuration compatible with the flow builder.",
    tags=["rule-builder"],
)
def compile_rule(
    workspace_id: UUID,
    request: CompileRequest,
    current_user: User = Depends(get_current_user),
) -> CompileResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return _compiler.compile(request)


@router.post(
    "/workspaces/{workspace_id}/rule-builder/generate-flow",
    response_model=GenerateFlowResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a flow from compiled check configs",
    description="Creates a new flow or adds nodes to an existing flow "
    "from one or more compiled check configurations.",
    tags=["rule-builder"],
)
def generate_flow(
    workspace_id: UUID,
    request: GenerateFlowRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GenerateFlowResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return _flow_generator.generate(db, workspace_id, current_user.id, request)


# ── F124: Multi-Stage Disambiguation Endpoints ──


@router.post(
    "/workspaces/{workspace_id}/rule-builder/disambiguate/start",
    response_model=DisambiguationStartResponse,
    status_code=status.HTTP_200_OK,
    summary="Start a disambiguation session",
    tags=["rule-builder"],
)
def start_disambiguation(
    workspace_id: UUID,
    request: DisambiguationStartRequest,
    current_user: User = Depends(get_current_user),
) -> DisambiguationStartResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    ambiguities = _disambiguation_detector.detect(
        sir=request.parsed_rule,
        subject_resolution=request.subject_resolution,
        object_resolution=request.object_resolution,
    )
    questions = _question_planner.plan_questions(ambiguities)

    from app.schemas.disambiguation import DisambiguationSession

    session = DisambiguationSession(
        workspace_id=workspace_id,
        user_id=current_user.id,
        request_text=request.request_text,
        parsed_rule_snapshot=request.parsed_rule.model_dump(mode="json"),
        ambiguities=ambiguities,
        questions=questions,
    )
    _disambiguation_session_service.save_session(session)

    return DisambiguationStartResponse(session=session, next_questions=questions)


@router.post(
    "/workspaces/{workspace_id}/rule-builder/disambiguate/{session_id}/answer",
    response_model=DisambiguationAnswerResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit disambiguation answers",
    tags=["rule-builder"],
)
def answer_disambiguation(
    workspace_id: UUID,
    session_id: UUID,
    request: DisambiguationAnswerRequest,
    current_user: User = Depends(get_current_user),
) -> DisambiguationAnswerResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    session = _disambiguation_session_service.get_session(session_id)
    if not session or session.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Disambiguation session not found"
        )

    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Session belongs to another user"
        )

    try:
        result = _disambiguation_session_service.apply_answers(
            session_id=session_id, answers=request.answers
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    refreshed = _disambiguation_session_service.get_session(session_id)
    return DisambiguationAnswerResponse(
        session_id=result.session_id,
        session_status=refreshed.status,
        can_resume_pipeline=result.can_resume_pipeline,
        pending_required_question_ids=result.pending_required_question_ids,
        answered_question_ids=result.answered_question_ids,
    )


@router.get(
    "/workspaces/{workspace_id}/rule-builder/disambiguate/{session_id}",
    response_model=DisambiguationSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get disambiguation session",
    tags=["rule-builder"],
)
def get_disambiguation_session(
    workspace_id: UUID,
    session_id: UUID,
    current_user: User = Depends(get_current_user),
) -> DisambiguationSessionResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    session = _disambiguation_session_service.get_session(session_id)
    if not session or session.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Disambiguation session not found"
        )
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Session belongs to another user"
        )

    return DisambiguationSessionResponse(session=session)


@router.post(
    "/workspaces/{workspace_id}/rule-builder/disambiguate/{session_id}/cancel",
    response_model=DisambiguationSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel disambiguation session",
    tags=["rule-builder"],
)
def cancel_disambiguation_session(
    workspace_id: UUID,
    session_id: UUID,
    current_user: User = Depends(get_current_user),
) -> DisambiguationSessionResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    session = _disambiguation_session_service.get_session(session_id)
    if not session or session.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Disambiguation session not found"
        )
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Session belongs to another user"
        )

    session.cancel()
    return DisambiguationSessionResponse(session=session)


# ── F107: Test Preview Endpoint ──


@router.post(
    "/workspaces/{workspace_id}/rule-builder/test",
    response_model=TestPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Test-preview a compiled rule against actual data",
    description="Runs a dry-run of a compiled check config: fetches sample rows, "
    "estimates pass/fail counts, returns violation examples, "
    "builds technical expression, and detects type/null warnings.",
    tags=["rule-builder"],
)
def test_preview(
    workspace_id: UUID,
    request: TestPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TestPreviewResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return _test_preview.preview(db, workspace_id, request)


# ── F106: Audit Trail Endpoints ──


@router.post(
    "/workspaces/{workspace_id}/rule-builder/audit",
    response_model=AuditRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an NL rule generation audit event",
    tags=["rule-builder"],
)
def create_audit_record(
    workspace_id: UUID,
    data: AuditRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AuditRecordResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return _audit_service.record_generation(db, workspace_id, current_user.id, data)


@router.post(
    "/workspaces/{workspace_id}/rule-builder/audit/{audit_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record user feedback on an NL rule generation",
    tags=["rule-builder"],
)
def create_feedback(
    workspace_id: UUID,
    audit_id: str,
    data: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FeedbackResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return _audit_service.record_feedback(db, audit_id, data)


@router.get(
    "/workspaces/{workspace_id}/rule-builder/audit",
    response_model=AuditListResponse,
    summary="List NL rule generation audit records",
    tags=["rule-builder"],
)
def list_audit_records(
    workspace_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AuditListResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return _audit_service.get_audit_trail(db, workspace_id, page, page_size, user_id)


@router.get(
    "/workspaces/{workspace_id}/rule-builder/audit/{audit_id}",
    response_model=ExplainabilityResponse,
    summary="Get audit record with explainability details",
    tags=["rule-builder"],
)
def get_audit_explainability(
    workspace_id: UUID,
    audit_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExplainabilityResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return _audit_service.get_explainability(db, audit_id)
