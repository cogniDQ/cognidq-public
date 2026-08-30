"""
F134 P03 — Rejection Validation (DB-free)
"""

from __future__ import annotations

ValidationErrors = list[tuple[str, str]]


def validate_rejection(*, reason: str) -> ValidationErrors:
    """reason must be 3–300 characters after stripping."""
    stripped = (reason or "").strip()
    if len(stripped) < 3 or len(stripped) > 300:
        return [("reason", "Rejection reason must be between 3 and 300 characters.")]
    return []
