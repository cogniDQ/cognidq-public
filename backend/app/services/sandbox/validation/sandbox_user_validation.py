"""
F134 P03 — Sandbox-User Action Validation (DB-free)

Validates in-sandbox user actions:
  - onboarding step completion (step_id in fixed enum)
  - extension request messages
"""

from __future__ import annotations

ValidationErrors = list[tuple[str, str]]

VALID_ONBOARDING_STEPS: frozenset[str] = frozenset(
    {
        "view_datasets",
        "run_check",
        "view_issues",
        "create_rule",
        "view_dashboard",
        "invite_teammate",
        "complete_profile",
    }
)


def validate_onboarding_step(*, step_id: str) -> ValidationErrors:
    if step_id not in VALID_ONBOARDING_STEPS:
        return [
            (
                "step_id",
                f"Unknown onboarding step '{step_id}'. Allowed: {sorted(VALID_ONBOARDING_STEPS)}",
            )
        ]
    return []


def validate_extension_request_message(*, message: str) -> ValidationErrors:
    """Sandbox user extension-request message must be >= 10 chars."""
    stripped = (message or "").strip()
    if len(stripped) < 10:
        return [("message", "Extension request message must be at least 10 characters.")]
    return []
