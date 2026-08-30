"""
Compilation validators — type compatibility, constraint checks.
"""

from __future__ import annotations

import re

from app.schemas.nl_compiler import ValidationError as ValError
from app.schemas.nl_rule_builder import StructuredIntermediateRepresentation
from app.services.nl_compiler.mappings import (
    RULE_TYPE_REQUIRED_TYPES,
    TYPE_COMPAT,
)


def validate_compatibility(
    sir: StructuredIntermediateRepresentation,
    column_data_types: dict[str, str] | None = None,
) -> list[ValError]:
    """Run all validation checks on the resolved SIR. Returns list of errors (empty = valid)."""
    errors: list[ValError] = []

    # 1. Subject must be resolved
    if not sir.subject.resolved_column:
        errors.append(
            ValError(
                field="subject.resolved_column",
                message="Subject column is not resolved. Run resolution first.",
                code="unresolved_subject",
            )
        )

    # 2. Object required for comparison types
    comparison_types = {
        "column_comparison",
        "date_comparison",
        "arithmetic_comparison",
    }
    rule_type = sir.rule_type.value
    if rule_type in comparison_types:
        if sir.object is None or not sir.object.resolved_column:
            errors.append(
                ValError(
                    field="object.resolved_column",
                    message=f"Rule type '{rule_type}' requires a resolved object column.",
                    code="unresolved_object",
                )
            )

    # 3. Operator required for most types
    operator_required = {
        "column_comparison",
        "numeric_threshold",
        "date_comparison",
        "arithmetic_comparison",
    }
    if rule_type in operator_required and not sir.operator:
        errors.append(
            ValError(
                field="operator",
                message=f"Rule type '{rule_type}' requires an operator.",
                code="missing_operator",
            )
        )

    # 4. Data-type compatibility
    if column_data_types and rule_type in RULE_TYPE_REQUIRED_TYPES:
        required_category = RULE_TYPE_REQUIRED_TYPES[rule_type]
        allowed_types = TYPE_COMPAT.get(required_category, set())
        col = sir.subject.resolved_column
        if col and col in column_data_types:
            col_type = column_data_types[col].lower()
            if not any(col_type.startswith(t) for t in allowed_types):
                errors.append(
                    ValError(
                        field="subject.data_type",
                        message=f"Column '{col}' has type '{column_data_types[col]}' which is incompatible with rule type '{rule_type}' (expected {required_category}).",
                        code="type_incompatible",
                    )
                )

    # 5. Constraint validation
    errors.extend(_validate_constraints(sir))

    return errors


def _validate_constraints(sir: StructuredIntermediateRepresentation) -> list[ValError]:
    """Validate rule-type-specific constraints."""
    errors: list[ValError] = []
    rule_type = sir.rule_type.value

    if rule_type == "value_in_list":
        if not sir.constraints:
            errors.append(
                ValError(
                    field="constraints",
                    message="value_in_list requires a non-empty constraints list.",
                    code="empty_value_list",
                )
            )

    if rule_type == "regex_format":
        # The first constraint should be the regex pattern
        if sir.constraints:
            pattern = (
                sir.constraints[0]
                if isinstance(sir.constraints[0], str)
                else str(sir.constraints[0])
            )
            try:
                re.compile(pattern)
            except re.error as e:
                errors.append(
                    ValError(
                        field="constraints[0]",
                        message=f"Invalid regex pattern: {e}",
                        code="invalid_regex",
                    )
                )
        else:
            errors.append(
                ValError(
                    field="constraints",
                    message="regex_format requires a pattern in constraints.",
                    code="missing_regex_pattern",
                )
            )

    if rule_type == "composite_uniqueness":
        # Need subject + either object or constraints listing additional columns
        if not sir.object and not sir.constraints:
            errors.append(
                ValError(
                    field="constraints",
                    message="composite_uniqueness requires multiple columns (object or constraints).",
                    code="missing_composite_columns",
                )
            )

    if rule_type == "conditional_rule":
        if not sir.conditions:
            errors.append(
                ValError(
                    field="conditions",
                    message="conditional_rule requires at least one condition.",
                    code="missing_conditions",
                )
            )

    return errors
