"""
RuleTemplateService — core service for template browsing, detail, and application.
"""

import copy
from typing import Any
from uuid import UUID

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.rule_template import RuleTemplate
from app.services.rule_templates.placeholders import (
    VALID_SEVERITIES,
    extract_placeholders,
    substitute_placeholders,
    validate_mapping_complete,
)


class RuleTemplateService:
    """Service for rule template operations."""

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_all_templates(
        self,
        db: Session,
        dimension: str | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> list[RuleTemplate]:
        """Return active templates, optionally filtered."""
        q = db.query(RuleTemplate).filter(RuleTemplate.is_active.is_(True))
        if dimension:
            q = q.filter(RuleTemplate.dimension == dimension.lower())
        if category:
            q = q.filter(RuleTemplate.category == category)
        if search:
            pattern = f"%{search.lower()}%"
            q = q.filter(
                (sa_func.lower(RuleTemplate.name).like(pattern))
                | (sa_func.lower(RuleTemplate.description).like(pattern))
                | (
                    RuleTemplate.tags.cast(
                        db.bind.dialect.name == "postgresql" and str or str
                    ).ilike(pattern)
                    if False
                    else sa_func.lower(
                        sa_func.cast(
                            RuleTemplate.tags,
                            db.bind.dialect.type_descriptor(RuleTemplate.tags.type)
                            if False
                            else RuleTemplate.tags.type,
                        )
                    ).like(pattern)
                )  # noqa — simplified below
            )
            # Simplified: search by name or description only (tags are JSONB)
            q = db.query(RuleTemplate).filter(
                RuleTemplate.is_active.is_(True),
                (sa_func.lower(RuleTemplate.name).like(pattern))
                | (sa_func.lower(RuleTemplate.description).like(pattern)),
            )
            if dimension:
                q = q.filter(RuleTemplate.dimension == dimension.lower())
            if category:
                q = q.filter(RuleTemplate.category == category)
        return q.order_by(RuleTemplate.dimension, RuleTemplate.name).all()

    def get_template_by_id(
        self,
        db: Session,
        template_id: UUID,
    ) -> RuleTemplate | None:
        """Return a single active template or None."""
        return (
            db.query(RuleTemplate)
            .filter(RuleTemplate.id == template_id, RuleTemplate.is_active.is_(True))
            .first()
        )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    def apply_template(
        self,
        db: Session,
        template_id: UUID,
        target_table: str,
        column_mapping: dict[str, str],
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Instantiate a canonical rule dict from a template.

        Returns dict with keys: canonical_rule, template_id, template_name.
        Raises ValueError on missing mappings, LookupError if template not found.
        """
        template = self.get_template_by_id(db, template_id)
        if template is None:
            raise LookupError(f"Template {template_id} not found")

        crt = copy.deepcopy(template.canonical_rule_template)

        # Determine required placeholders (excluding __TABLE__ which is auto-filled)
        all_placeholders = extract_placeholders(crt)
        auto_tokens = {"__TABLE__"}
        required = all_placeholders - auto_tokens

        # Validate mapping completeness
        missing = validate_mapping_complete(required, column_mapping)
        if missing:
            raise ValueError(f"Missing required column mappings: {', '.join(missing)}")

        # Build full substitution map (include __TABLE__)
        full_mapping = {**column_mapping, "__TABLE__": target_table}
        canonical_rule = substitute_placeholders(crt, full_mapping)

        # Apply overrides
        overrides = overrides or {}
        if "threshold_pass" in overrides and overrides["threshold_pass"] is not None:
            tp = float(overrides["threshold_pass"])
            if not (0 <= tp <= 100):
                raise ValueError("threshold_pass must be between 0 and 100")
            canonical_rule.setdefault("parameters", {})["threshold_pass"] = tp
            canonical_rule["expectation"] = f"{tp}%"
        if "threshold_warn" in overrides and overrides["threshold_warn"] is not None:
            tw = float(overrides["threshold_warn"])
            if not (0 <= tw <= 100):
                raise ValueError("threshold_warn must be between 0 and 100")
            canonical_rule.setdefault("parameters", {})["threshold_warn"] = tw
        if "severity" in overrides and overrides["severity"] is not None:
            sev = str(overrides["severity"]).lower()
            if sev not in VALID_SEVERITIES:
                raise ValueError(f"severity must be one of {VALID_SEVERITIES}")
            canonical_rule["severity"] = sev

        # Ensure target_table is set
        canonical_rule["target_table"] = target_table

        # Increment use_count atomically
        db.query(RuleTemplate).filter(RuleTemplate.id == template_id).update(
            {RuleTemplate.use_count: RuleTemplate.use_count + 1}
        )
        db.commit()

        return {
            "canonical_rule": canonical_rule,
            "template_id": str(template.id),
            "template_name": template.name,
        }
