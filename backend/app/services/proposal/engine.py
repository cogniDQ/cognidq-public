"""ProposalEngine — orchestrates parse → resolve → compile into a reviewable proposal (F111)."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.proposal import (
    ConfirmProposalRequest,
    ProposalAdjustment,
    ProposalPayload,
    ProposalResponse,
    ProposalStatus,
)


def _translate_sql_to_postgres(expr: str) -> str:
    """Best-effort translation of common cross-dialect SQL functions to Postgres.

    The LLM frequently emits MySQL / Snowflake syntax inside free-form
    ``business_rule_expression`` strings (e.g. ``DATEDIFF(CURRENT_DATE, dob)``,
    ``IFNULL(x, 0)``). These crash on Postgres execution. We rewrite the most
    common offenders here. The translation is conservative — anything we don't
    recognise is left untouched.
    """
    if not expr or not isinstance(expr, str):
        return expr
    out = expr
    # IFNULL(a, b) -> COALESCE(a, b)
    out = re.sub(r"\bIFNULL\s*\(", "COALESCE(", out, flags=re.IGNORECASE)
    # NVL(a, b)    -> COALESCE(a, b)
    out = re.sub(r"\bNVL\s*\(", "COALESCE(", out, flags=re.IGNORECASE)
    # GETDATE() / SYSDATE / NOW() -> CURRENT_TIMESTAMP (NOW() is valid PG too)
    out = re.sub(r"\bGETDATE\s*\(\s*\)", "CURRENT_TIMESTAMP", out, flags=re.IGNORECASE)
    out = re.sub(r"\bSYSDATE\b", "CURRENT_TIMESTAMP", out, flags=re.IGNORECASE)

    # DATEDIFF(a, b) -> (a - b)  — Postgres returns integer days for date subtraction.
    # Use a non-greedy two-arg matcher that respects nested parens at depth 0.
    def _datediff_two_arg(match: re.Match) -> str:
        inner = match.group(1)
        # Split on the top-level comma.
        depth = 0
        for i, ch in enumerate(inner):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                a = inner[:i].strip()
                b = inner[i + 1 :].strip()
                return f"({a} - {b})"
        return match.group(0)

    out = re.sub(
        r"\bDATEDIFF\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)",
        _datediff_two_arg,
        out,
        flags=re.IGNORECASE,
    )
    # DATE_ADD(d, INTERVAL n unit) -> (d + INTERVAL 'n unit')
    out = re.sub(
        r"\bDATE_ADD\s*\(\s*([^,]+?)\s*,\s*INTERVAL\s+(\d+)\s+(\w+)\s*\)",
        lambda m: f"({m.group(1)} + INTERVAL '{m.group(2)} {m.group(3)}')",
        out,
        flags=re.IGNORECASE,
    )
    return out


class ProposalEngine:
    """Creates, persists, and manages rule proposals."""

    def __init__(
        self,
        parser=None,
        resolution_engine=None,
        compiler=None,
    ):
        self._parser = parser
        self._resolution = resolution_engine
        self._compiler = compiler

    # ── Create proposal ───────────────────────────────────────────────

    async def propose(
        self,
        db: Session,
        workspace_id: UUID,
        prompt: str,
        user_id: str | None = None,
        dataset_context: str | None = None,
        domain_context: str | None = None,
    ) -> ProposalResponse:
        """Run full pipeline and persist as a pending proposal."""
        from app.schemas.nl_rule_builder import ParseRuleRequest
        from app.schemas.resolution import ResolveRequest

        # Normalise user_id: empty string → None
        if not user_id:
            user_id = None

        # Stage 1: Parse
        parse_req = ParseRuleRequest(
            rule_text=prompt,
            dataset_id=dataset_context,
            domain=domain_context,
        )
        user_uuid = uuid.UUID(user_id) if user_id else uuid.UUID(int=0)
        parse_resp = await self._parser.parse_rule(db, workspace_id, parse_req, user_uuid)
        sir = parse_resp.parsed_rule
        if sir is None:
            raise ValueError(parse_resp.reason or "Could not interpret the rule")
        parse_confidence = sir.confidence

        # Stage 2: Resolve
        glossary_matches: list = []
        resolution_evidence: dict = {}
        resolution_confidence = 0.0
        resolved_sir = sir.model_dump()
        resolved_sir_obj = sir  # default for compilation if resolution skipped

        if self._resolution:
            resolve_req = ResolveRequest(
                parsed_rule=sir,
                dataset_context=dataset_context,
                domain_context=domain_context,
            )
            resolve_resp = self._resolution.resolve(db, workspace_id, resolve_req)
            resolved_sir_obj = resolve_resp.resolved_rule
            resolution_confidence = resolve_resp.overall_confidence
            resolution_evidence = (
                resolve_resp.resolution_evidence.model_dump()
                if hasattr(resolve_resp.resolution_evidence, "model_dump")
                else dict(resolve_resp.resolution_evidence)
            )
            glossary_matches = [m.model_dump() for m in resolve_resp.glossary_matches]

            # ── User-confirmed dataset override ──
            # When the user explicitly selected a dataset in the wizard, that selection
            # is authoritative: pin the dataset onto the SIR's subject/object entities and
            # verify columns against control.dataset_fields. This makes the proposal show
            # the correct dataset_name + column FQN even when the metadata search service
            # did not return candidates for the column raw_text.
            ds_uuid = self._coerce_uuid(dataset_context)
            if ds_uuid is not None:
                ds_name, field_names = self._lookup_dataset_and_fields(db, workspace_id, ds_uuid)
                if ds_name:
                    matched_any = False
                    for entity in (resolved_sir_obj.subject, resolved_sir_obj.object):
                        if entity is None:
                            continue
                        # Always pin user's dataset choice
                        entity.dataset_id = str(ds_uuid)
                        entity.resolved_dataset = ds_name
                        # Verify column existence (case-insensitive) and pin canonical name
                        raw = (entity.raw_text or "").strip()
                        if raw:
                            match = next((f for f in field_names if f.lower() == raw.lower()), None)
                            if match:
                                entity.resolved_column = match
                                matched_any = True
                    if matched_any:
                        # User's explicit dataset + verified column → high confidence
                        resolution_confidence = max(resolution_confidence, 0.95)

            resolved_sir = resolved_sir_obj.model_dump()

        # Stage 3: Compile
        compiled_checks: list = []
        if self._compiler and resolution_confidence >= 0.7:
            try:
                from app.schemas.nl_compiler import CompilationOptions, CompileRequest

                compile_req = CompileRequest(
                    resolved_rule=resolved_sir_obj,
                    compilation_options=CompilationOptions(),
                )
                compile_resp = self._compiler.compile(compile_req)
                if compile_resp and getattr(compile_resp, "compiled_configs", None):
                    compiled_checks = [c.model_dump() for c in compile_resp.compiled_configs]
            except Exception as exc:
                import logging

                logging.getLogger(__name__).warning(
                    "Proposal compilation failed: %s", exc, exc_info=True
                )

        # Compute overall confidence
        confidence = round(
            min(parse_confidence, resolution_confidence)
            if resolution_confidence > 0
            else parse_confidence,
            4,
        )

        # Spec §12 / AC8 — hard gate: a proposal cannot be persisted unless
        # the resolved/compiled rule is convertible into a valid DQ flow.
        try:
            from app.schemas.nl_rule_builder import CheckConfigOutput as _CC
            from app.services.nl_rule_builder.dataset_metadata import load_dataset_meta
            from app.services.nl_rule_builder.rule_proposal_validation import (
                RuleProposalValidationService,
            )

            ds_uuid_for_gate = self._coerce_uuid(dataset_context)
            dataset_meta_for_gate = None
            if ds_uuid_for_gate is not None:
                try:
                    dataset_meta_for_gate = load_dataset_meta(db, workspace_id, ds_uuid_for_gate)
                except Exception:
                    dataset_meta_for_gate = None
            ccos = []
            for cc in compiled_checks:
                try:
                    ccos.append(_CC(**cc))
                except Exception:
                    pass
            validation, refinement, _proposal = RuleProposalValidationService().validate(
                sir=resolved_sir_obj,
                dataset_meta=dataset_meta_for_gate,
                check_configs=ccos or None,
            )
            if not validation.dq_flow_convertible:
                msg = (
                    refinement.message
                    if refinement is not None
                    else "Rule proposal is not convertible to a valid DQ flow."
                )
                raise ValueError(msg)
        except ValueError:
            raise
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "Proposal validation gate skipped due to internal error: %s", exc
            )

        payload = ProposalPayload(
            parsed_rule=sir.model_dump(),
            resolved_rule=resolved_sir,
            compiled_checks=compiled_checks,
            glossary_matches=glossary_matches,
            resolution_evidence=resolution_evidence,
            parse_confidence=parse_confidence,
            resolution_confidence=resolution_confidence,
        )

        # Persist
        proposal_id = uuid.uuid4()
        now = datetime.now(UTC)
        db.execute(
            text("""
                INSERT INTO control.nl_rule_proposals
                    (id, workspace_id, created_by, status, original_prompt,
                     proposal_payload, adjustments, confidence, created_at, updated_at)
                VALUES (:id, :ws, :user, :status, :prompt, :payload, :adj, :conf, :now, :now)
            """),
            {
                "id": str(proposal_id),
                "ws": str(workspace_id),
                "user": user_id,
                "status": ProposalStatus.pending.value,
                "prompt": prompt,
                "payload": json.dumps(payload.model_dump(), default=str),
                "adj": json.dumps([]),
                "conf": confidence,
                "now": now,
            },
        )
        db.commit()

        return ProposalResponse(
            proposal_id=proposal_id,
            workspace_id=workspace_id,
            created_by=user_id,
            status=ProposalStatus.pending,
            original_prompt=prompt,
            proposal_payload=payload,
            adjustments=[],
            confidence=confidence,
            created_at=now,
            updated_at=now,
        )

    # ── Get / List ────────────────────────────────────────────────────

    def get(self, db: Session, workspace_id: UUID, proposal_id: UUID) -> ProposalResponse | None:
        row = (
            db.execute(
                text(
                    "SELECT * FROM control.nl_rule_proposals WHERE id = :id AND workspace_id = :ws"
                ),
                {"id": str(proposal_id), "ws": str(workspace_id)},
            )
            .mappings()
            .first()
        )
        return self._row_to_response(row) if row else None

    def list_proposals(
        self,
        db: Session,
        workspace_id: UUID,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ProposalResponse], int]:
        where = "WHERE workspace_id = :ws"
        params: dict = {"ws": str(workspace_id), "lim": limit, "off": offset}
        if status:
            where += " AND status = :status"
            params["status"] = status

        total = (
            db.execute(
                text(f"SELECT count(*) FROM control.nl_rule_proposals {where}"),
                params,
            ).scalar()
            or 0
        )

        rows = (
            db.execute(
                text(
                    f"SELECT * FROM control.nl_rule_proposals {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"
                ),
                params,
            )
            .mappings()
            .all()
        )

        return [self._row_to_response(r) for r in rows], total

    # ── Confirm / Reject ──────────────────────────────────────────────

    def confirm(
        self,
        db: Session,
        workspace_id: UUID,
        proposal_id: UUID,
        request: ConfirmProposalRequest,
    ) -> ProposalResponse | None:
        proposal = self.get(db, workspace_id, proposal_id)
        if not proposal or proposal.status != ProposalStatus.pending:
            return None

        new_status = ProposalStatus.adjusted if request.adjustments else ProposalStatus.confirmed
        adjustments = [a.model_dump() for a in request.adjustments]
        now = datetime.now(UTC)

        # Apply user adjustments to a mutable copy of the proposal before rule creation
        adj_map = {a.field: a.new_value for a in request.adjustments}
        proposal_for_rule = proposal
        if adj_map:
            payload_dict = proposal.proposal_payload.model_dump()
            checks = payload_dict.get("compiled_checks") or []
            # Apply field overrides
            if "dataset_id" in adj_map and checks:
                for cc in checks:
                    cc["dataset_id"] = adj_map["dataset_id"]
                    # Lookup dataset name will be best-effort; store id as name too if unknown
                    cc["dataset_name"] = adj_map.get("dataset_name", adj_map["dataset_id"])
            if "severity" in adj_map and checks:
                for cc in checks:
                    cc["severity"] = adj_map["severity"]
            if "threshold_pass" in adj_map and checks:
                for cc in checks:
                    cc.setdefault("thresholds", {})["threshold_pass"] = adj_map["threshold_pass"]
            if "threshold_warn" in adj_map and checks:
                for cc in checks:
                    cc.setdefault("thresholds", {})["threshold_warn"] = adj_map["threshold_warn"]
            resolved = dict(
                payload_dict.get("resolved_rule") or payload_dict.get("parsed_rule") or {}
            )
            if "subject_column" in adj_map:
                resolved.setdefault("subject", {})["resolved_column"] = adj_map["subject_column"]
            if "object_column" in adj_map:
                resolved.setdefault("object", {})["resolved_column"] = adj_map["object_column"]
            # Any other adjustment field is treated as a clarification answer
            # — merged into ``parsed_rule.clarification_answers`` so the
            # downstream `_create_rule_from_proposal` picks it up alongside
            # LLM-emitted answers.
            _STRUCT_FIELDS = {
                "dataset_id",
                "dataset_name",
                "severity",
                "threshold_pass",
                "threshold_warn",
                "subject_column",
                "object_column",
                "rule_name",
            }
            parsed = dict(payload_dict.get("parsed_rule") or {})
            existing_answers = dict(parsed.get("clarification_answers") or {})
            for fld, val in adj_map.items():
                if fld in _STRUCT_FIELDS:
                    continue
                existing_answers[fld] = val
            if existing_answers:
                parsed["clarification_answers"] = existing_answers
                payload_dict["parsed_rule"] = parsed
            payload_dict["compiled_checks"] = checks
            payload_dict["resolved_rule"] = resolved
            # Rebuild a temporary proposal object with the adjusted payload
            from app.schemas.proposal import ProposalPayload as PP

            adjusted_payload = PP(**payload_dict)
            # Use rule_name override if provided
            prompt_for_rule = str(adj_map.get("rule_name", proposal.original_prompt))
            proposal_for_rule = proposal.model_copy(
                update={
                    "proposal_payload": adjusted_payload,
                    "original_prompt": prompt_for_rule,
                }
            )

        # Create a confirmed rule in dq_rules
        self._create_rule_from_proposal(db, workspace_id, proposal_for_rule)

        db.execute(
            text("""
                UPDATE control.nl_rule_proposals
                SET status = :status, adjustments = :adj, updated_at = :now
                WHERE id = :id AND workspace_id = :ws
            """),
            {
                "status": new_status.value,
                "adj": json.dumps(adjustments, default=str),
                "now": now,
                "id": str(proposal_id),
                "ws": str(workspace_id),
            },
        )
        db.commit()

        proposal.status = new_status
        proposal.adjustments = [ProposalAdjustment(**a) for a in adjustments]
        proposal.updated_at = now
        return proposal

    def reject(
        self,
        db: Session,
        workspace_id: UUID,
        proposal_id: UUID,
        reason: str | None = None,
    ) -> ProposalResponse | None:
        proposal = self.get(db, workspace_id, proposal_id)
        if not proposal or proposal.status != ProposalStatus.pending:
            return None

        now = datetime.now(UTC)
        adj = [{"field": "_rejection", "new_value": reason or "Rejected by user"}]

        db.execute(
            text("""
                UPDATE control.nl_rule_proposals
                SET status = :status, adjustments = :adj, updated_at = :now
                WHERE id = :id AND workspace_id = :ws
            """),
            {
                "status": ProposalStatus.rejected.value,
                "adj": json.dumps(adj, default=str),
                "now": now,
                "id": str(proposal_id),
                "ws": str(workspace_id),
            },
        )
        db.commit()

        proposal.status = ProposalStatus.rejected
        proposal.updated_at = now
        return proposal

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _coerce_uuid(value) -> UUID | None:
        """Return a UUID if value is a UUID-like string, else None."""
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value).strip())
        except (ValueError, AttributeError, TypeError):
            return None

    @staticmethod
    def _lookup_dataset_and_fields(
        db: Session,
        workspace_id: UUID,
        dataset_id: UUID,
    ) -> tuple[str | None, list[str]]:
        """Return (dataset_name, [field_names]) for a dataset in a workspace.

        Returns (None, []) if the dataset does not exist or belongs to a different workspace.
        """
        try:
            ds_row = db.execute(
                text(
                    "SELECT dataset_name FROM control.datasets "
                    "WHERE dataset_id = CAST(:id AS UUID) AND workspace_id = CAST(:ws AS UUID)"
                ),
                {"id": str(dataset_id), "ws": str(workspace_id)},
            ).first()
            if not ds_row:
                return None, []
            ds_name = ds_row[0]
            field_rows = db.execute(
                text(
                    "SELECT field_name FROM control.dataset_fields "
                    "WHERE dataset_id = CAST(:id AS UUID) ORDER BY ordinal_position"
                ),
                {"id": str(dataset_id)},
            ).all()
            return ds_name, [r[0] for r in field_rows]
        except Exception:
            return None, []

    # ── Rule creation from proposal ─────────────────────────────────

    # Map from parser/SIR rule_type to high-level dq dimension (legacy fallback).
    _DIMENSION_MAP_LEGACY = {
        "null_check": "completeness",
        "value_in_list": "validity",
        "range_check": "validity",
        "regex_check": "conformity",
        "uniqueness_check": "uniqueness",
        "cross_dataset": "consistency",
        "aggregate_check": "statistical",
        "date_check": "timeliness",
        "reconciliation": "reconciliation",
        "custom": "validity",
    }

    # Per-dimension parameter key under which the canonical_rule.parameters
    # carries the subtype name expected by the rule compiler dispatchers.
    _SUBTYPE_PARAM_BY_DIMENSION = {
        "validity": "validation_type",
        "conformity": "conformity_type",
        "completeness": "check_mode",
        "uniqueness": "uniqueness_type",
        "consistency": "consistency_type",
        "accuracy": "accuracy_type",
        "timeliness": "timeliness_type",
        "reconciliation": "reconciliation_type",
    }

    # Whitelist of valid subtype values per compiler dispatcher.
    _VALID_SUBTYPES_BY_DIMENSION = {
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
        "conformity": {
            "regex",
            "standard",
            "length",
            "charset",
            "case",
            "structural",
        },
        "completeness": {
            "null",
            "empty",
            "placeholder",
            "conditional",
            "multi_field",
            "population",
            "group",
        },
        "uniqueness": {
            "exact",
            "composite",
            "scoped",
            "cross_dataset",
            "fuzzy",
            "temporal",
        },
        "consistency": {
            "intra_record",
            "formula",
            "temporal",
            "inter_record",
            "cross_table",
            "aggregation",
        },
        "accuracy": {
            "reference_comparison",
            "trusted_source",
            "tolerated_deviation",
            "statistical",
            "derived_value",
        },
        "timeliness": {
            "freshness",
            "record_age",
            "latency",
            "processing_delay",
            "delivery_window",
            "heartbeat",
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

    # LLM-emitted aliases mapped to canonical compiler subtypes.
    _SUBTYPE_ALIASES = {
        "consistency": {
            "cross_field": "intra_record",
            "calculation": "formula",
            "date_logic": "temporal",
        },
        "validity": {
            "allowed": "allowed_values",
            "list": "allowed_values",
            "lookup": "reference_lookup",
        },
        "conformity": {
            "format": "standard",
        },
        "accuracy": {
            "numeric": "tolerated_deviation",
            "comparison": "reference_comparison",
        },
        "timeliness": {"age": "record_age"},
    }

    @staticmethod
    def _normalize_compiler_parameters(
        dimension: str | None,
        subtype: str | None,
        params: dict,
        entity_column: str | None,
    ) -> dict:
        """Bridge LLM subtype_config naming to RuleCompiler-expected keys."""
        p = dict(params or {})
        dim = (dimension or "").lower()
        sub = (subtype or "").lower()

        if dim == "conformity":
            if (
                p.get("standard_name")
                and not p.get("regex_pattern")
                and p.get("conformity_type") in (None, "regex")
            ):
                p["conformity_type"] = "standard"

        if dim == "uniqueness":
            valid_modes = {
                "exact",
                "composite",
                "scoped",
                "cross_dataset",
                "fuzzy",
                "temporal",
            }
            mode = p.get("uniqueness_mode")
            if mode not in valid_modes:
                cand = p.get("uniqueness_type") or sub
                p["uniqueness_mode"] = cand if cand in valid_modes else "exact"
            mode = p["uniqueness_mode"]
            if mode == "composite":
                cols = p.get("columns") or p.get("scope_columns") or []
                if cols:
                    p["columns"] = cols
                    p.pop("scope_columns", None)
            if mode == "scoped" and not p.get("columns") and entity_column:
                p["columns"] = [entity_column]
            if mode == "temporal" and not p.get("temporal_column"):
                # Look for *_ts / *_at column hint in entity or fall back
                # to a common timestamp column name.
                ec = entity_column or ""
                if ec.endswith("_ts") or ec.endswith("_at") or ec.endswith("_time"):
                    p["temporal_column"] = ec
                else:
                    p["temporal_column"] = "created_at"
            if mode == "temporal" and not p.get("temporal_window"):
                v = p.get("temporal_window_value")
                u = (p.get("temporal_window_unit") or "hours").lower()
                if v is not None:
                    letter = {
                        "day": "d",
                        "days": "d",
                        "hour": "h",
                        "hours": "h",
                        "minute": "m",
                        "minutes": "m",
                        "second": "s",
                        "seconds": "s",
                    }.get(u, "h")
                    try:
                        p["temporal_window"] = f"{int(v)}{letter}"
                    except Exception:
                        pass

        if dim == "timeliness":
            if not p.get("max_age") and p.get("max_age_value") is not None:
                unit = str(p.get("max_age_unit", "days")).lower()
                unit_letter = {
                    "day": "d",
                    "days": "d",
                    "hour": "h",
                    "hours": "h",
                    "minute": "m",
                    "minutes": "m",
                    "second": "s",
                    "seconds": "s",
                }.get(unit, "d")
                p["max_age"] = f"{int(p['max_age_value'])}{unit_letter}"

        if dim == "validity":
            for k_src, k_dst in (
                ("min", "min_value"),
                ("max", "max_value"),
                ("low", "min_value"),
                ("high", "max_value"),
            ):
                if k_src in p and k_dst not in p:
                    p[k_dst] = p[k_src]
            if "allowed_values" not in p:
                for k in ("values", "value_list", "list"):
                    if p.get(k):
                        p["allowed_values"] = p[k]
                        break
            if "regex_pattern" not in p and p.get("pattern"):
                p["regex_pattern"] = p["pattern"]
            # Translate common cross-dialect SQL functions inside
            # business_rule_expression / rule_expression so they execute
            # on Postgres. The LLM frequently emits MySQL/Snowflake
            # syntax (DATEDIFF, DATE_ADD, IFNULL, ...) which the compiler
            # passes through verbatim.
            for _expr_key in (
                "business_rule_expression",
                "rule_expression",
                "negative_expression",
                "filter_expression",
            ):
                _v = p.get(_expr_key)
                if isinstance(_v, str) and _v:
                    p[_expr_key] = _translate_sql_to_postgres(_v)

        if dim == "completeness":
            if not p.get("check_mode") and sub in ("null", "empty", "placeholder", "conditional"):
                p["check_mode"] = sub
            # Multi-field: parse comma/and-separated columns from entity
            if sub == "multi_field" and (not p.get("columns") or len(p.get("columns") or []) < 2):
                src = entity_column or ""
                # Split on commas, "and", semicolons
                tokens = re.split(r"[,;]|\band\b", src, flags=re.IGNORECASE)
                cols = [t.strip().strip("\"'") for t in tokens if t and t.strip()]
                cols = [c for c in cols if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", c)]
                if len(cols) >= 2:
                    p["columns"] = cols

        # Camel-case alias normalization for dataset references emitted by
        # the LLM (e.g. referenceDataset, sourceDataset, targetDataset).
        for camel, snake in (
            ("referenceDataset", "reference_dataset"),
            ("referenceColumn", "reference_column"),
            ("sourceDataset", "source_dataset"),
            ("targetDataset", "target_dataset"),
            ("sourceFilter", "source_filter"),
            ("targetFilter", "target_filter"),
            ("crossDatasetName", "cross_dataset_name"),
            ("joinKeys", "join_keys"),
        ):
            if camel in p and snake not in p:
                p[snake] = p[camel]

        # ── Conformity sub-type-specific key/value normalization ───────
        if dim == "conformity":
            # case rule
            if sub == "case" and not p.get("case_rule"):
                ec = p.get("expected_case") or p.get("case")
                if ec:
                    p["case_rule"] = ec
            # charset → allowed_characters
            if sub == "charset" and not p.get("allowed_characters"):
                cs = p.get("allowed_charset") or p.get("charset")
                if cs:
                    charset_map = {
                        "alpha": "a-zA-Z",
                        "alphanumeric": "a-zA-Z0-9",
                        "alnum": "a-zA-Z0-9",
                        "numeric": "0-9",
                        "digits": "0-9",
                        "ascii": "\\x20-\\x7E",
                    }
                    p["allowed_characters"] = charset_map.get(str(cs).lower(), str(cs))
            # structural_pattern → structural_format
            if sub == "structural" and not p.get("structural_format"):
                sp = p.get("structural_pattern") or p.get("pattern")
                if sp:
                    p["structural_format"] = sp
            # If structural_format is not json/xml, fall back to regex
            sf = p.get("structural_format")
            if sub == "structural" and sf and str(sf).lower() not in ("json", "xml"):
                # Translate template like "XX-9999" / "AA-99" to a regex
                tmpl = str(sf)
                regex_parts = []
                for ch in tmpl:
                    if ch.isalpha() and ch.isupper():
                        regex_parts.append("[A-Z]")
                    elif ch.isalpha() and ch.islower():
                        regex_parts.append("[a-z]")
                    elif ch.isdigit():
                        regex_parts.append("[0-9]")
                    elif ch in r"-_./ ":
                        regex_parts.append(re.escape(ch))
                    else:
                        regex_parts.append(re.escape(ch))
                regex_str = "^" + "".join(regex_parts) + "$"
                p["regex_pattern"] = regex_str
                p["pattern"] = regex_str
                p["conformity_type"] = "regex"
                p.pop("structural_format", None)

        # ── Accuracy/statistical key remap ─────────────────────────────
        if dim == "accuracy" and sub == "statistical":
            # Common LLM aliases: method ↔ statistical_method,
            # outlier_threshold ↔ statistical_threshold.
            if "statistical_method" not in p and p.get("method"):
                m = str(p["method"]).lower().replace("-", "_")
                # normalize "z-score" / "zscore" → "zscore"
                if m in ("zscore", "z_score", "z"):
                    p["statistical_method"] = "zscore"
                elif m in ("iqr", "interquartile", "interquartile_range"):
                    p["statistical_method"] = "iqr"
                else:
                    p["statistical_method"] = m
            if "statistical_threshold" not in p and p.get("outlier_threshold") is not None:
                p["statistical_threshold"] = p["outlier_threshold"]

        # ── Validity/negative key remap ────────────────────────────────
        if (
            dim == "validity"
            and sub == "negative"
            and not p.get("negative_expression")
            and entity_column
        ):
            np_pat = p.get("negative_pattern")
            mode = (p.get("negative_match_mode") or "regex").lower()
            if np_pat:
                # Build a SQL boolean expression that flags BAD rows so the
                # compiler's _validity_negative wraps it correctly.
                col = f'"{entity_column}"'
                if mode == "regex":
                    safe = str(np_pat).replace("'", "''")
                    p["negative_expression"] = f"{col} ~ '{safe}'"
                elif mode == "like":
                    safe = str(np_pat).replace("'", "''")
                    p["negative_expression"] = f"{col} LIKE '{safe}'"
                else:
                    safe = str(np_pat).replace("'", "''")
                    p["negative_expression"] = f"{col} = '{safe}'"

        # ── Consistency normalisations ─────────────────────────────────
        if dim == "consistency":
            if (
                sub in ("formula", "intra_record")
                and not p.get("expected_column")
                and entity_column
            ):
                p["expected_column"] = entity_column
            if sub == "aggregation" and not p.get("aggregation_function"):
                af = p.get("aggregate_function") or p.get("aggregationFunction")
                if af:
                    p["aggregation_function"] = af

        # ── Timeliness latency / processing_delay ──────────────────────
        if dim == "timeliness":

            def _to_duration(value, unit):
                if value is None:
                    return None
                u = str(unit or "hours").lower()
                letter = {
                    "day": "d",
                    "days": "d",
                    "hour": "h",
                    "hours": "h",
                    "minute": "m",
                    "minutes": "m",
                    "second": "s",
                    "seconds": "s",
                }.get(u, "h")
                try:
                    return f"{int(value)}{letter}"
                except Exception:
                    return None

            if sub == "latency":
                if not p.get("timestamp_column"):
                    p["timestamp_column"] = p.get("event_timestamp_column") or entity_column
                if not p.get("comparison_timestamp"):
                    p["comparison_timestamp"] = p.get("load_timestamp_column")
                if not p.get("max_age"):
                    p["max_age"] = _to_duration(
                        p.get("max_latency_value"),
                        p.get("max_latency_unit"),
                    )
            if sub == "processing_delay":
                if not p.get("timestamp_column"):
                    p["timestamp_column"] = p.get("start_timestamp_column") or entity_column
                if not p.get("comparison_timestamp"):
                    p["comparison_timestamp"] = p.get("end_timestamp_column")
                if not p.get("max_age"):
                    p["max_age"] = _to_duration(
                        p.get("max_delay_value"),
                        p.get("max_delay_unit"),
                    )
            if sub == "heartbeat":
                if not p.get("expected_frequency"):
                    p["expected_frequency"] = _to_duration(
                        p.get("expected_frequency_value"),
                        p.get("expected_frequency_unit"),
                    )
                if not p.get("timestamp_column"):
                    # fallback: use entity column even if it's not a real ts col
                    p["timestamp_column"] = entity_column

        # ── Accuracy reference checks: derive reference_column ─────────
        if dim == "accuracy" and sub in (
            "reference_comparison",
            "trusted_source",
            "tolerated_deviation",
        ):
            if not p.get("reference_column"):
                cc = p.get("compare_column") or ((p.get("compare_columns") or [None])[0])
                p["reference_column"] = cc or entity_column

        # ── Reconciliation: best-effort source_dataset = primary table ─
        # target_dataset still must come from clarification — but at least
        # avoid the "source_dataset is required" error if the primary
        # dataset is the source side.
        # (No-op here: caller substitutes resolved schema.table later.)

        return p

    def _resolve_column_name(
        self,
        db: Session,
        workspace_id: UUID,
        physical_identifier: str | None,
        column_hint: str | None,
    ) -> str | None:
        """Resolve a free-text column reference to a real column.

        The NL parser sometimes emits entity columns like ``"names"`` or
        ``"net amount"`` or ``"email signups"`` that don't exactly match
        the real dataset_fields. Look up the workspace dataset's columns
        and pick the closest match.
        """
        if not column_hint or not physical_identifier:
            return None
        try:
            rows = db.execute(
                text(
                    """
                    SELECT f.field_name
                    FROM control.dataset_fields f
                    JOIN control.datasets d ON d.dataset_id = f.dataset_id
                    WHERE d.workspace_id = CAST(:ws AS UUID)
                      AND d.physical_identifier = :p
                    """
                ),
                {"ws": str(workspace_id), "p": physical_identifier},
            ).fetchall()
        except Exception:
            return None
        cols = [r[0] for r in rows if r and r[0]]
        if not cols:
            return None
        hint = column_hint.strip()
        hint_lower = hint.lower()
        # 1. exact match
        for c in cols:
            if c.lower() == hint_lower:
                return c
        # 2. strip non-alnum
        norm = lambda s: re.sub(r"[^a-z0-9]+", "", s.lower())
        nh = norm(hint)
        for c in cols:
            if norm(c) == nh:
                return c
        # 3. drop trailing 's' or append '_id'/'_type'/'_name'
        for cand in (
            hint_lower.rstrip("s"),
            hint_lower + "_id",
            hint_lower + "_type",
            hint_lower + "_name",
        ):
            for c in cols:
                if c.lower() == cand:
                    return c
        # 4. tokenized: try each token of the hint
        tokens = [t for t in re.split(r"[^A-Za-z0-9]+", hint_lower) if t]
        for tok in tokens:
            for c in cols:
                cl = c.lower()
                if cl == tok or cl == tok + "_id" or cl == tok + "_type" or cl == tok + "_name":
                    return c
        # 5. partial: column starts with a long-enough token
        for tok in tokens:
            if len(tok) < 3:
                continue
            for c in cols:
                if c.lower().startswith(tok):
                    return c
        # 6. contains: any token appears anywhere in column name
        #    (e.g. hint "names" → token "name" → matches "full_name")
        for tok in tokens:
            if len(tok) < 3:
                continue
            tok_s = tok.rstrip("s")
            for c in cols:
                cl = c.lower()
                if tok in cl or (len(tok_s) >= 3 and tok_s in cl):
                    return c
        return None

    def _pick_timestamp_column(
        self,
        db: Session,
        workspace_id: UUID,
        physical_identifier: str | None,
    ) -> str | None:
        """Pick a sensible timestamp column from the dataset.

        Used when the LLM emits ``temporal_column="timestamp"`` or
        ``timestamp_column="updated_at"`` and the literal name doesn't
        exist in the table — we fall back to the first column whose name
        ends with ``_ts``/``_at``/``_time``/``_date``.
        """
        if not physical_identifier:
            return None
        try:
            rows = db.execute(
                text(
                    """
                    SELECT f.field_name
                    FROM control.dataset_fields f
                    JOIN control.datasets d ON d.dataset_id = f.dataset_id
                    WHERE d.workspace_id = CAST(:ws AS UUID)
                      AND d.physical_identifier = :p
                    ORDER BY f.field_name
                    """
                ),
                {"ws": str(workspace_id), "p": physical_identifier},
            ).fetchall()
        except Exception:
            return None
        cols = [r[0] for r in rows if r and r[0]]
        suffixes = ("_ts", "_at", "_time", "_date", "_timestamp")
        # Prefer event/created/load before generic
        priority_prefixes = ("event_", "created", "load_", "start_", "occurred_")
        priority_matches = [
            c
            for c in cols
            if any(c.lower().endswith(s) for s in suffixes)
            and any(c.lower().startswith(p) for p in priority_prefixes)
        ]
        if priority_matches:
            return priority_matches[0]
        for c in cols:
            if any(c.lower().endswith(s) for s in suffixes):
                return c
        return None

    def _resolve_secondary_dataset_name(
        self,
        db: Session,
        workspace_id: UUID,
        name_hint: str | None,
    ) -> str | None:
        """Resolve a free-text dataset reference to ``schema.physical_identifier``.

        Used for multi-dataset checks (reconciliation, accuracy/reference,
        validity/reference_lookup, consistency/cross_table, etc.) where the
        LLM produced a dataset name like ``"hr_system"`` or
        ``"customers_ref"``. Looks up control.datasets in the workspace by:
          1. exact dataset_name match (case-insensitive)
          2. exact physical_identifier match
          3. substring match
        Returns ``"schema.physical_identifier"`` (unquoted) suitable for
        passing to RuleCompiler dispatchers; or ``None`` if no match.
        """
        if not name_hint or not isinstance(name_hint, str):
            return None
        token = name_hint.strip().strip("\"'")
        if not token:
            return None
        # If already qualified schema.table, accept as-is (compiler handles it).
        if "." in token and " " not in token:
            return token
        try:
            row = db.execute(
                text(
                    """
                    SELECT schema_name, physical_identifier
                    FROM control.datasets
                    WHERE workspace_id = CAST(:ws AS UUID)
                      AND status = 'active'
                      AND (
                          lower(dataset_name) = lower(:t)
                          OR lower(physical_identifier) = lower(:t)
                      )
                    LIMIT 1
                    """
                ),
                {"ws": str(workspace_id), "t": token},
            ).fetchone()
            if not row:
                row = db.execute(
                    text(
                        """
                        SELECT schema_name, physical_identifier
                        FROM control.datasets
                        WHERE workspace_id = CAST(:ws AS UUID)
                          AND status = 'active'
                          AND (
                              lower(dataset_name) LIKE lower(:p)
                              OR lower(physical_identifier) LIKE lower(:p)
                          )
                        ORDER BY length(dataset_name) ASC
                        LIMIT 1
                        """
                    ),
                    {"ws": str(workspace_id), "p": f"%{token}%"},
                ).fetchone()
        except Exception:
            return None
        if not row:
            return None
        schema, ident = row[0], row[1]
        if schema:
            return f"{schema}.{ident}"
        return ident

    def _resolve_dataset_metadata(
        self, db: Session, workspace_id: UUID, dataset_id: str | None
    ) -> dict[str, str | None]:
        """Resolve schema/table/data_source for a dataset.

        Returns dict with keys schema_name, physical_identifier, dataset_name,
        public_data_source_id (the id matching public.data_sources, used by
        rule execution), control_data_source_id, source_name.
        """
        empty = {
            "schema_name": None,
            "physical_identifier": None,
            "dataset_name": None,
            "public_data_source_id": None,
            "control_data_source_id": None,
            "source_name": None,
        }
        if not dataset_id:
            return empty
        try:
            ds_uuid = self._coerce_uuid(dataset_id)
        except Exception:
            return empty
        try:
            row = db.execute(
                text(
                    """
                    SELECT d.dataset_name, d.schema_name, d.physical_identifier,
                           d.data_source_id AS control_ds_id, ds.source_name
                    FROM control.datasets d
                    LEFT JOIN control.data_sources ds
                      ON ds.data_source_id = d.data_source_id
                    WHERE d.dataset_id = CAST(:id AS UUID)
                      AND d.workspace_id = CAST(:ws AS UUID)
                    """
                ),
                {"id": str(ds_uuid), "ws": str(workspace_id)},
            ).fetchone()
        except Exception:
            return empty
        if not row:
            return empty
        # Resolve public.data_sources.id by source_name match.
        public_ds_id = None
        if row[4]:
            try:
                pub = db.execute(
                    text("SELECT id FROM public.data_sources WHERE name = :n LIMIT 1"),
                    {"n": row[4]},
                ).fetchone()
                if pub:
                    public_ds_id = str(pub[0])
            except Exception:
                public_ds_id = None
        return {
            "schema_name": row[1],
            "physical_identifier": row[2],
            "dataset_name": row[0],
            "control_data_source_id": str(row[3]) if row[3] else None,
            "public_data_source_id": public_ds_id,
            "source_name": row[4],
        }

    def _ensure_public_data_source_mirror(
        self,
        db: Session,
        control_ds_id: str | None,
        workspace_id: UUID,
    ) -> str | None:
        """Ensure a row in legacy ``public.data_sources`` mirrors the
        tenant-owned ``control.data_sources`` entry so that
        ``dq_rules.data_source_id`` (FK → public.data_sources.id) can be
        populated and the rule executor can decrypt credentials and connect.

        The mirror reuses the same UUID. Returns the public id (== control id)
        on success, ``None`` if the control row is missing/uncredentialed.
        """
        import logging

        logger = logging.getLogger(__name__)

        if not control_ds_id:
            return None
        try:
            row = db.execute(
                text(
                    """
                    SELECT ds.source_name, ds.source_type, ds.status,
                           ds.credential_reference, creds.encrypted_payload
                      FROM control.data_sources ds
                 LEFT JOIN control.data_source_credentials creds
                        ON creds.credential_id = ds.credential_reference
                     WHERE ds.data_source_id = CAST(:id AS UUID)
                    """
                ),
                {"id": str(control_ds_id)},
            ).fetchone()
        except Exception as exc:
            logger.warning("ensure_public_ds_mirror lookup failed: %s", exc)
            return None
        if not row:
            return None

        # Already mirrored?
        existing = db.execute(
            text("SELECT 1 FROM public.data_sources WHERE id = CAST(:id AS UUID)"),
            {"id": str(control_ds_id)},
        ).fetchone()
        if existing:
            return str(control_ds_id)

        source_name, source_type, status_val, _cred_ref, payload = row
        creds: dict = {}
        if payload is not None:
            try:
                from app.services.data_sources import credential_service as cred_svc

                creds = cred_svc.decrypt(bytes(payload))
            except Exception as exc:
                logger.warning(
                    "ensure_public_ds_mirror decrypt failed ds=%s err=%s",
                    control_ds_id,
                    exc,
                )
                return None

        try:
            db.execute(
                text(
                    """
                    INSERT INTO public.data_sources
                        (id, workspace_id, name, type, connection_config, status)
                    VALUES
                        (CAST(:id AS UUID), CAST(:ws AS UUID), :name, :type,
                         CAST(:cfg AS JSONB), :status)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "id": str(control_ds_id),
                    "ws": str(workspace_id),
                    "name": source_name,
                    "type": source_type,
                    "cfg": json.dumps(creds),
                    "status": (status_val or "active"),
                },
            )
            return str(control_ds_id)
        except Exception as exc:
            logger.warning(
                "ensure_public_ds_mirror insert failed ds=%s err=%s",
                control_ds_id,
                exc,
            )
            return None

    def _create_rule_from_proposal(
        self,
        db: Session,
        workspace_id: UUID,
        proposal: ProposalResponse,
    ) -> str | None:
        """Create a dq_rules record from a confirmed proposal.

        Carries check_dimension/check_subtype/subtype_config from the parsed
        SIR into canonical_rule, resolves dataset → data_source → schema/table,
        compiles SQL inline so the rule is executable immediately.
        """
        import logging

        logger = logging.getLogger(__name__)

        payload = proposal.proposal_payload
        parsed_raw = payload.parsed_rule or {}
        resolved_raw = payload.resolved_rule or parsed_raw
        checks_raw = payload.compiled_checks or []

        def _to_dict(v):
            if v is None:
                return {}
            if isinstance(v, dict):
                return v
            if hasattr(v, "model_dump"):
                return v.model_dump()
            return dict(v) if hasattr(v, "__iter__") else {}

        parsed = _to_dict(parsed_raw)
        resolved = _to_dict(resolved_raw)
        checks = [_to_dict(c) for c in checks_raw]
        check = checks[0] if checks else {}

        # ── Dimension / subtype resolution ──────────────────────────────
        rule_type_raw = parsed.get("rule_type", "custom")
        legacy_dimension = self._DIMENSION_MAP_LEGACY.get(rule_type_raw, "validity")

        # Prefer LLM-asserted check_dimension/check_subtype (carried on parsed
        # SIR or first compiled_check). Fall back to legacy mapping.
        check_dimension = (
            parsed.get("check_dimension")
            or resolved.get("check_dimension")
            or (check.get("check_dimension") if check else None)
            or legacy_dimension
        )
        check_subtype = (
            parsed.get("check_subtype")
            or resolved.get("check_subtype")
            or (check.get("check_subtype") if check else None)
        )
        subtype_config = (
            parsed.get("subtype_config")
            or resolved.get("subtype_config")
            or (check.get("subtype_config") if check else None)
            or {}
        )

        # ── Subject (table.column) ──────────────────────────────────────
        subject = resolved.get("subject", parsed.get("subject", {})) or {}
        operator = resolved.get("operator", parsed.get("operator", "")) or ""
        entity_col = subject.get("resolved_column") or subject.get("raw_text", "unknown")
        entity_table = subject.get("resolved_dataset") or ""
        if check.get("columns"):
            entity_col = check["columns"][0]
        entity = f"{entity_table}.{entity_col}" if entity_table else entity_col

        # ── Severity / threshold / parameters ───────────────────────────
        severity_raw = (check.get("severity") if check else None) or "medium"
        SEVERITY_MAP = {
            "critical": "critical",
            "high": "major",
            "medium": "minor",
            "low": "info",
            "info": "info",
            "blocker": "blocker",
            "major": "major",
            "minor": "minor",
        }
        severity = SEVERITY_MAP.get(severity_raw, "minor")

        thresholds = (check.get("thresholds") or {}) if check else {}
        expectation = f"{thresholds.get('threshold_pass', 100)}%"
        condition = operator or (check.get("config") or {}).get("condition", "custom")

        params: dict = {}
        if check.get("config"):
            params.update({k: v for k, v in check["config"].items() if k != "columns"})
        # Carry subtype_config (overrides nothing already set on config)
        for k, v in (subtype_config or {}).items():
            params.setdefault(k, v)
        # Tag canonical with dimension/subtype for downstream tooling.
        if check_subtype:
            params["check_subtype"] = check_subtype
            # Resolve subtype to a compiler-valid value: alias → whitelist.
            valid_set = self._VALID_SUBTYPES_BY_DIMENSION.get(check_dimension, set())
            alias_map = self._SUBTYPE_ALIASES.get(check_dimension, {})
            resolved_subtype = alias_map.get(check_subtype, check_subtype)
            dispatch_key = self._SUBTYPE_PARAM_BY_DIMENSION.get(check_dimension)
            if dispatch_key and resolved_subtype in valid_set:
                params[dispatch_key] = resolved_subtype
        if check_dimension:
            params["check_dimension"] = check_dimension

        # ── Dataset / data-source resolution ────────────────────────────
        dataset_id = (
            (check.get("dataset_id") if check else None)
            or resolved.get("dataset_id")
            or parsed.get("dataset_id")
            or subject.get("dataset_id")
        )
        meta = self._resolve_dataset_metadata(db, workspace_id, dataset_id)
        target_table = meta["physical_identifier"] or entity_table or None
        target_schema = meta["schema_name"]

        # ── Column-name fuzzy resolution against real schema ───────────
        # The NL parser sometimes emits broken column names like "names"
        # or "email signups". Match against control.dataset_fields and
        # replace entity_col with the canonical column name. Also fix the
        # entity string so the compiled SQL uses the real column.
        if entity_col and target_table:
            real_col = self._resolve_column_name(
                db,
                workspace_id,
                target_table,
                entity_col,
            )
            if real_col and real_col != entity_col:
                entity_col = real_col
                # Rebuild entity string to use the real column
                entity = f"{target_table}.{entity_col}"

        # Also resolve column references inside ``params`` so subtype-
        # specific columns (temporal_column, scope_columns, compare_column,
        # partition_columns, etc.) match the real schema. Without this,
        # uniqueness/scoped, uniqueness/temporal, uniqueness/fuzzy and
        # consistency/inter_record can compile but fail at runtime with
        # "column X does not exist".
        if target_table:
            _col_scalar_keys = (
                "temporal_column",
                "expected_column",
                "compare_column",
                "reference_column",
                "timestamp_column",
                "comparison_timestamp",
                "event_timestamp_column",
                "load_timestamp_column",
                "start_timestamp_column",
                "end_timestamp_column",
                "date_column",
                "partition_column",
                "scope_column",
                "group_by_column",
                "primary_key_column",
            )
            _col_list_keys = (
                "compare_columns",
                "scope_columns",
                "partition_columns",
                "primary_key_columns",
                "group_by_columns",
                "join_keys",
                "fuzzy_columns",
            )
            for k in _col_scalar_keys:
                v = params.get(k)
                if isinstance(v, str) and v:
                    fixed = self._resolve_column_name(db, workspace_id, target_table, v)
                    is_ts_key = k in {
                        "temporal_column",
                        "timestamp_column",
                        "comparison_timestamp",
                        "event_timestamp_column",
                        "load_timestamp_column",
                        "start_timestamp_column",
                        "end_timestamp_column",
                        "date_column",
                    }
                    if fixed:
                        # For timestamp keys, the resolved column must
                        # actually look like a timestamp; otherwise fall
                        # through to the timestamp picker.
                        if is_ts_key and not any(
                            fixed.lower().endswith(s)
                            for s in ("_ts", "_at", "_time", "_date", "_timestamp")
                        ):
                            ts_col = self._pick_timestamp_column(db, workspace_id, target_table)
                            params[k] = ts_col or fixed
                        else:
                            params[k] = fixed
                    elif is_ts_key:
                        ts_col = self._pick_timestamp_column(db, workspace_id, target_table)
                        if ts_col:
                            params[k] = ts_col
            for k in _col_list_keys:
                v = params.get(k)
                if isinstance(v, list):
                    new_list = []
                    for item in v:
                        if isinstance(item, str) and item:
                            fixed = self._resolve_column_name(db, workspace_id, target_table, item)
                            new_list.append(fixed or item)
                        else:
                            new_list.append(item)
                    params[k] = new_list
            # ``columns`` (used by completeness/multi_field & similar)
            cols_v = params.get("columns")
            if isinstance(cols_v, list):
                params["columns"] = [
                    (self._resolve_column_name(db, workspace_id, target_table, c) or c)
                    if isinstance(c, str) and c
                    else c
                    for c in cols_v
                ]

        # ── Secondary dataset resolution (multi-dataset checks) ────────
        # Reconciliation / accuracy / consistency / validity reference_lookup
        # and uniqueness/cross_dataset all reference one or more *other*
        # datasets by name. Resolve each free-text reference to the physical
        # ``schema.table`` identifier the compiler expects.
        # Also pull the clarification answers for these fields if the user
        # provided them via the clarifier (overrides the LLM's guess).
        clarif_answers = (
            (parsed.get("clarification_answers") or {})
            if isinstance(parsed.get("clarification_answers"), dict)
            else {}
        )
        # Merge clarification answers into ``params`` so subtype-specific
        # numeric/scalar values (min/max, lengths, tolerances, conditions)
        # collected via the clarifier reach the compiler. Only set keys
        # not already present so the LLM's value (if any) wins.
        _CLARIF_PARAM_KEYS = (
            "min_value",
            "max_value",
            "min_length",
            "max_length",
            "expected_value",
            "expected_length",
            "expected_pattern",
            "expected_format",
            "expected_case",
            "allowed_values",
            "disallowed_values",
            "regex_pattern",
            "structural_format",
            "structural_pattern",
            "tolerance_value",
            "tolerance_pct",
            "tolerated_deviation",
            "deviation_pct",
            "outlier_threshold",
            "z_score_threshold",
            "iqr_multiplier",
            "condition_value",
            "condition_operator",
            "condition_column",
            "condition_expression",
            "max_age_value",
            "max_age_unit",
            "max_latency_value",
            "max_latency_unit",
            "max_delay_value",
            "max_delay_unit",
            "expected_frequency_value",
            "expected_frequency_unit",
            "delivery_window_start",
            "delivery_window_end",
            "case_rule",
            "allowed_characters",
            "join_keys",
            "primary_key_columns",
            "group_by_columns",
            "scope_columns",
            "compare_column",
            "compare_columns",
            "reference_column",
            "expected_column",
            "temporal_column",
            "timestamp_column",
            "negative_pattern",
            "negative_expression",
            "negative_mode",
            "rule_expression",
            "aggregation_function",
            "fuzzy_threshold",
            "fuzzy_algorithm",
            "method",
            "statistical_method",
            "statistical_threshold",
            "formula",
            "expression",
        )

        def _coerce_clarif(val):
            # Strings like "5", "0.5", "0.5%" → numeric where possible.
            if not isinstance(val, str):
                return val
            s = val.strip()
            if not s:
                return val
            # strip trailing % (treat 0.5% → 0.5)
            stripped = s.rstrip("% ")
            try:
                if "." in stripped or "e" in stripped.lower():
                    return float(stripped)
                return int(stripped)
            except (ValueError, TypeError):
                return val

        for _k in _CLARIF_PARAM_KEYS:
            if _k in clarif_answers:
                # User-supplied clarification answers are an explicit
                # correction and must override whatever the LLM emitted.
                params[_k] = _coerce_clarif(clarif_answers[_k])
        # ``columns`` (e.g. completeness/multi_field) must be a list of real
        # column names. The clarifier may emit it as a list or comma string.
        if "columns" in clarif_answers and (
            not isinstance(params.get("columns"), list) or len(params.get("columns") or []) < 2
        ):
            cv = clarif_answers["columns"]
            if isinstance(cv, str):
                cv = [c.strip() for c in cv.split(",") if c.strip()]
            if isinstance(cv, list) and cv:
                resolved_cols = []
                for c in cv:
                    if isinstance(c, str) and target_table:
                        resolved_cols.append(
                            self._resolve_column_name(db, workspace_id, target_table, c) or c
                        )
                    else:
                        resolved_cols.append(c)
                params["columns"] = resolved_cols
        # Also accept an explicit ``check_subtype`` adjustment to override
        # the LLM-selected subtype.
        if "check_subtype" in clarif_answers:
            params["check_subtype"] = clarif_answers["check_subtype"]
        # ``length_range`` shorthand: "5-10" or "between 5 and 10".
        lr = clarif_answers.get("length_range") or params.get("length_range")
        if isinstance(lr, str) and (
            params.get("min_length") in (None, "", 0) or params.get("max_length") in (None, "", 0)
        ):
            import re as _re

            nums = _re.findall(r"\d+", lr)
            if len(nums) >= 2:
                params["min_length"] = int(nums[0])
                params["max_length"] = int(nums[1])
            elif len(nums) == 1:
                params["max_length"] = int(nums[0])
        for key in (
            "reference_dataset",
            "source_dataset",
            "target_dataset",
            "cross_dataset_name",
            "secondary_dataset",
        ):
            text_hint = clarif_answers.get(key) or params.get(key) or subtype_config.get(key)
            if not text_hint:
                continue
            resolved_qualified = self._resolve_secondary_dataset_name(
                db, workspace_id, str(text_hint)
            )
            if resolved_qualified:
                params[key] = resolved_qualified

        # Fallback: if a multi-dataset check still lacks its secondary
        # dataset reference, scan the original prompt text for any
        # workspace dataset name and auto-fill.
        _dim_lower = (check_dimension or "").lower()
        _sub_lower = (check_subtype or "").lower()
        _needs_secondary = (
            _dim_lower == "reconciliation"
            or (
                _dim_lower == "accuracy"
                and _sub_lower
                in (
                    "reference_comparison",
                    "trusted_source",
                    "tolerated_deviation",
                )
            )
            or (_dim_lower == "validity" and _sub_lower == "reference_lookup")
            or (
                _dim_lower == "consistency"
                and _sub_lower
                in (
                    "cross_table",
                    "reference_lookup",
                )
            )
            or (
                _dim_lower == "uniqueness"
                and _sub_lower
                in (
                    "cross_dataset",
                    "reference_lookup",
                )
            )
        )
        if _needs_secondary:
            try:
                ws_datasets = db.execute(
                    text(
                        """
                        SELECT dataset_name, schema_name, physical_identifier
                        FROM control.datasets
                        WHERE workspace_id = CAST(:ws AS UUID)
                          AND status = 'active'
                        """
                    ),
                    {"ws": str(workspace_id)},
                ).fetchall()
            except Exception:
                ws_datasets = []
            prompt_text = (proposal.original_prompt or "").lower()
            primary_ident = (meta.get("physical_identifier") or "").lower()
            mentioned: list[str] = []  # ordered by appearance, dedup'd
            for r in ws_datasets:
                ds_name = (r[0] or "").lower()
                ident = (r[2] or "").lower()
                schema = r[1]
                # match either the dataset_name token or physical_identifier
                hit_pos = -1
                for token in (ident, ds_name):
                    if token and token in prompt_text:
                        pos = prompt_text.find(token)
                        if pos >= 0 and (hit_pos == -1 or pos < hit_pos):
                            hit_pos = pos
                if hit_pos >= 0 and r[2]:
                    qualified = f"{schema}.{r[2]}" if schema else r[2]
                    mentioned.append((hit_pos, qualified, ident))
            mentioned.sort(key=lambda x: x[0])
            mentioned_quals = [q for _, q, _ in mentioned]
            mentioned_idents = [i for _, _, i in mentioned]
            # secondary candidates = mentioned, excluding the primary table
            secondary = [
                q for q, ident in zip(mentioned_quals, mentioned_idents) if ident != primary_ident
            ]

            if _dim_lower == "reconciliation":
                # Always supply source_dataset (compiler requires it)
                if not params.get("source_dataset"):
                    src_qual = (
                        f"{target_schema}.{target_table}"
                        if target_schema and target_table
                        else target_table
                    )
                    if src_qual:
                        params["source_dataset"] = src_qual
                if not params.get("target_dataset") and secondary:
                    params["target_dataset"] = secondary[0]
            else:
                if not params.get("reference_dataset"):
                    if secondary:
                        params["reference_dataset"] = secondary[0]
                    elif _dim_lower == "accuracy":
                        # Heuristic: pick a workspace dataset whose name
                        # contains "ref" / "reference" / "trusted".
                        for r in ws_datasets:
                            ds_name = (r[0] or "").lower()
                            ident = (r[2] or "").lower()
                            if ident == primary_ident:
                                continue
                            if any(
                                k in ident or k in ds_name
                                for k in ("ref", "reference", "trusted", "_ref")
                            ):
                                qualified = f"{r[1]}.{r[2]}" if r[1] else r[2]
                                params["reference_dataset"] = qualified
                                break

            # ── Fill join_keys from shared dataset columns ─────────────
            need_join = (
                _dim_lower == "accuracy"
                and _sub_lower
                in (
                    "reference_comparison",
                    "trusted_source",
                    "tolerated_deviation",
                )
                and not params.get("join_keys")
            ) or (
                _dim_lower == "reconciliation"
                and _sub_lower
                in (
                    "one_to_one",
                    "field_level",
                    "aggregate",
                    "tolerance",
                    "missing_extra",
                )
                and not params.get("join_keys")
            )
            secondary_for_join = params.get("target_dataset") or params.get("reference_dataset")
            if need_join and secondary_for_join and target_table:
                # Resolve to physical_identifier
                def _split(qual):
                    if not qual:
                        return None, None
                    if "." in qual:
                        s, t = qual.split(".", 1)
                        return s, t
                    return None, qual

                _, sec_ident = _split(secondary_for_join)
                try:
                    shared_cols = db.execute(
                        text(
                            """
                            SELECT f1.field_name
                            FROM control.dataset_fields f1
                            JOIN control.datasets d1 ON d1.dataset_id = f1.dataset_id
                            JOIN control.datasets d2 ON d2.workspace_id = d1.workspace_id
                            JOIN control.dataset_fields f2
                              ON f2.dataset_id = d2.dataset_id
                             AND f2.field_name = f1.field_name
                            WHERE d1.workspace_id = CAST(:ws AS UUID)
                              AND d1.physical_identifier = :p
                              AND d2.physical_identifier = :s
                            """
                        ),
                        {
                            "ws": str(workspace_id),
                            "p": target_table,
                            "s": sec_ident,
                        },
                    ).fetchall()
                except Exception:
                    shared_cols = []
                shared = [r[0] for r in shared_cols if r and r[0]]
                priority = (
                    "sku",
                    "id",
                    "key",
                    "code",
                    "txn_id",
                    "uuid",
                )
                pick = None
                lowered = {c.lower(): c for c in shared}
                for cand in priority:
                    if cand in lowered:
                        pick = lowered[cand]
                        break
                if not pick:
                    for c in shared:
                        if c.lower().endswith("_id"):
                            pick = c
                            break
                if pick:
                    params["join_keys"] = [pick]

        # ── Inline compile (best-effort) ────────────────────────────────
        canonical = {
            "dimension": check_dimension,
            "entity": entity,
            "condition": condition,
            "expectation": expectation,
            "severity": severity,
            "parameters": self._normalize_compiler_parameters(
                check_dimension,
                check_subtype,
                dict(params),
                entity_col,
            ),
        }
        compiled_postgres = ""
        compiled_sql = ""
        if target_table:
            try:
                from app.services.rules.compiler import RuleCompiler

                compiled_dict = RuleCompiler().compile_rule(
                    canonical_rule=canonical,
                    target_schema=target_schema,
                    target_table=target_table,
                    target_columns=[entity_col] if entity_col else None,
                )
                if not compiled_dict.get("error"):
                    compiled_postgres = compiled_dict.get("compiled_postgres") or ""
                    compiled_sql = compiled_dict.get("compiled_sql") or compiled_postgres
                else:
                    err_msg = compiled_dict.get("error_message") or compiled_dict.get("error")
                    logger.warning(
                        "compile_rule returned error for proposal %s: %s | canonical=%s",
                        proposal.proposal_id,
                        err_msg,
                        canonical,
                    )
            except Exception as ex:
                logger.warning(
                    "compile_rule failed for proposal %s: %s",
                    proposal.proposal_id,
                    ex,
                )

        rule_name = proposal.original_prompt[:255]
        rule_id = uuid.uuid4()
        now = datetime.now(UTC)

        # Resolve the rule's data_source_id. The new tenant-owned connections
        # layer writes to ``control.data_sources`` only — but the rule
        # executor still expects a row in legacy ``public.data_sources``
        # (DQRule.data_source FK). Mirror the control row with the same UUID
        # so the FK is satisfied and ConnectionManager can decrypt credentials.
        ds_id_for_rule = meta.get(
            "public_data_source_id"
        ) or self._ensure_public_data_source_mirror(
            db,
            meta.get("control_data_source_id"),
            workspace_id,
        )

        try:
            db.execute(
                text("""
                    INSERT INTO dq_rules
                        (id, workspace_id, name, description, category, rule_type,
                         canonical_rule, target_schema, target_table, target_columns,
                         data_source_id, compiled_sql, compiled_postgres,
                         status, is_active, tags, created_by, created_at, updated_at)
                    VALUES
                        (:id, :ws, :name, :desc, :cat, :rtype,
                         :canonical, :tschema, :table, :cols,
                         :ds_id, :csql, :cpg,
                         'active', true, :tags, :user, :now, :now)
                """),
                {
                    "id": str(rule_id),
                    "ws": str(workspace_id),
                    "name": rule_name,
                    "desc": proposal.original_prompt,
                    "cat": check_dimension,
                    "rtype": (check_subtype or rule_type_raw),
                    "canonical": json.dumps(canonical, default=str),
                    "tschema": target_schema,
                    "table": target_table,
                    "cols": [entity_col] if entity_col else None,
                    "ds_id": ds_id_for_rule,
                    "csql": compiled_sql or None,
                    "cpg": compiled_postgres or None,
                    "tags": ["nl-generated"],
                    "user": str(proposal.created_by) if proposal.created_by else None,
                    "now": now,
                },
            )
            logger.info(
                "Created rule %s from proposal %s (dim=%s, subtype=%s, ds=%s, table=%s)",
                rule_id,
                proposal.proposal_id,
                check_dimension,
                check_subtype,
                ds_id_for_rule,
                target_table,
            )
            return str(rule_id)
        except Exception as e:
            logger.warning(f"Failed to create rule from proposal {proposal.proposal_id}: {e}")
            return None

    @staticmethod
    def _row_to_response(row) -> ProposalResponse:
        payload_raw = row["proposal_payload"]
        if isinstance(payload_raw, str):
            payload_raw = json.loads(payload_raw)

        adj_raw = row["adjustments"]
        if isinstance(adj_raw, str):
            adj_raw = json.loads(adj_raw)

        return ProposalResponse(
            proposal_id=uuid.UUID(str(row["id"])),
            workspace_id=uuid.UUID(str(row["workspace_id"])),
            created_by=row.get("created_by"),
            status=ProposalStatus(row["status"]),
            original_prompt=row["original_prompt"],
            proposal_payload=ProposalPayload(**payload_raw),
            adjustments=[ProposalAdjustment(**a) for a in (adj_raw or []) if "field" in a],
            generated_flow_id=uuid.UUID(str(row["generated_flow_id"]))
            if row.get("generated_flow_id")
            else None,
            confidence=float(row.get("confidence", 0)),
            created_at=row["created_at"],
            updated_at=row.get("updated_at") or row["created_at"],
        )
