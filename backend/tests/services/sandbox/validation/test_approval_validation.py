"""
F134 P03 — Tests for approval_validation.py
"""

import pytest
from app.services.sandbox.validation.approval_validation import (
    VALID_ADMIN_TAGS,
    VALID_DURATION_DAYS,
    validate_approval,
)


class TestValidateApproval:
    def _valid(self, **overrides):
        base = dict(
            template_id="general_dq",
            duration_days=7,
            access_profile_code="mvp_default",
            tags=None,
            internal_note=None,
        )
        base.update(overrides)
        return base

    def test_valid_returns_empty(self):
        assert validate_approval(**self._valid()) == []

    @pytest.mark.parametrize("days", list(VALID_DURATION_DAYS))
    def test_all_valid_durations(self, days):
        assert validate_approval(**self._valid(duration_days=days)) == []

    def test_invalid_duration_returns_error(self):
        errs = validate_approval(**self._valid(duration_days=5))
        fields = [e[0] for e in errs]
        assert "duration_days" in fields

    def test_empty_template_id_returns_error(self):
        errs = validate_approval(**self._valid(template_id=""))
        assert any(e[0] == "template_id" for e in errs)

    def test_template_id_not_exists_returns_error(self):
        errs = validate_approval(
            **self._valid(
                template_id="nonexistent",
                template_id_exists=lambda _: False,
            )
        )
        assert any(e[0] == "template_id" for e in errs)

    def test_template_id_exists_hook_passes(self):
        errs = validate_approval(**self._valid(template_id_exists=lambda _: True))
        assert errs == []

    def test_empty_access_profile_returns_error(self):
        errs = validate_approval(**self._valid(access_profile_code=""))
        assert any(e[0] == "access_profile_code" for e in errs)

    def test_access_profile_not_exists_returns_error(self):
        errs = validate_approval(
            **self._valid(
                access_profile_code="unknown",
                access_profile_code_exists=lambda _: False,
            )
        )
        assert any(e[0] == "access_profile_code" for e in errs)

    def test_valid_tags_pass(self):
        errs = validate_approval(**self._valid(tags=["high_intent", "enterprise_target"]))
        assert errs == []

    def test_invalid_tag_returns_error(self):
        errs = validate_approval(**self._valid(tags=["bogus_tag"]))
        assert any(e[0] == "tags" for e in errs)

    def test_mixed_tags_with_invalid_returns_error(self):
        errs = validate_approval(**self._valid(tags=["high_intent", "unknown_tag"]))
        assert any(e[0] == "tags" for e in errs)

    def test_all_valid_tags_pass(self):
        errs = validate_approval(**self._valid(tags=list(VALID_ADMIN_TAGS)))
        assert errs == []

    def test_none_tags_ok(self):
        assert validate_approval(**self._valid(tags=None)) == []
