"""Proposal endpoints — propose, confirm, reject, list, get (F111)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.schemas.proposal import (
    ConfirmProposalRequest,
    ProposalListResponse,
    ProposalRequest,
    ProposalResponse,
    RejectProposalRequest,
)
from app.services.auth.jwt import get_current_user
from app.services.nl_compiler.compiler import NLRuleCompiler
from app.services.nl_rule_builder.parser import NLRuleParserService
from app.services.proposal import ProposalEngine
from app.services.resolution.engine import ResolutionEngine

router = APIRouter(prefix="/proposals", tags=["Proposals (F111)"])


def _get_engine() -> ProposalEngine:
    return ProposalEngine(
        parser=NLRuleParserService(),
        resolution_engine=ResolutionEngine(),
        compiler=NLRuleCompiler(),
    )


@router.post(
    "/workspaces/{workspace_id}/proposals",
    response_model=ProposalResponse,
    status_code=201,
)
async def create_proposal(
    workspace_id: UUID,
    request: ProposalRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Generate a rule proposal from natural language."""
    engine = _get_engine()
    user_id = (
        str(user.get("user_id", ""))
        if isinstance(user, dict)
        else str(getattr(user, "user_id", ""))
    )
    try:
        return await engine.propose(
            db,
            workspace_id,
            request.prompt,
            user_id=user_id,
            dataset_context=request.dataset_context,
            domain_context=request.domain_context,
        )
    except ValueError as exc:
        message = str(exc) or "Could not create proposal"
        if "LLM service unavailable" in message:
            raise HTTPException(status_code=503, detail=message)
        raise HTTPException(status_code=422, detail=message)


@router.get(
    "/workspaces/{workspace_id}/proposals",
    response_model=ProposalListResponse,
)
def list_proposals(
    workspace_id: UUID,
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """List proposals for a workspace."""
    engine = _get_engine()
    items, total = engine.list_proposals(
        db, workspace_id, status=status, limit=limit, offset=offset
    )
    return ProposalListResponse(items=items, total=total)


@router.get(
    "/workspaces/{workspace_id}/proposals/{proposal_id}",
    response_model=ProposalResponse,
)
def get_proposal(
    workspace_id: UUID,
    proposal_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Get a single proposal."""
    engine = _get_engine()
    proposal = engine.get(db, workspace_id, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


@router.post(
    "/workspaces/{workspace_id}/proposals/{proposal_id}/confirm",
    response_model=ProposalResponse,
)
def confirm_proposal(
    workspace_id: UUID,
    proposal_id: UUID,
    request: ConfirmProposalRequest,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Confirm (accept) a proposal, optionally with adjustments."""
    engine = _get_engine()
    result = engine.confirm(db, workspace_id, proposal_id, request)
    if not result:
        raise HTTPException(status_code=404, detail="Proposal not found or not in pending state")
    return result


@router.post(
    "/workspaces/{workspace_id}/proposals/{proposal_id}/reject",
    response_model=ProposalResponse,
)
def reject_proposal(
    workspace_id: UUID,
    proposal_id: UUID,
    request: RejectProposalRequest,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Reject a proposal."""
    engine = _get_engine()
    result = engine.reject(db, workspace_id, proposal_id, reason=request.reason)
    if not result:
        raise HTTPException(status_code=404, detail="Proposal not found or not in pending state")
    return result
