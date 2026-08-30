"""
Rule Template API Endpoints — F093
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.schemas.rule_template import (
    ApplyTemplateRequest,
    ApplyTemplateResponse,
    RuleTemplateDetail,
    RuleTemplateListItem,
    RuleTemplateListResponse,
)
from app.services.rule_templates.service import RuleTemplateService

router = APIRouter(prefix="/rule-templates", tags=["rule-templates"])

_service = RuleTemplateService()


@router.get(
    "",
    response_model=RuleTemplateListResponse,
    summary="List rule templates",
    description="Returns all active rule templates, optionally filtered by dimension, category, or search query.",
)
def list_templates(
    dimension: str | None = Query(None, description="Filter by DQ dimension"),
    category: str | None = Query(None, description="Filter by category"),
    search: str | None = Query(None, description="Search name/description"),
    db: Session = Depends(get_db),
):
    templates = _service.get_all_templates(
        db, dimension=dimension, category=category, search=search
    )
    items = [RuleTemplateListItem.model_validate(t) for t in templates]
    return RuleTemplateListResponse(templates=items, total=len(items))


@router.get(
    "/{template_id}",
    response_model=RuleTemplateDetail,
    summary="Get rule template detail",
    description="Returns full template including canonical_rule_template JSONB.",
)
def get_template(
    template_id: UUID,
    db: Session = Depends(get_db),
):
    template = _service.get_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return RuleTemplateDetail.model_validate(template)


@router.post(
    "/{template_id}/apply",
    response_model=ApplyTemplateResponse,
    summary="Apply a rule template",
    description="Instantiates a canonical rule dict from a template with column mappings and optional overrides.",
)
def apply_template(
    template_id: UUID,
    request: ApplyTemplateRequest,
    db: Session = Depends(get_db),
):
    try:
        result = _service.apply_template(
            db=db,
            template_id=template_id,
            target_table=request.target_table,
            column_mapping=request.column_mapping,
            overrides=request.overrides,
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return ApplyTemplateResponse(**result)
