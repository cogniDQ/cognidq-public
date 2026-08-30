"""
F134 P03 — Sandbox-user endpoint Pydantic schemas.
"""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from app.services.sandbox.validation.sandbox_user_validation import (
    validate_extension_request_message,
    validate_onboarding_step,
)


class OnboardingStepCompleteBody(BaseModel):
    """POST /api/v1/sandbox/onboarding/{step_id}/complete"""

    step_id: str

    @model_validator(mode="after")
    def _validate(self) -> OnboardingStepCompleteBody:
        errors = validate_onboarding_step(step_id=self.step_id)
        if errors:
            raise ValueError(errors[0][1])
        return self


class ExtensionRequestBody(BaseModel):
    """POST /api/v1/sandbox/extension-request"""

    message: str

    @model_validator(mode="after")
    def _validate(self) -> ExtensionRequestBody:
        errors = validate_extension_request_message(message=self.message)
        if errors:
            raise ValueError(errors[0][1])
        return self
