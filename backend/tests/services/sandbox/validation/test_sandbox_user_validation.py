"""
F134 P03 — Tests for sandbox_user_validation.py
"""

import pytest
from app.services.sandbox.validation.sandbox_user_validation import (
    VALID_ONBOARDING_STEPS,
    validate_extension_request_message,
    validate_onboarding_step,
)


class TestValidateOnboardingStep:
    @pytest.mark.parametrize("step", list(VALID_ONBOARDING_STEPS))
    def test_all_valid_steps_pass(self, step):
        assert validate_onboarding_step(step_id=step) == []

    def test_invalid_step_returns_error(self):
        errs = validate_onboarding_step(step_id="fly_to_moon")
        assert len(errs) == 1
        assert errs[0][0] == "step_id"

    def test_empty_step_returns_error(self):
        errs = validate_onboarding_step(step_id="")
        assert len(errs) == 1


class TestValidateExtensionRequestMessage:
    def test_valid_message(self):
        assert validate_extension_request_message(message="I need more time for evaluation.") == []

    def test_too_short_returns_error(self):
        errs = validate_extension_request_message(message="short")
        assert len(errs) == 1
        assert errs[0][0] == "message"

    def test_exactly_10_chars_ok(self):
        assert validate_extension_request_message(message="1234567890") == []

    def test_empty_message_returns_error(self):
        errs = validate_extension_request_message(message="")
        assert len(errs) == 1
