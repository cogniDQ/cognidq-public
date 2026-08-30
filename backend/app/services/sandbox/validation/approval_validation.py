"""
F134 P03 — Admin Approval Validation (DB-free)

Validates the approve-request payload.
No DB calls: template_id and access_profile_code existence checks are
performed via injected callback hooks to keep this module DB-free.
"""

from __future__ import annotations

from collections.abc import Callable

ValidationErrors = list[tuple[str, str]]

VALID_DURATION_DAYS: frozenset[int] = frozenset({3, 7, 10, 14})

VALID_ADMIN_TAGS: frozenset[str] = frozenset(
    {
        "high_intent",
        "enterprise_target",
        "low_priority",
        "follow_up_later",
        "competitor_research",
    }
)


def validate_approval(
    *,
    template_id: str,
    duration_days: int,
    access_profile_code: str,
    tags: list[str] | None = None,
    internal_note: str | None = None,
    template_id_exists: Callable[[str], bool] = lambda _: True,
    access_profile_code_exists: Callable[[str], bool] = lambda _: True,
) -> ValidationErrors:
    """
    Validate admin approval payload.

    ``template_id_exists`` and ``access_profile_code_exists`` are callable hooks
    so this function stays DB-free; callers inject real lookups.
    """
    errors: ValidationErrors = []

    if not template_id or not template_id.strip():
        errors.append(("template_id", "Template ID is required."))
    elif not template_id_exists(template_id):
        errors.append(("template_id", f"Template '{template_id}' does not exist or is disabled."))

    if duration_days not in VALID_DURATION_DAYS:
        errors.append(
            ("duration_days", f"Duration must be one of {sorted(VALID_DURATION_DAYS)} days.")
        )

    if not access_profile_code or not access_profile_code.strip():
        errors.append(("access_profile_code", "Access profile code is required."))
    elif not access_profile_code_exists(access_profile_code):
        errors.append(
            (
                "access_profile_code",
                f"Access profile '{access_profile_code}' does not exist or is disabled.",
            )
        )

    if tags:
        invalid_tags = [t for t in tags if t not in VALID_ADMIN_TAGS]
        if invalid_tags:
            errors.append(
                ("tags", f"Unknown tag(s): {invalid_tags}. Allowed: {sorted(VALID_ADMIN_TAGS)}")
            )

    return errors
