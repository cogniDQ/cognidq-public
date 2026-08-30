"""
F134 P03 — Tests for extension_validation.py
"""

from app.services.sandbox.validation.extension_validation import (
    MAX_EXTENSIONS,
    validate_extension,
)


class TestValidateExtension:
    def test_valid_extension(self):
        assert (
            validate_extension(note="This prospect is very engaged.", current_extension_count=0)
            == []
        )

    def test_note_too_short_returns_error(self):
        errs = validate_extension(note="short", current_extension_count=0)
        assert any(e[0] == "note" for e in errs)

    def test_note_exactly_10_chars_ok(self):
        assert validate_extension(note="1234567890", current_extension_count=0) == []

    def test_empty_note_returns_error(self):
        errs = validate_extension(note="", current_extension_count=0)
        assert any(e[0] == "note" for e in errs)

    def test_at_max_extensions_returns_error(self):
        errs = validate_extension(
            note="Good enough note here.", current_extension_count=MAX_EXTENSIONS
        )
        assert any(e[0] == "extension_count" for e in errs)

    def test_below_max_extensions_ok(self):
        assert validate_extension(note="Acceptable note text.", current_extension_count=1) == []

    def test_both_errors_accumulated(self):
        errs = validate_extension(note="short", current_extension_count=MAX_EXTENSIONS)
        fields = [e[0] for e in errs]
        assert "note" in fields
        assert "extension_count" in fields
