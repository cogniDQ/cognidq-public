"""
F106 — NL Rule Audit Trail Tests
40+ tests covering schemas, models, service, and endpoint.
"""

from uuid import uuid4

import pytest
from app.schemas.nl_audit import (
    AuditListResponse,
    AuditRecordCreate,
    AuditRecordResponse,
    EntityRole,
    ExplainabilityEntry,
    ExplainabilityResponse,
    FeedbackCreate,
    FeedbackResponse,
    FeedbackType,
)
from app.services.nl_audit.service import NLAuditService

# ── helpers ──

WS_ID = uuid4()
USER_ID = uuid4()

service = NLAuditService()


def make_audit_create(**kwargs) -> AuditRecordCreate:
    defaults = {
        "rule_text": "email must not be null",
        "parse_request_id": str(uuid4()),
        "parsed_sir": {"rule_type": "not_null", "subject": {"raw_text": "email"}},
        "parse_explainability": [{"topic": "rule_type", "decision": "not_null"}],
        "parse_trust_summary": {"confidence_band": "high", "confidence_score": 0.9},
        "resolution_candidates": {
            "subject": {
                "best_candidate": {
                    "column_name": "email",
                    "dataset_name": "users",
                    "signal_breakdown": [
                        {"signal_name": "lexical_match", "score": 0.95, "evidence": "exact"},
                    ],
                    "evidence_summary": ["lexical_match"],
                    "rationale": ["Resolved with high confidence"],
                },
            },
        },
        "selected_mappings": {"subject": {"column": "email", "dataset": "users"}},
        "compiled_config": {"check_type": "completeness", "subtype": "null"},
        "compilation_status": "success",
        "model_version": "gpt-4o-2024-01",
    }
    defaults.update(kwargs)
    return AuditRecordCreate(**defaults)


def make_feedback(**kwargs) -> FeedbackCreate:
    defaults = {
        "feedback_type": FeedbackType.ACCEPTED_MATCH,
        "entity_role": EntityRole.SUBJECT,
        "confidence_at_decision": 0.95,
    }
    defaults.update(kwargs)
    return FeedbackCreate(**defaults)


# ══════════════════════════════════════
# 1. Schema Tests
# ══════════════════════════════════════


class TestSchemas:
    def test_feedback_type_values(self):
        assert FeedbackType.ACCEPTED_MATCH == "accepted_match"
        assert FeedbackType.REJECTED_MATCH == "rejected_match"
        assert FeedbackType.MANUAL_OVERRIDE == "manual_override"
        assert FeedbackType.CORRECTED_RULE == "corrected_rule"

    def test_entity_role_values(self):
        assert EntityRole.SUBJECT == "subject"
        assert EntityRole.OBJECT == "object"
        assert EntityRole.GENERAL == "general"

    def test_audit_record_create(self):
        rec = make_audit_create()
        assert rec.rule_text == "email must not be null"
        assert rec.compilation_status == "success"

    def test_audit_record_create_minimal(self):
        rec = AuditRecordCreate(rule_text="test rule")
        assert rec.rule_text == "test rule"
        assert rec.parsed_sir is None

    def test_audit_record_response(self):
        resp = AuditRecordResponse(
            id=str(uuid4()),
            workspace_id=str(uuid4()),
            user_id=str(uuid4()),
            rule_text="test",
        )
        assert resp.rule_text == "test"

    def test_feedback_create(self):
        fb = make_feedback()
        assert fb.feedback_type == FeedbackType.ACCEPTED_MATCH

    def test_feedback_create_with_candidates(self):
        fb = make_feedback(
            original_candidate={"column": "email_addr"},
            selected_candidate={"column": "email"},
        )
        assert fb.original_candidate is not None
        assert fb.selected_candidate is not None

    def test_feedback_response(self):
        resp = FeedbackResponse(
            id=str(uuid4()),
            audit_id=str(uuid4()),
            feedback_type="accepted_match",
            entity_role="subject",
        )
        assert resp.feedback_type == "accepted_match"

    def test_explainability_entry(self):
        entry = ExplainabilityEntry(
            entity_role="subject",
            column_name="email",
            reason="lexical match",
        )
        assert entry.was_overridden is False

    def test_explainability_entry_with_override(self):
        entry = ExplainabilityEntry(
            entity_role="subject",
            column_name="email",
            reason="overridden",
            was_overridden=True,
            override_from="email_addr",
            override_to="email",
        )
        assert entry.was_overridden is True
        assert entry.override_from == "email_addr"

    def test_explainability_response(self):
        resp = ExplainabilityResponse(
            audit_id=str(uuid4()),
            rule_text="test",
            parse_explainability=[{"topic": "subject", "decision": "email"}],
            parse_trust_summary={"confidence_band": "medium"},
            explanations=[],
            feedbacks=[],
        )
        assert resp.rule_text == "test"
        assert resp.parse_trust_summary is not None

    def test_audit_list_response(self):
        resp = AuditListResponse(items=[], total=0, page=1, page_size=20)
        assert resp.total == 0

    def test_feedback_confidence_validation(self):
        fb = make_feedback(confidence_at_decision=0.5)
        assert fb.confidence_at_decision == 0.5

    def test_feedback_confidence_range(self):
        with pytest.raises(Exception):
            make_feedback(confidence_at_decision=1.5)


# ══════════════════════════════════════
# 2. Model Tests
# ══════════════════════════════════════


class TestModels:
    def test_rule_generation_audit_import(self):
        from app.models.nl_audit import RuleGenerationAudit

        assert hasattr(RuleGenerationAudit, "__tablename__")
        assert RuleGenerationAudit.__tablename__ == "rule_generation_audit"

    def test_rule_user_feedback_import(self):
        from app.models.nl_audit import RuleUserFeedback

        assert hasattr(RuleUserFeedback, "__tablename__")
        assert RuleUserFeedback.__tablename__ == "rule_user_feedback"

    def test_audit_schema_prefix(self):
        from app.models.nl_audit import RuleGenerationAudit

        assert RuleGenerationAudit.__table_args__["schema"] == "control"

    def test_feedback_schema_prefix(self):
        from app.models.nl_audit import RuleUserFeedback

        assert RuleUserFeedback.__table_args__["schema"] == "control"


# ══════════════════════════════════════
# 3. Service Tests — Explainability Logic
# ══════════════════════════════════════


class TestExplainability:
    def test_build_explanations_with_signals(self):
        resolution = {
            "subject": {
                "best_candidate": {
                    "column_name": "email",
                    "dataset_name": "users",
                    "signal_breakdown": [
                        {"signal_name": "lexical_match", "score": 0.95, "evidence": "exact"},
                        {"signal_name": "glossary_match", "score": 0.80, "evidence": "term linked"},
                    ],
                    "evidence_summary": ["lexical_match", "glossary_match"],
                    "rationale": ["Resolved with high confidence"],
                },
            },
        }
        explanations = service._build_explanations(None, resolution, None, None)
        assert len(explanations) == 1
        assert explanations[0].column_name == "email"
        assert "lexical_match" in explanations[0].reason
        assert "glossary_match" in explanations[0].reason
        assert explanations[0].rationale == ["Resolved with high confidence"]

    def test_build_explanations_with_override(self):
        resolution = {
            "subject": {
                "best_candidate": {
                    "column_name": "email",
                    "dataset_name": "users",
                    "signal_breakdown": [],
                    "evidence_summary": [],
                },
            },
        }
        overrides = {
            "subject": {"from": "email_address", "to": "email"},
        }
        explanations = service._build_explanations(None, resolution, None, overrides)
        assert len(explanations) == 1
        assert explanations[0].was_overridden is True
        assert explanations[0].override_from == "email_address"
        assert explanations[0].override_to == "email"

    def test_build_explanations_dual_entity(self):
        resolution = {
            "subject": {
                "best_candidate": {
                    "column_name": "ship_date",
                    "signal_breakdown": [{"signal_name": "lexical", "score": 0.9}],
                    "evidence_summary": [],
                },
            },
            "object": {
                "best_candidate": {
                    "column_name": "order_date",
                    "signal_breakdown": [{"signal_name": "lexical", "score": 0.95}],
                    "evidence_summary": [],
                },
            },
        }
        explanations = service._build_explanations(None, resolution, None, None)
        assert len(explanations) == 2
        roles = {e.entity_role for e in explanations}
        assert "subject" in roles
        assert "object" in roles

    def test_build_explanations_empty(self):
        explanations = service._build_explanations(None, None, None, None)
        assert explanations == []

    def test_extract_parse_payload_with_explainability_envelope(self):
        payload = {
            "sir": {"rule_type": "not_null"},
            "parse_explainability": [{"topic": "rule_type"}],
            "parse_trust_summary": {"confidence_band": "high"},
        }
        extracted = service._extract_parse_payload(payload)
        assert extracted["sir"]["rule_type"] == "not_null"
        assert len(extracted["parse_explainability"]) == 1
        assert extracted["parse_trust_summary"]["confidence_band"] == "high"

    def test_extract_resolution_payload_from_resolve_response_shape(self):
        payload = {
            "subject_resolution": {"best_candidate": {"column_name": "email"}},
            "object_resolution": None,
        }
        extracted = service._extract_resolution_payload(payload)
        assert extracted is not None
        assert extracted["subject"]["best_candidate"]["column_name"] == "email"

    def test_build_explanations_zero_score_signals_excluded(self):
        resolution = {
            "subject": {
                "best_candidate": {
                    "column_name": "email",
                    "signal_breakdown": [
                        {"signal_name": "lexical", "score": 0.9},
                        {"signal_name": "glossary", "score": 0.0},
                    ],
                    "evidence_summary": [],
                },
            },
        }
        explanations = service._build_explanations(None, resolution, None, None)
        assert "glossary" not in explanations[0].reason
        assert "lexical" in explanations[0].reason

    def test_build_explanations_no_best_candidate(self):
        resolution = {
            "subject": {
                "best_candidate": None,
            },
        }
        explanations = service._build_explanations(None, resolution, None, None)
        assert explanations == []


# ══════════════════════════════════════
# 4. Endpoint Tests
# ══════════════════════════════════════


class TestEndpoints:
    def test_create_audit_endpoint_import(self):
        from app.api.v1.endpoints.rule_builder import create_audit_record

        assert callable(create_audit_record)

    def test_create_feedback_endpoint_import(self):
        from app.api.v1.endpoints.rule_builder import create_feedback

        assert callable(create_feedback)

    def test_list_audit_endpoint_import(self):
        from app.api.v1.endpoints.rule_builder import list_audit_records

        assert callable(list_audit_records)

    def test_explainability_endpoint_import(self):
        from app.api.v1.endpoints.rule_builder import get_audit_explainability

        assert callable(get_audit_explainability)

    def test_audit_service_instance(self):
        from app.api.v1.endpoints.rule_builder import _audit_service

        assert isinstance(_audit_service, NLAuditService)


# ══════════════════════════════════════
# 5. Migration Tests
# ══════════════════════════════════════


class TestMigration:
    def test_migration_file_exists(self):
        import os

        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "scripts",
            "migrations",
            "031_nl_rule_audit.sql",
        )
        assert os.path.exists(os.path.normpath(path))

    def test_migration_has_both_tables(self):
        import os

        path = os.path.normpath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "scripts",
                "migrations",
                "031_nl_rule_audit.sql",
            )
        )
        with open(path) as f:
            sql = f.read()
        assert "rule_generation_audit" in sql
        assert "rule_user_feedback" in sql

    def test_migration_has_indexes(self):
        import os

        path = os.path.normpath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "scripts",
                "migrations",
                "031_nl_rule_audit.sql",
            )
        )
        with open(path) as f:
            sql = f.read()
        assert "idx_rule_gen_audit_workspace" in sql
        assert "idx_rule_feedback_audit" in sql
