"""
F134 P03 — Tests for rejection_validation.py
"""

from app.services.sandbox.validation.rejection_validation import validate_rejection


class TestValidateRejection:
    def test_valid_reason(self):
        assert validate_rejection(reason="Not a fit for our platform right now.") == []

    def test_empty_reason_returns_error(self):
        errs = validate_rejection(reason="")
        assert len(errs) == 1
        assert errs[0][0] == "reason"

    def test_too_short_returns_error(self):
        errs = validate_rejection(reason="ab")
        assert len(errs) == 1

    def test_exactly_3_chars_ok(self):
        assert validate_rejection(reason="nah") == []

    def test_exactly_300_chars_ok(self):
        assert validate_rejection(reason="A" * 300) == []

    def test_301_chars_returns_error(self):
        errs = validate_rejection(reason="A" * 301)
        assert len(errs) == 1
