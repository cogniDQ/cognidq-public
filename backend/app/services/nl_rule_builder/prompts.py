"""
LLM Prompt Templates for NL Rule Parsing.
Constrained prompts that force LLM output into the SIR JSON schema.
Covers all 47 check type+subtype combinations from dq_expected_results.
"""

from app.services.nl_compiler.subtype_schema import format_inventory_for_prompt

# Pre-rendered catalogue of every (dimension → subtype → required fields).
# Injected verbatim into the prompt so the LLM knows exactly which subtype
# names are valid and which configuration keys must accompany each.
SUBTYPE_INVENTORY_TEXT = format_inventory_for_prompt()

# All supported rule types with descriptions — maps to dq_expected_results dimensions/subtypes
RULE_TYPE_DESCRIPTIONS = """
Supported rule types (use EXACTLY one of these values for rule_type):

COMPLETENESS CHECKS:
- "not_null": Field must not be NULL. E.g., "email must not be null"
- "null_check": Field must be NULL. E.g., "archived_date must be null for active records"
- "empty_check": Field must not be empty string or whitespace. E.g., "name must not be empty, include empty strings"
- "placeholder_check": Field must not contain placeholder values like N/A, TBD, unknown. E.g., "address cannot contain placeholder values like N/A or TBD"
- "multi_field_completeness": Multiple fields must be complete (any or all). E.g., "either phone or email must be filled"
- "conditional_completeness": Field must be complete when a condition holds. E.g., "if status is active, department must not be null"
- "group_completeness": Completeness measured per group. E.g., "email completeness by region should be above 90%"
- "population_completeness": Overall population completeness with threshold. E.g., "customer_id completeness must be above 95%"

UNIQUENESS CHECKS:
- "uniqueness": Single column uniqueness. E.g., "employee ID must be unique"
- "composite_uniqueness": Combination of columns must be unique together. E.g., "order_id and line_number must be unique together"
- "scoped_uniqueness": Uniqueness within a scope/partition. E.g., "order_id must be unique within each region"
- "fuzzy_uniqueness": Near-duplicate detection. E.g., "company name should have no near-duplicates"
- "temporal_uniqueness": Uniqueness within a time window. E.g., "sensor_id must be unique within 24 hours"

CONFORMITY CHECKS:
- "regex_format": Field matches a regex pattern. E.g., "invoice code must match INV-######"
- "length_check": Field has expected length range. E.g., "username must be 3 to 20 characters"
- "case_check": Field conforms to case rule. E.g., "country code must be uppercase"
- "charset_check": Field uses allowed character set. E.g., "first name must contain only letters"
- "standard_format": Field matches a named standard. E.g., "email must be valid email format" or "phone must be valid phone format"
- "structural_pattern": Field matches a structural pattern template. E.g., "part number must follow pattern AA-9999"

CONSISTENCY CHECKS:
- "column_comparison": Intra-record column comparison. E.g., "end_date must be after start_date"
- "formula_check": Formula/expression consistency. E.g., "total must equal quantity times unit_price"
- "temporal_consistency": Date ordering consistency. E.g., "start_date must be before end_date"
- "inter_record": Consistency across records in same group. E.g., "currency must be consistent per customer"
- "aggregation_consistency": Aggregate must match expected. E.g., "sum of line totals must equal order total"

VALIDITY CHECKS:
- "value_in_list": Field is one of allowed values. E.g., "priority must be low, medium, or high"
- "numeric_range": Number within range. E.g., "score must be between 0 and 100"
- "date_logic": Date comparisons. E.g., "ship date must be after order date"
- "reference_lookup": Field value exists in reference table. E.g., "department must exist in departments reference"
- "business_rule": Complex business rule expression. E.g., "amount must be positive and status not cancelled"
- "cross_field": Cross-field validation. E.g., "end_value must be greater than or equal to start_value"
- "negative_pattern": Field must NOT match a pattern. E.g., "email must not start with test."
- "regex_validation": Field matches regex (validity dimension). E.g., "product code must match PRD-####"

ACCURACY CHECKS:
- "reference_comparison": Compare field against trusted reference. E.g., "customer name must match CRM master"
- "tolerated_deviation": Field within tolerance of reference. E.g., "salary must be within 1000 of HR system value"
- "statistical_outlier": Detect statistical outliers. E.g., "score must not be a statistical outlier (IQR method)"
- "derived_value": Computed value accuracy. E.g., "bonus must equal salary times bonus rate"

TIMELINESS CHECKS:
- "freshness": Data recency check. E.g., "data must be updated within last 24 hours"
- "record_age": Individual record age. E.g., "records must not be older than 30 days"
- "latency": Processing latency check. E.g., "load time must be within 2 hours of event time"
- "processing_delay": Processing duration check. E.g., "processing must complete within 60 minutes"
- "delivery_window": Data delivered in expected window. E.g., "delivery must happen between 6 AM and 9 AM"
- "heartbeat": Regular update frequency check. E.g., "system must have updates at least every hour"

RECONCILIATION CHECKS:
- "record_count": Count match between source and target. E.g., "source and target record counts must match"
- "one_to_one": One-to-one matching between datasets. E.g., "every source record must have exactly one target match"
- "field_level_recon": Field-level comparison between datasets. E.g., "customer and amount must match between systems"
- "aggregate_recon": Aggregate comparison between datasets. E.g., "sum of amounts must match between source and target"
- "tolerance_recon": Field comparison with tolerance. E.g., "amounts must match within $5 tolerance"
- "missing_extra": Find missing and extra records between datasets. E.g., "identify records in source missing from target"

BACKWARD COMPATIBILITY:
- "date_comparison": Same as "temporal_consistency" or "date_logic"
- "numeric_threshold": Same as "numeric_range"
- "conditional_rule": Same as "conditional_completeness"
- "arithmetic_comparison": Same as "formula_check"
- "unknown": Use ONLY if no other type fits
"""

SIR_JSON_SCHEMA = """{
  "schema_version": "1.0",
  "rule_type": "<one of the supported rule types>",
  "subject": {
    "raw_text": "<exact text from the user's input referring to the primary field or table>",
    "dataset_hint": "<if user mentions a specific table/dataset for this field, extract it here>",
    "matched_glossary_term_id": "<glossary term UUID if matched, else null>"
  },
  "operator": "<comparison operator or null>",
  "object": {
    "raw_text": "<secondary field, reference table, or value. null if not applicable>",
    "dataset_hint": "<if user mentions a reference table/dataset>",
    "matched_glossary_term_id": "<glossary term UUID if matched, else null>"
  },
  "scope": {
    "dataset_hint": "<dataset/table name if mentioned>",
    "domain_hint": "<business domain if mentioned>",
    "source_system_hint": "<source system if mentioned>"
  },
  "conditions": [
    {
      "field": {"raw_text": "<condition field text>", "matched_glossary_term_id": "<glossary term UUID if matched, else null>"},
      "operator": "<condition operator>",
      "value": "<condition value>"
    }
  ],
  "constraints": ["<value lists, ranges, patterns, thresholds, tolerance values, time windows, etc.>"],
  "check_dimension": "<MUST be one of: completeness|uniqueness|conformity|consistency|validity|accuracy|timeliness|reconciliation>",
  "check_subtype": "<MUST be one of the subtypes listed under the chosen dimension in the SUBTYPE INVENTORY below>",
  "subtype_config": {
    "<key>": "<EXHAUSTIVE config — populate every required field for the chosen subtype using snake_case keys exactly as listed in the SUBTYPE INVENTORY (e.g. min_value, max_value, allowed_values, pattern, scope_columns, comparison_column, …)>"
  },
  "check_config": {
    "check_dimension": "<same as top-level check_dimension>",
    "check_subtype": "<same as top-level check_subtype>",
    "config": {
      "<key>": "<MUST mirror subtype_config — keep this for backward compatibility>"
    },
    "thresholds": {
      "threshold_pass": 100,
      "threshold_warn": 95,
      "null_handling": "skip",
      "include_empty_strings": false
    }
  },
  "confidence": 0.0,
  "requires_disambiguation": false,
  "parse_warnings": [],
  "clarifying_questions": [
    {
      "field": "<dataset|column|check_dimension|check_subtype|<config_field_name>|threshold|reference|format|operator|...>",
      "question": "<human-readable question>",
      "options": ["<option1>", "<option2>"],
      "answer_type": "<single_select|multi_select|free_text|numeric>",
      "required": true,
      "rationale": "<one short sentence explaining why this question is being asked>"
    }
  ],
  "clarification_context": "<null on first parse. When re-asking after user answers, explain what you tried and why you need to ask again, e.g. 'I looked for dataset X but it does not exist in the workspace. Please choose from the available datasets.'>"
}"""

FEW_SHOT_EXAMPLES = """
Example 1 (completeness/null):
Input: "customer email must not be null"
Output:
{
  "schema_version": "1.0",
  "rule_type": "not_null",
  "subject": {"raw_text": "email", "dataset_hint": "customer"},
  "operator": "is_not_null",
  "object": null,
  "scope": {"dataset_hint": "customer", "domain_hint": null, "source_system_hint": null},
  "conditions": [],
  "constraints": [],
  "check_config": {
    "check_dimension": "completeness",
    "check_subtype": "null",
    "config": {"checkMode": "null", "columns": ["email"]},
    "thresholds": {"threshold_pass": 100, "threshold_warn": 95, "null_handling": "fail", "include_empty_strings": false}
  },
  "confidence": 0.95,
  "requires_disambiguation": false,
  "parse_warnings": [],
  "clarifying_questions": []
}

Example 2 (completeness/empty with threshold):
Input: "I want to check if customer_id is complete in customers_table. if customer_id completeness is less than 95% than you consider the column failed, include empty strings"
Output:
{
  "schema_version": "1.0",
  "rule_type": "empty_check",
  "subject": {"raw_text": "customer_id", "dataset_hint": "customers_table"},
  "operator": "is_not_null",
  "object": null,
  "scope": {"dataset_hint": "customers_table", "domain_hint": null, "source_system_hint": null},
  "conditions": [],
  "constraints": [95],
  "check_config": {
    "check_dimension": "completeness",
    "check_subtype": "empty",
    "config": {"checkMode": "empty", "columns": ["customer_id"]},
    "thresholds": {"threshold_pass": 95, "threshold_warn": 90, "null_handling": "fail", "include_empty_strings": true}
  },
  "confidence": 0.96,
  "requires_disambiguation": false,
  "parse_warnings": []
}

Example 3 (validity/allowed_values — no dataset specified):
Input: "Status must be one of OPEN, CLOSED, PENDING"
Output:
{
  "schema_version": "1.0",
  "rule_type": "value_in_list",
  "subject": {"raw_text": "Status"},
  "operator": "in",
  "object": null,
  "scope": {"dataset_hint": null, "domain_hint": null, "source_system_hint": null},
  "conditions": [],
  "constraints": ["OPEN", "CLOSED", "PENDING"],
  "check_config": {
    "check_dimension": "validity",
    "check_subtype": "allowed_values",
    "config": {"validationType": "allowed_values", "columns": ["Status"], "allowedValues": ["OPEN", "CLOSED", "PENDING"]},
    "thresholds": {"threshold_pass": 100, "threshold_warn": 95, "null_handling": "skip", "include_empty_strings": false}
  },
  "confidence": 0.85,
  "requires_disambiguation": true,
  "parse_warnings": ["No dataset specified for column 'Status'"],
  "clarifying_questions": [
    {"field": "dataset", "question": "Which dataset or table does the 'Status' column belong to?", "options": [], "required": true}
  ]
}

Example 4 (consistency/formula):
Input: "line_total must equal quantity * unit_price"
Output:
{
  "schema_version": "1.0",
  "rule_type": "formula_check",
  "subject": {"raw_text": "line_total"},
  "operator": "equals",
  "object": null,
  "scope": {"dataset_hint": null, "domain_hint": null, "source_system_hint": null},
  "conditions": [],
  "constraints": ["quantity", "unit_price"],
  "check_config": {
    "check_dimension": "consistency",
    "check_subtype": "formula",
    "config": {"consistencyType": "formula", "columns": ["line_total"], "ruleExpression": "\\"quantity\\" * \\"unit_price\\""},
    "thresholds": {"threshold_pass": 100, "threshold_warn": 95, "null_handling": "fail", "include_empty_strings": false}
  },
  "confidence": 0.93,
  "requires_disambiguation": false,
  "parse_warnings": []
}

Example 5 (uniqueness/scoped):
Input: "order_id must be unique within each region"
Output:
{
  "schema_version": "1.0",
  "rule_type": "scoped_uniqueness",
  "subject": {"raw_text": "order_id"},
  "operator": null,
  "object": {"raw_text": "region"},
  "scope": {"dataset_hint": null, "domain_hint": null, "source_system_hint": null},
  "conditions": [],
  "constraints": [],
  "check_config": {
    "check_dimension": "uniqueness",
    "check_subtype": "scoped",
    "config": {"uniquenessMode": "scoped", "columns": ["order_id"], "scopeColumns": ["region"]},
    "thresholds": {"threshold_pass": 100, "threshold_warn": 95, "null_handling": "skip", "include_empty_strings": false}
  },
  "confidence": 0.94,
  "requires_disambiguation": false,
  "parse_warnings": []
}

Example 6 (timeliness/record_age):
Input: "records must not be older than 30 days"
Output:
{
  "schema_version": "1.0",
  "rule_type": "record_age",
  "subject": {"raw_text": "records"},
  "operator": "less_than_or_equal",
  "object": null,
  "scope": {"dataset_hint": null, "domain_hint": null, "source_system_hint": null},
  "conditions": [],
  "constraints": [30, "days"],
  "check_config": {
    "check_dimension": "timeliness",
    "check_subtype": "record_age",
    "config": {"timelinessType": "record_age", "timestampColumn": "updated_at", "maxAgeValue": 30, "maxAgeUnit": "days"},
    "thresholds": {"threshold_pass": 100, "threshold_warn": 95, "null_handling": "skip", "include_empty_strings": false}
  },
  "confidence": 0.88,
  "requires_disambiguation": true,
  "parse_warnings": ["Timestamp column not specified — defaulting to updated_at. Please confirm."],
  "clarifying_questions": [
    {"field": "timestamp_column", "question": "Which column should be used as the timestamp for the age check?", "options": ["updated_at", "created_at"], "required": true},
    {"field": "dataset", "question": "Which dataset or table does this rule apply to?", "options": [], "required": true}
  ]
}

Example 7 (reconciliation/record_count):
Input: "source and target record counts must match"
Output:
{
  "schema_version": "1.0",
  "rule_type": "record_count",
  "subject": {"raw_text": "source"},
  "operator": "equals",
  "object": {"raw_text": "target"},
  "scope": {"dataset_hint": null, "domain_hint": null, "source_system_hint": null},
  "conditions": [],
  "constraints": [],
  "check_config": {
    "check_dimension": "reconciliation",
    "check_subtype": "record_count",
    "config": {"reconciliationType": "record_count", "sourceDataset": "source", "targetDataset": "target"},
    "thresholds": {"threshold_pass": 100, "threshold_warn": 95, "null_handling": "skip", "include_empty_strings": false}
  },
  "confidence": 0.90,
  "requires_disambiguation": true,
  "parse_warnings": ["Source and target datasets need to be specified"],
  "clarifying_questions": [
    {"field": "source_dataset", "question": "Which dataset or table is the source?", "options": [], "required": true},
    {"field": "target_dataset", "question": "Which dataset or table is the target?", "options": [], "required": true}
  ]
}

Example 8 (accuracy/tolerated_deviation):
Input: "salary must be within 1000 of HR system value"
Output:
{
  "schema_version": "1.0",
  "rule_type": "tolerated_deviation",
  "subject": {"raw_text": "salary"},
  "operator": "within_tolerance",
  "object": {"raw_text": "HR system"},
  "scope": {"dataset_hint": null, "domain_hint": null, "source_system_hint": null},
  "conditions": [],
  "constraints": [1000],
  "check_config": {
    "check_dimension": "accuracy",
    "check_subtype": "tolerated_deviation",
    "config": {"accuracyType": "tolerated_deviation", "columns": ["salary"], "referenceDataset": "HR system", "toleranceType": "absolute", "toleranceValue": 1000},
    "thresholds": {"threshold_pass": 100, "threshold_warn": 95, "null_handling": "skip", "include_empty_strings": false}
  },
  "confidence": 0.91,
  "requires_disambiguation": true,
  "parse_warnings": ["Reference dataset needs to be resolved"],
  "clarifying_questions": [
    {"field": "reference_dataset", "question": "Which dataset or table contains the reference HR system values?", "options": [], "required": true}
  ]
}
"""


def build_parse_prompt(rule_text: str, context: dict | None = None) -> str:
    """Build the constrained LLM prompt for parsing a natural language rule.

    Args:
        rule_text: The user's natural language rule text.
        context: Optional context (dataset_id, domain, source_system, etc.).

    Returns:
        The complete prompt string for the LLM.
    """
    context_section = ""
    clarification_section = ""
    glossary_section = ""
    selected_dataset_section = ""
    if context:
        parts = []
        if context.get("dataset_id"):
            parts.append(f"Dataset context: {context['dataset_id']}")
        if context.get("dataset_name"):
            parts.append(f"Dataset name: {context['dataset_name']}")
        if context.get("domain"):
            parts.append(f"Domain: {context['domain']}")
        if context.get("source_system"):
            parts.append(f"Source system: {context['source_system']}")
        if context.get("rule_category"):
            parts.append(f"Category: {context['rule_category']}")
        if context.get("available_columns"):
            parts.append(f"Available columns in dataset: {', '.join(context['available_columns'])}")
        if context.get("available_datasets"):
            parts.append(
                f"Available datasets in workspace: {', '.join(context['available_datasets'])}"
            )
        if parts:
            context_section = "\nAdditional context provided by the user:\n" + "\n".join(
                f"- {p}" for p in parts
            )

        # Spec §4.1 — when a dataset is selected, attach its full schema as
        # authoritative grounding context. The LLM MUST treat columns outside
        # this list as unknown.
        if context.get("selected_dataset_block"):
            selected_dataset_section = (
                "\n\n=== SELECTED DATASET METADATA (authoritative — do not invent columns) ===\n"
                + context["selected_dataset_block"]
                + "\n\nRules:\n"
                + "- ONLY use columns from the list above. If the user mentions a column "
                "that is not in this list, set requires_disambiguation=true and ask the "
                "user to confirm or pick one of the listed columns.\n"
                + "- Use each column's data type to validate the requested check. If the "
                "check is not compatible with the data type (e.g. greater_than on a "
                "string column), set requires_disambiguation=true and add a "
                "parse_warning explaining the type incompatibility.\n"
                + "=== END OF SELECTED DATASET METADATA ===\n"
            )

        if context.get("glossary_section"):
            glossary_section = f"\n\n{context['glossary_section']}"

        # Build a separate, prominent clarification section
        # F1 — render multi-turn history (older Q/A turns) before the latest answers
        history_block = ""
        if context.get("clarification_history"):
            turns = context["clarification_history"]
            if turns:
                turn_lines = []
                for i, t in enumerate(turns, start=1):
                    turn_lines.append(
                        f"  Turn {i} — field={t.get('field', 'general')!s}\n"
                        f"    Q: {t.get('question', '')}\n"
                        f"    A: {t.get('answer', '')}"
                    )
                history_block = (
                    "\n\n=== PRIOR CLARIFICATION TURNS (oldest first) ===\n"
                    + "\n".join(turn_lines)
                    + "\nUse this history to AVOID repeating questions whose answers are already on record. "
                    + "If a prior answer was invalid, reflect that in clarification_context and ask a REFINED follow-up.\n"
                    + "=== END OF PRIOR TURNS ===\n"
                )

        if context.get("clarification_answers"):
            answers = context["clarification_answers"]
            answer_lines = [f"  {k} = {v}" for k, v in answers.items()]
            available_ds = context.get("available_datasets", [])
            ds_list = (
                f"\nAvailable datasets in workspace: {', '.join(available_ds)}"
                if available_ds
                else ""
            )
            clarification_section = f"""{history_block}

=== USER HAS ANSWERED YOUR PREVIOUS QUESTIONS ===
The user was previously asked clarifying questions and has provided these answers.

Answers:
{chr(10).join(answer_lines)}
{ds_list}

INSTRUCTIONS FOR HANDLING ANSWERS:
- Validate each answer against available data. For example, if the user said dataset="xyz" but "xyz" is NOT in the available datasets list above, the answer is INVALID.
- If ALL answers are valid: use them to fill in the missing info, set clarifying_questions to [], set clarification_context to null, and increase confidence.
- If ANY answer is invalid or still ambiguous: set clarification_context to a message explaining what you tried and what went wrong (e.g. "I tried using dataset 'xyz' but it does not exist in the workspace. Please choose from the available datasets."). Then ask REFINED follow-up questions with better options (e.g. populate the options array with the actual available datasets). Do NOT just repeat the same question — improve it.
- You may ask about the SAME field again if the previous answer was invalid, but the question text must be different and explain why the previous answer did not work.
- Consider any PRIOR CLARIFICATION TURNS shown above as already-resolved unless the user contradicts them.
- The user may submit only a subset of answers (partial accept). For any field listed in your previous clarifying_questions that is NOT present in the Answers above and NOT already resolved by a prior turn, you MUST keep it (or a refined variant) in clarifying_questions.
=== END OF ANSWERS ==="""
        elif history_block:
            # No new answers in this turn but a prior history is available — still surface it.
            clarification_section = history_block

    return f"""You are a data quality rule parser. Your task is to parse a natural language data quality rule into a structured JSON representation that maps to executable check node configurations.

CRITICAL RULES:
1. You MUST output ONLY valid JSON matching the schema below. No text before or after.
2. You MUST NOT produce SQL, code, or any executable logic.
3. You MUST use EXACTLY one of the supported rule types listed below.
4. If you cannot confidently interpret the input, set rule_type to "unknown" and confidence to a low value.
5. When the user writes "TableName columnName" (e.g., "customer email"), split it: raw_text should be just the column name ("email") and dataset_hint should be the table name ("customer"). Do NOT merge table and column names into raw_text.
6. Set confidence between 0.0 and 1.0 based on how clear the rule intent is.
7. Set requires_disambiguation to true if confidence is below 0.7 or the rule is ambiguous.
8. Add parse_warnings for any ambiguity or missing information.
9. ALWAYS include the check_config object with the correct check_dimension, check_subtype, and config.
10. If the user specifies a threshold (e.g., "less than 95%"), set threshold_pass accordingly.
11. If the user says "include empty strings", set include_empty_strings to true and use check_subtype "empty".
12. If the user mentions a specific table/dataset, extract it into scope.dataset_hint and subject.dataset_hint.
13. IMPORTANT: When you are uncertain about ANY aspect of the rule (which dataset/table, which column, what check type, what threshold, what reference, etc.), you MUST add specific clarifying_questions. Each question must have a "field" (what it's about), a "question" (human-readable), an "answer_type" (one of "single_select", "multi_select", "free_text", "numeric"), optional "options" (required when answer_type is single_select or multi_select), optional "min_value"/"max_value" (for numeric answers), and optional "rationale" (one short sentence explaining why you are asking). Common cases requiring questions:
    - No dataset/table mentioned → ask which dataset the column belongs to (single_select with available datasets if known, else free_text)
    - Ambiguous column name → ask to clarify which column (single_select)
    - Multiple possible check types → ask which type the user means (single_select)
    - Missing reference table for lookups/reconciliation → ask for the reference (single_select or free_text)
    - No threshold specified when relevant → ask what threshold to use (numeric, with min_value/max_value)
    - Multi-column requirement (e.g. which columns must be unique) → multi_select
    - Timestamp column not specified for timeliness checks → ask which column (single_select)
14. If the user has provided clarification answers (see ANSWERS section below), validate them against available data first. If valid, use them and clear all questions. If invalid (e.g., dataset not found), explain what went wrong in clarification_context and ask improved follow-up questions with better options.
15. If BUSINESS GLOSSARY terms are provided below, treat them as governed semantic hints. Prefer glossary-backed interpretations over raw string guessing. When a term match is clear, set matched_glossary_term_id on subject/object/condition field.

COMPOUND RULE DECOMPOSITION (F126):
16. If the input contains multiple distinct obligations joined by AND, semicolons, or independent comma-separated clauses for DIFFERENT columns or check types, set is_compound=true, set obligation_logic to "AND", "OR", or "INDEPENDENT", and populate the obligations array with one partial SIR per obligation. Each obligation follows the same JSON schema as the top-level SIR.
17. OR between values for the SAME column (e.g., "status must be Active OR Inactive") is NOT compound — treat as a single value_in_list obligation with is_compound=false.
18. OR between DIFFERENT columns or different rule types IS compound — set is_compound=true with obligation_logic="OR".
19. IF-THEN conditional rules are single obligations with is_compound=false; populate conditions instead.
20. IF-THEN-ELSE rules produce is_compound=true with 2 obligations: one for the THEN branch and one for the ELSE branch (with the condition negated). Set obligation_logic="INDEPENDENT".
21. Maximum 10 obligations allowed. If more would result, set is_compound=false and add a parse_warning.

INLINE PARAMETER EXTRACTION (F126):
22. If the rule contains natural-language threshold phrasing (e.g., "at least 95%", "pass rate of 90%", "no more than 5 failures"), set threshold_pass (as a percentage 0–100) at the top level of the JSON output.
23. If the rule contains an allowed-values list (e.g., "must be one of X, Y, Z" or "valid values are X, Y, Z"), set allowed_values as a top-level array.
24. If the rule references a lookup or reference table (e.g., "must exist in customers", "foreign key to orders"), set reference_dataset as a top-level string.
25. If the rule explicitly states a severity (e.g., "with severity critical", "severity high"), set severity (or inline_severity) as a top-level string. Supported values: critical, high, medium, low, info.
26. For natural-language operators (e.g., "at least", "no more than", "greater than", "after", "before"), use the closest SQL operator in the operator field. These are normalized via OPERATOR_ALIASES downstream.

CHECK SUBTYPE CAPTURE (CRITICAL — required for executable flow generation):
27. You MUST emit BOTH top-level `check_dimension` and top-level `check_subtype` fields. Their values MUST appear in the SUBTYPE INVENTORY below. Never invent a new dimension or subtype name.
28. You MUST also populate top-level `subtype_config` with EVERY required field for the chosen subtype, using the exact snake_case keys listed in the inventory. Do not omit required keys — if you do not know a value, prefer asking a clarifying question over leaving it out.
29. When the rule text could plausibly map to MORE THAN ONE subtype within the same dimension (e.g. "name must not be empty" → completeness/null vs completeness/empty vs completeness/placeholder; "amount must be positive" → validity/range vs validity/business_rule), DO NOT silently pick one. Add a clarifying question with `field="check_subtype"`, `answer_type="single_select"`, `options=<list of candidate subtypes>`, and a clear `rationale` explaining what each candidate would do. Lower the confidence accordingly and set requires_disambiguation=true.
30. When the chosen subtype has REQUIRED config fields whose values you cannot extract from the rule text (e.g. validity/regex needs a pattern, validity/range needs at least one of min_value/max_value, uniqueness/scoped needs scope_columns, timeliness/freshness needs timestamp_column + max_age_value + max_age_unit), DO NOT fabricate values. Add ONE clarifying question per missing required field, using `field=<config_field_name>`, the correct `answer_type` ("numeric" for numbers, "single_select" for enums with their `options` populated from the inventory, "free_text" otherwise), and a `rationale`. Mark each question as required.
31. Mirror `subtype_config` into `check_config.config` for backward compatibility with downstream consumers; keep `check_config.check_dimension` and `check_config.check_subtype` aligned with the top-level values.
32. The valid subtypes per dimension and their required configuration fields are listed in the SUBTYPE INVENTORY block below — treat it as the source of truth.

SUBTYPE INVENTORY (canonical dimensions, subtypes, and required config fields):
{SUBTYPE_INVENTORY_TEXT}

{RULE_TYPE_DESCRIPTIONS}

OUTPUT JSON SCHEMA:
{SIR_JSON_SCHEMA}

EXAMPLES:
{FEW_SHOT_EXAMPLES}

---
{context_section}
{selected_dataset_section}
{glossary_section}
{clarification_section}

USER RULE TEXT (parse this):
\"\"\"{rule_text}\"\"\"

Output ONLY the JSON object:"""


# NL variation normalization map — extended for all check types
NL_VARIATIONS = {
    # Completeness
    "must not be empty": "not_null",
    "should not be empty": "not_null",
    "cannot be empty": "not_null",
    "must not be blank": "not_null",
    "should not be blank": "not_null",
    "cannot be blank": "not_null",
    "must not be null": "not_null",
    "should not be null": "not_null",
    "cannot be null": "not_null",
    "is required": "not_null",
    "is mandatory": "not_null",
    "must be complete": "population_completeness",
    "completeness": "population_completeness",
    "must be null": "null_check",
    "should be empty": "null_check",
    "must be empty": "null_check",
    "no placeholder": "placeholder_check",
    "not n/a": "placeholder_check",
    "not tbd": "placeholder_check",
    "either": "multi_field_completeness",
    # Uniqueness
    "must be unique": "uniqueness",
    "should be unique": "uniqueness",
    "cannot have duplicates": "uniqueness",
    "no duplicates": "uniqueness",
    "unique together": "composite_uniqueness",
    "unique within": "scoped_uniqueness",
    "unique per": "scoped_uniqueness",
    "near-duplicate": "fuzzy_uniqueness",
    "similar to": "fuzzy_uniqueness",
    # Conformity
    "must match pattern": "regex_format",
    "must match format": "regex_format",
    "characters long": "length_check",
    "must be uppercase": "case_check",
    "must be lowercase": "case_check",
    "letters only": "charset_check",
    "alpha only": "charset_check",
    "valid email": "standard_format",
    "valid phone": "standard_format",
    "follow pattern": "structural_pattern",
    # Consistency
    "must be after": "column_comparison",
    "must be before": "column_comparison",
    "must equal": "formula_check",
    "must be consistent": "inter_record",
    "sum of": "aggregation_consistency",
    # Validity
    "must be one of": "value_in_list",
    "allowed values": "value_in_list",
    "between": "numeric_range",
    "must be positive": "numeric_range",
    "must exist in": "reference_lookup",
    "must be found in": "reference_lookup",
    "must belong to": "reference_lookup",
    "must not start with": "negative_pattern",
    "must not contain": "negative_pattern",
    # Accuracy
    "must match reference": "reference_comparison",
    "within tolerance": "tolerated_deviation",
    "outlier": "statistical_outlier",
    # Timeliness
    "freshness": "freshness",
    "updated within": "freshness",
    "older than": "record_age",
    "latency": "latency",
    "processing time": "processing_delay",
    "delivery window": "delivery_window",
    "heartbeat": "heartbeat",
    # Reconciliation
    "counts must match": "record_count",
    "record count": "record_count",
    "one to one": "one_to_one",
    "field level": "field_level_recon",
    "missing from": "missing_extra",
}


def detect_rule_type_hint(rule_text: str) -> str | None:
    """Detect a rule type hint from common NL phrases.

    Returns the detected rule type string or None.
    """
    lower = rule_text.lower().strip()
    for phrase, rule_type in NL_VARIATIONS.items():
        if phrase in lower:
            return rule_type
    return None
