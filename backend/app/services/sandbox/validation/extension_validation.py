"""
F134 P03 — Extension Validation (DB-free)

Validates admin-initiated extension requests.
"""

from __future__ import annotations

ValidationErrors = list[tuple[str, str]]

MAX_EXTENSIONS = 2


def validate_extension(*, note: str, current_extension_count: int) -> ValidationErrors:
    """
    note must be >= 10 chars; extension_count must be < MAX_EXTENSIONS.
    """
    errors: ValidationErrors = []

    stripped_note = (note or "").strip()
    if len(stripped_note) < 10:
        errors.append(("note", "An internal note (10+ chars) is required when extending."))

    if current_extension_count >= MAX_EXTENSIONS:
        errors.append(
            ("extension_count", f"Maximum of {MAX_EXTENSIONS} extensions allowed per sandbox.")
        )

    return errors
