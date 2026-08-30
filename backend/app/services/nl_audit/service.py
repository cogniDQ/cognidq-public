"""
NL Rule Audit Service — record, query, and explain NL rule generation events.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.nl_audit import (
    AuditListResponse,
    AuditRecordCreate,
    AuditRecordResponse,
    ExplainabilityEntry,
    ExplainabilityResponse,
    FeedbackCreate,
    FeedbackResponse,
)


class NLAuditService:
    """Service for NL rule generation audit trail."""

    def record_generation(
        self,
        db: Session,
        workspace_id: UUID,
        user_id: UUID,
        data: AuditRecordCreate,
    ) -> AuditRecordResponse:
        """Insert a full audit record for an NL rule generation event."""
        import json

        parsed_sir_payload: dict[str, Any] | None = data.parsed_sir
        if data.parse_explainability is not None or data.parse_trust_summary is not None:
            parsed_sir_payload = {
                "sir": data.parsed_sir,
                "parse_explainability": data.parse_explainability or [],
                "parse_trust_summary": data.parse_trust_summary,
            }

        result = db.execute(
            text("""
                INSERT INTO control.rule_generation_audit
                    (workspace_id, user_id, rule_text, parse_request_id,
                     parsed_sir, resolution_candidates, selected_mappings,
                     user_overrides, compiled_config, flow_id,
                     compilation_status, model_version, metadata_snapshot_version)
                VALUES
                    (:ws, :uid, :rule_text, :parse_req,
                     :sir::jsonb, :candidates::jsonb, :mappings::jsonb,
                     :overrides::jsonb, :compiled::jsonb, :flow,
                     :status, :model, :snap)
                RETURNING id, workspace_id, user_id, rule_text, parse_request_id,
                          parsed_sir, resolution_candidates, selected_mappings,
                          user_overrides, compiled_config, flow_id,
                          compilation_status, model_version, metadata_snapshot_version,
                          created_at
            """),
            {
                "ws": str(workspace_id),
                "uid": str(user_id),
                "rule_text": data.rule_text,
                "parse_req": data.parse_request_id,
                "sir": json.dumps(parsed_sir_payload) if parsed_sir_payload else None,
                "candidates": json.dumps(data.resolution_candidates)
                if data.resolution_candidates
                else None,
                "mappings": json.dumps(data.selected_mappings) if data.selected_mappings else None,
                "overrides": json.dumps(data.user_overrides) if data.user_overrides else None,
                "compiled": json.dumps(data.compiled_config) if data.compiled_config else None,
                "flow": data.flow_id,
                "status": data.compilation_status,
                "model": data.model_version,
                "snap": data.metadata_snapshot_version,
            },
        )
        db.commit()
        row = result.fetchone()
        return self._row_to_response(row)

    def record_feedback(
        self,
        db: Session,
        audit_id: str,
        data: FeedbackCreate,
    ) -> FeedbackResponse:
        """Insert user feedback for an audit record."""
        import json

        result = db.execute(
            text("""
                INSERT INTO control.rule_user_feedback
                    (audit_id, feedback_type, entity_role,
                     original_candidate, selected_candidate,
                     confidence_at_decision, user_comment)
                VALUES
                    (:aid, :ftype, :role,
                     :orig::jsonb, :sel::jsonb,
                     :conf, :comment)
                RETURNING id, audit_id, feedback_type, entity_role,
                          original_candidate, selected_candidate,
                          confidence_at_decision, user_comment, created_at
            """),
            {
                "aid": audit_id,
                "ftype": data.feedback_type.value,
                "role": data.entity_role.value,
                "orig": json.dumps(data.original_candidate) if data.original_candidate else None,
                "sel": json.dumps(data.selected_candidate) if data.selected_candidate else None,
                "conf": data.confidence_at_decision,
                "comment": data.user_comment,
            },
        )
        db.commit()
        row = result.fetchone()
        return FeedbackResponse(
            id=str(row[0]),
            audit_id=str(row[1]),
            feedback_type=row[2],
            entity_role=row[3],
            original_candidate=row[4],
            selected_candidate=row[5],
            confidence_at_decision=row[6],
            user_comment=row[7],
            created_at=row[8],
        )

    def get_audit_trail(
        self,
        db: Session,
        workspace_id: UUID,
        page: int = 1,
        page_size: int = 20,
        user_id: str | None = None,
    ) -> AuditListResponse:
        """List audit records with pagination and filters."""
        offset = (page - 1) * page_size
        conditions = ["workspace_id = :ws"]
        params: dict[str, Any] = {"ws": str(workspace_id), "lim": page_size, "off": offset}

        if user_id:
            conditions.append("user_id = :uid")
            params["uid"] = user_id

        where = " AND ".join(conditions)

        count_row = db.execute(
            text(f"SELECT count(*) FROM control.rule_generation_audit WHERE {where}"),
            params,
        ).fetchone()
        total = count_row[0] if count_row else 0

        rows = db.execute(
            text(f"""
                SELECT id, workspace_id, user_id, rule_text, parse_request_id,
                       parsed_sir, resolution_candidates, selected_mappings,
                       user_overrides, compiled_config, flow_id,
                       compilation_status, model_version, metadata_snapshot_version,
                       created_at
                FROM control.rule_generation_audit
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :lim OFFSET :off
            """),
            params,
        ).fetchall()

        items = [self._row_to_response(r) for r in rows]
        return AuditListResponse(items=items, total=total, page=page, page_size=page_size)

    def get_explainability(
        self,
        db: Session,
        audit_id: str,
    ) -> ExplainabilityResponse:
        """Build explainability response for an audit record."""
        row = db.execute(
            text("""
                SELECT id, rule_text, parsed_sir, resolution_candidates,
                       selected_mappings, user_overrides
                FROM control.rule_generation_audit
                WHERE id = :aid
            """),
            {"aid": audit_id},
        ).fetchone()

        if not row:
            raise ValueError(f"Audit record {audit_id} not found")

        explanations = self._build_explanations(
            self._extract_parse_payload(row[2]).get("sir"),
            self._extract_resolution_payload(row[3]),
            row[4],  # selected_mappings
            row[5],  # user_overrides
        )

        parse_payload = self._extract_parse_payload(row[2])

        # Fetch feedbacks
        fb_rows = db.execute(
            text("""
                SELECT id, audit_id, feedback_type, entity_role,
                       original_candidate, selected_candidate,
                       confidence_at_decision, user_comment, created_at
                FROM control.rule_user_feedback
                WHERE audit_id = :aid
                ORDER BY created_at
            """),
            {"aid": audit_id},
        ).fetchall()

        feedbacks = [
            FeedbackResponse(
                id=str(r[0]),
                audit_id=str(r[1]),
                feedback_type=r[2],
                entity_role=r[3],
                original_candidate=r[4],
                selected_candidate=r[5],
                confidence_at_decision=r[6],
                user_comment=r[7],
                created_at=r[8],
            )
            for r in fb_rows
        ]

        return ExplainabilityResponse(
            audit_id=audit_id,
            rule_text=row[1],
            parse_explainability=parse_payload.get("parse_explainability", []),
            parse_trust_summary=parse_payload.get("parse_trust_summary"),
            explanations=explanations,
            feedbacks=feedbacks,
        )

    # ── internal ──

    def _build_explanations(
        self,
        parsed_sir: dict | None,
        resolution_candidates: dict | None,
        selected_mappings: dict | None,
        user_overrides: dict | None,
    ) -> list[ExplainabilityEntry]:
        explanations: list[ExplainabilityEntry] = []
        if not resolution_candidates:
            return explanations

        for role in ("subject", "object"):
            entity_data = resolution_candidates.get(role)
            if not entity_data:
                continue

            best = entity_data.get("best_candidate", {})
            if not best:
                continue

            col_name = best.get("column_name", "unknown")
            ds_name = best.get("dataset_name")
            signals = best.get("signal_breakdown", [])
            best.get("evidence_summary", [])
            rationale = best.get("rationale", [])

            reason_parts = []
            for sig in signals:
                if sig.get("score", 0) > 0:
                    reason_parts.append(f"{sig['signal_name']} ({sig['score']:.2f})")

            reason = (
                f"Selected based on: {', '.join(reason_parts)}"
                if reason_parts
                else "Default selection"
            )

            was_overridden = False
            override_from = None
            override_to = None
            if user_overrides and role in user_overrides:
                override = user_overrides[role]
                was_overridden = True
                override_from = override.get("from")
                override_to = override.get("to")
                reason = f"User overrode from '{override_from}' to '{override_to}'"

            explanations.append(
                ExplainabilityEntry(
                    entity_role=role,
                    column_name=col_name,
                    dataset_name=ds_name,
                    reason=reason,
                    signal_scores=signals,
                    rationale=rationale,
                    was_overridden=was_overridden,
                    override_from=override_from,
                    override_to=override_to,
                )
            )

        return explanations

    @staticmethod
    def _extract_parse_payload(parsed_sir: dict[str, Any] | None) -> dict[str, Any]:
        if not parsed_sir:
            return {"sir": None, "parse_explainability": [], "parse_trust_summary": None}
        if isinstance(parsed_sir, dict) and "sir" in parsed_sir:
            return {
                "sir": parsed_sir.get("sir"),
                "parse_explainability": parsed_sir.get("parse_explainability", []),
                "parse_trust_summary": parsed_sir.get("parse_trust_summary"),
            }
        return {"sir": parsed_sir, "parse_explainability": [], "parse_trust_summary": None}

    @staticmethod
    def _extract_resolution_payload(
        resolution_candidates: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not resolution_candidates:
            return resolution_candidates
        if (
            isinstance(resolution_candidates, dict)
            and "subject_resolution" in resolution_candidates
        ):
            return {
                "subject": resolution_candidates.get("subject_resolution"),
                "object": resolution_candidates.get("object_resolution"),
            }
        return resolution_candidates

    def _row_to_response(self, row) -> AuditRecordResponse:
        return AuditRecordResponse(
            id=str(row[0]),
            workspace_id=str(row[1]),
            user_id=str(row[2]),
            rule_text=row[3],
            parse_request_id=str(row[4]) if row[4] else None,
            parsed_sir=row[5],
            resolution_candidates=row[6],
            selected_mappings=row[7],
            user_overrides=row[8],
            compiled_config=row[9],
            flow_id=str(row[10]) if row[10] else None,
            compilation_status=row[11],
            model_version=row[12],
            metadata_snapshot_version=row[13] or 1,
            created_at=row[14],
        )
