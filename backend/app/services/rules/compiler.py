"""
Rule Compiler Service
Compiles canonical rule definitions into executable SQL and Spark code.
"""

import re
from typing import Any

from app.schemas.rule import RuleCategory


class RuleCompiler:
    """
    Compiles canonical rule definitions into database-specific SQL and Spark code.
    """

    def compile_rule(
        self,
        canonical_rule: dict[str, Any],
        target_schema: str | None = None,
        target_table: str | None = None,
        target_columns: list[str] | None = None,
    ) -> dict[str, str]:
        """
        Compile canonical rule into multiple formats.

        Args:
            canonical_rule: Canonical rule definition with keys: dimension, entity, condition, expectation, parameters
            target_schema: Target schema name (optional, can be extracted from entity)
            target_table: Target table name (optional, can be extracted from entity)
            target_columns: Target column names (optional)

        Returns:
            Dictionary with compiled SQL variants and Spark code
        """
        dimension = canonical_rule.get("dimension")
        entity = canonical_rule.get("entity")
        condition = canonical_rule.get("condition")
        expectation = canonical_rule.get("expectation")
        parameters = canonical_rule.get("parameters", {})

        # Parse entity to get table and column
        if "." in entity:
            table, column = entity.split(".", 1)
        else:
            table = entity
            column = target_columns[0] if target_columns else "*"

        # Use provided schema/table/column or extract from entity
        schema = target_schema or ""
        table = target_table or table
        # If target_columns provided, use the first one as the column name (override entity-parsed column)
        if target_columns:
            column = target_columns[0]
        full_table = f'"{schema}"."{table}"' if schema else f'"{table}"'

        # Compile based on dimension and condition type
        compiled = {}

        if dimension == "completeness":
            compiled = self._compile_completeness_rule(
                full_table, column, condition, expectation, parameters
            )
        elif dimension == "validity":
            compiled = self._compile_validity_rule(
                full_table, column, condition, expectation, parameters
            )
        elif dimension == "uniqueness":
            compiled = self._compile_uniqueness_rule(
                full_table, column, condition, expectation, parameters
            )
        elif dimension == "conformity":
            compiled = self._compile_conformity_rule(
                full_table, column, condition, expectation, parameters
            )
        elif dimension == "consistency":
            compiled = self._compile_consistency_rule(
                full_table, column, condition, expectation, parameters
            )
        elif dimension == "timeliness":
            compiled = self._compile_timeliness_rule(
                full_table, column, condition, expectation, parameters
            )
        elif dimension == "accuracy":
            compiled = self._compile_accuracy_rule(
                full_table, column, condition, expectation, parameters
            )
        elif dimension == "reconciliation":
            compiled = self._compile_reconciliation_rule(
                full_table, column, condition, expectation, parameters
            )
        elif dimension == "statistical":
            compiled = self._compile_statistical_rule(
                full_table, column, condition, expectation, parameters
            )
        else:
            # Generic compilation
            compiled = self._compile_generic_rule(
                full_table, column, condition, expectation, parameters
            )

        return compiled

    def compile_rule_for_spark(
        self,
        canonical_rule: dict[str, Any],
        target_schema: str | None = None,
        target_table: str | None = None,
        target_columns: list[str] | None = None,
    ) -> str:
        """
        Compile canonical rule to Spark SQL (ANSI SQL compatible).

        Args:
            canonical_rule: Canonical rule definition
            target_schema: Target schema name
            target_table: Target table name
            target_columns: Target column names

        Returns:
            Spark SQL query string
        """
        # First compile to all formats
        compiled = self.compile_rule(canonical_rule, target_schema, target_table, target_columns)

        # Return Spark-compatible SQL (use postgresql as base, it's ANSI compatible)
        spark_sql = compiled.get("compiled_postgres", compiled.get("compiled_sql", ""))

        # Make Spark-specific adjustments if needed
        spark_sql = self._adjust_for_spark_sql(spark_sql)

        return spark_sql

    def _adjust_for_spark_sql(self, sql: str) -> str:
        """
        Adjust SQL to be Spark SQL compatible.

        Args:
            sql: Original SQL query

        Returns:
            Spark SQL compatible query
        """
        import re

        # Replace table identifiers like "schema"."table" with schema.table
        sql = re.sub(r'"(\w+)"\."(\w+)"', r"\1.\2", sql)

        # Replace single-part table names in FROM clauses: FROM "table" -> FROM table
        sql = re.sub(r'FROM\s+"(\w+)"', r"FROM \1", sql, flags=re.IGNORECASE)

        # Replace column identifiers like "column" with column (if not in string context)
        sql = re.sub(r"([^\'])\"(\w+)\"", r"\1\2", sql)

        # ── PostgreSQL regex operators → Spark RLIKE ──────────────────────────
        # Must be ordered: !~ before ~* before ~ to avoid partial matches.
        #
        # 1. col !~ 'pat'  →  col NOT RLIKE 'pat'  (negative case-sensitive)
        sql = re.sub(r"!~", " NOT RLIKE ", sql)
        # 2. col ~* 'pat'  →  col RLIKE '(?i)pat'  (positive case-insensitive)
        #    Embed the (?i) flag directly in the pattern string.
        sql = re.sub(r"~\*\s*'([^']*)'", lambda m: f"RLIKE '(?i){m.group(1)}'", sql)
        # 3. col ~ 'pat'   →  col RLIKE 'pat'       (positive case-sensitive)
        #    Negative lookbehind avoids re-matching RLIKE already written above.
        sql = re.sub(r"(?<![A-Za-z])~(?!\*)", " RLIKE ", sql)

        return sql

    # --- F084: Completeness check mode constants and helpers ---

    VALID_CHECK_MODES = {
        "null",
        "empty",
        "placeholder",
        "conditional",
        "multi_field",
        "population",
        "group",
    }

    # Tokens permitted inside a filter expression / formula. Anything that does
    # not tokenize cleanly (comment markers, semicolons, backslashes, backticks,
    # unterminated quotes, ...) is rejected outright.
    _FILTER_TOKEN = re.compile(
        r"""
          \s+                              # whitespace
        | ''                               # empty / escaped string literal remnant
        | "[A-Za-z_][A-Za-z0-9_ ]*"        # double-quoted identifier
        | \[[A-Za-z_][A-Za-z0-9_ ]*\]      # bracket-quoted identifier (MSSQL)
        | \d+(?:\.\d+)?                    # numeric literal
        | [A-Za-z_][A-Za-z0-9_$]*          # bare identifier / keyword
        | !~\*? | ~\*?                     # PostgreSQL regex operators
        | \|\| | ::                        # string concat, type cast
        | <> | != | <= | >= | = | < | >
        | [(),.]
        | [+\-*/%]
        """,
        re.VERBOSE,
    )

    # Words that must never appear (outside string literals) in a filter
    # expression. Combined with strict tokenization, comment/semicolon
    # rejection and parenthesis balancing, this prevents statement injection,
    # subquery-based exfiltration and time-based probing while still allowing
    # ordinary predicates (AND/OR/NOT, IN, BETWEEN, LIKE, IS NULL, CASE WHEN,
    # arithmetic, function calls such as EXTRACT(YEAR FROM col)).
    _FILTER_FORBIDDEN_WORDS = frozenset(
        {
            "select",
            "insert",
            "update",
            "delete",
            "drop",
            "alter",
            "create",
            "truncate",
            "merge",
            "grant",
            "revoke",
            "exec",
            "execute",
            "call",
            "copy",
            "vacuum",
            "union",
            "into",
            "returning",
            "sleep",
            "pg_sleep",
            "benchmark",
            "waitfor",
            "load_file",
            "outfile",
            "dumpfile",
            "information_schema",
            "pg_catalog",
            "sysobjects",
            "xp_cmdshell",
        }
    )

    def _validate_filter_expression(self, expr: str) -> bool:
        """Validate a user-supplied filter expression before SQL interpolation.

        Strict allowlist approach: the expression must tokenize completely
        into known-safe tokens, contain no comment markers / semicolons, keep
        parentheses balanced (never closing more than were opened), and use no
        forbidden statement keywords outside string literals.
        """
        if not expr or len(expr) > 2000:
            return False

        # Blank out string literal contents ('' is the SQL escape for a quote)
        # so they are not inspected; a leftover quote means an unterminated
        # string literal.
        stripped = re.sub(r"'(?:[^']|'')*'", "''", expr)
        if "'" in stripped.replace("''", ""):
            return False

        # Comment markers, statement separators and escape characters.
        if re.search(r"--|/\*|\*/|#|;|\\|`", stripped):
            return False

        # Parentheses must balance and never close the enclosing context.
        depth = 0
        for ch in stripped:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    return False
        if depth != 0:
            return False

        # Strict tokenization: reject anything that is not an allowed token.
        pos = 0
        while pos < len(stripped):
            match = self._FILTER_TOKEN.match(stripped, pos)
            if not match:
                return False
            token = match.group(0)
            if token.lower() in self._FILTER_FORBIDDEN_WORDS:
                return False
            pos = match.end()
        return True

    def _build_where_clause(
        self, filter_expression: str | None = None, existing_where: str | None = None
    ) -> str:
        """Build WHERE clause combining filter_expression with mode-specific conditions."""
        clauses = []
        if filter_expression:
            clauses.append(f"({filter_expression})")
        if existing_where:
            clauses.append(f"({existing_where})")
        if not clauses:
            return ""
        return "WHERE " + " AND ".join(clauses)

    def _format_placeholder_list(self, placeholders: list[str]) -> str:
        """Format placeholder values as a SQL IN-list. Safe: single-quoted literals only."""
        sanitized = []
        for p in placeholders:
            cleaned = p.strip().lower().replace("'", "''")
            sanitized.append(f"'{cleaned}'")
        return ", ".join(sanitized)

    def _completeness_error_result(self, message: str) -> dict[str, Any]:
        """Return an error result dict for completeness compilation failures."""
        return {
            "compiled_sql": "",
            "compiled_postgres": "",
            "compiled_mysql": "",
            "compiled_snowflake": "",
            "compiled_spark": "",
            "violation_sql": "",
            "error": True,
            "error_message": message,
        }

    def _compile_completeness_rule(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Compile completeness rule — dispatches to per-mode helper based on check_mode."""
        check_mode = parameters.get("check_mode", "null")

        # Validate check_mode
        if check_mode not in self.VALID_CHECK_MODES:
            return self._completeness_error_result(
                f"Invalid check_mode '{check_mode}'. Allowed: {', '.join(sorted(self.VALID_CHECK_MODES))}"
            )

        # Validate filter_expression if present
        filter_expression = parameters.get("filter_expression")
        if filter_expression and not self._validate_filter_expression(filter_expression):
            return self._completeness_error_result(
                "Filter expression contains forbidden SQL constructs"
            )

        # Dispatch to per-mode helper
        if check_mode == "null":
            return self._completeness_null(table, column, parameters)
        elif check_mode == "empty":
            return self._completeness_empty(table, column, parameters)
        elif check_mode == "placeholder":
            return self._completeness_placeholder(table, column, parameters)
        elif check_mode == "conditional":
            return self._completeness_conditional(table, column, parameters)
        elif check_mode == "multi_field":
            return self._completeness_multi_field(table, column, parameters)
        elif check_mode == "population":
            # Population reuses null SQL — threshold distinction handled at result parsing
            return self._completeness_null(table, column, parameters)
        elif check_mode == "group":
            return self._completeness_group(table, column, parameters)
        else:
            return self._completeness_error_result(f"Unhandled check_mode '{check_mode}'")

    def _completeness_null(
        self, table: str, column: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Compile null-mode completeness check (backward-compatible default)."""
        filter_expression = parameters.get("filter_expression")
        include_empty = parameters.get("include_empty_strings", False)
        columns = parameters.get("columns", [])

        # Multi-column null check (existing behavior preserved for backward compat)
        if len(columns) > 1 and not include_empty:
            not_null_cond = " AND ".join(f'"{col}" IS NOT NULL' for col in columns)
            null_cond = " OR ".join(f'"{col}" IS NULL' for col in columns)
            where = self._build_where_clause(filter_expression)
            sql = f"""
        SELECT
            COUNT(*) as total_rows,
            COUNT(CASE WHEN {not_null_cond} THEN 1 END) as non_null_rows,
            COUNT(CASE WHEN {null_cond} THEN 1 END) as null_rows,
            ROUND(100.0 * COUNT(CASE WHEN {not_null_cond} THEN 1 END) / NULLIF(COUNT(*), 0), 2) as completeness_rate
        FROM {table}
        {where}"""
            violation_where = self._build_where_clause(filter_expression, null_cond)
            violation_sql = f"""
        SELECT *
        FROM {table}
        {violation_where}"""
        elif include_empty:
            # include_empty_strings in null mode → also detect empty/whitespace
            where = self._build_where_clause(filter_expression)
            sql = f"""
        SELECT
            COUNT(*) as total_rows,
            COUNT(CASE WHEN "{column}" IS NOT NULL AND TRIM("{column}") != '' THEN 1 END) as non_null_rows,
            COUNT(CASE WHEN "{column}" IS NULL OR TRIM("{column}") = '' THEN 1 END) as null_rows,
            ROUND(100.0 * COUNT(CASE WHEN "{column}" IS NOT NULL AND TRIM("{column}") != '' THEN 1 END) / NULLIF(COUNT(*), 0), 2) as completeness_rate
        FROM {table}
        {where}"""
            null_cond = f'"{column}" IS NULL OR TRIM("{column}") = \'\''
            violation_where = self._build_where_clause(filter_expression, null_cond)
            violation_sql = f"""
        SELECT *
        FROM {table}
        {violation_where}"""
        else:
            # Single column null check (default, backward compatible)
            # population mode arrives here with column='*' — use COUNT(*) to count all rows
            where = self._build_where_clause(filter_expression)
            if column == "*":
                sql = f"""
        SELECT 
            COUNT(*) as total_rows,
            COUNT(*) as non_null_rows,
            0 as null_rows,
            100.00 as completeness_rate
        FROM {table}
        {where}"""
                violation_sql = f"""
        SELECT *
        FROM {table}
        WHERE 1=0"""
            else:
                sql = f"""
        SELECT 
            COUNT(*) as total_rows,
            COUNT("{column}") as non_null_rows,
            COUNT(*) - COUNT("{column}") as null_rows,
            ROUND(100.0 * COUNT("{column}") / NULLIF(COUNT(*), 0), 2) as completeness_rate
        FROM {table}
        {where}"""
                violation_where = self._build_where_clause(filter_expression, f'"{column}" IS NULL')
                violation_sql = f"""
        SELECT *
        FROM {table}
        {violation_where}"""

        # Spark code
        if column == "*":
            spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
total_rows = df.count()
non_null_rows = total_rows
null_rows = 0
completeness_rate = 100.0 if total_rows > 0 else 0

result = {{
    "total_rows": total_rows,
    "non_null_rows": non_null_rows,
    "null_rows": null_rows,
    "completeness_rate": completeness_rate
}}
violations_df = df.filter(F.lit(False))
        """
        else:
            spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
total_rows = df.count()
non_null_rows = df.filter(F.col("{column}").isNotNull()).count()
null_rows = total_rows - non_null_rows
completeness_rate = (non_null_rows / total_rows * 100) if total_rows > 0 else 0

result = {{
    "total_rows": total_rows,
    "non_null_rows": non_null_rows,
    "null_rows": null_rows,
    "completeness_rate": completeness_rate
}}

# Get violations
violations_df = df.filter(F.col("{column}").isNull())
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql.replace("NULLIF", "IFNULL"),
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _completeness_empty(
        self, table: str, column: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Compile empty-mode completeness (NULL + empty string + whitespace)."""
        filter_expression = parameters.get("filter_expression")
        where = self._build_where_clause(filter_expression)

        sql = f"""
        SELECT
            COUNT(*) as total_rows,
            COUNT(CASE WHEN "{column}" IS NOT NULL AND TRIM("{column}") != '' THEN 1 END) as non_null_rows,
            COUNT(CASE WHEN "{column}" IS NULL OR TRIM("{column}") = '' THEN 1 END) as null_rows,
            ROUND(100.0 * COUNT(CASE WHEN "{column}" IS NOT NULL AND TRIM("{column}") != '' THEN 1 END) / NULLIF(COUNT(*), 0), 2) as completeness_rate
        FROM {table}
        {where}"""

        null_cond = f'"{column}" IS NULL OR TRIM("{column}") = \'\''
        violation_where = self._build_where_clause(filter_expression, null_cond)
        violation_sql = f"""
        SELECT *
        FROM {table}
        {violation_where}"""

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
total_rows = df.count()
non_null_rows = df.filter(F.col("{column}").isNotNull() & (F.trim(F.col("{column}")) != "")).count()
null_rows = total_rows - non_null_rows
completeness_rate = (non_null_rows / total_rows * 100) if total_rows > 0 else 0

violations_df = df.filter(F.col("{column}").isNull() | (F.trim(F.col("{column}")) == ""))
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql.replace("NULLIF", "IFNULL"),
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _completeness_placeholder(
        self, table: str, column: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Compile placeholder-mode completeness (NULL + empty + placeholder values)."""
        filter_expression = parameters.get("filter_expression")
        placeholders = parameters.get("placeholder_values", [])
        where = self._build_where_clause(filter_expression)

        if placeholders:
            placeholder_list = self._format_placeholder_list(placeholders)
            pass_cond = f'"{column}" IS NOT NULL AND TRIM("{column}") != \'\' AND LOWER(TRIM("{column}")) NOT IN ({placeholder_list})'
            fail_cond = f'"{column}" IS NULL OR TRIM("{column}") = \'\' OR LOWER(TRIM("{column}")) IN ({placeholder_list})'
        else:
            # Empty placeholder list → same as empty mode
            pass_cond = f'"{column}" IS NOT NULL AND TRIM("{column}") != \'\''
            fail_cond = f'"{column}" IS NULL OR TRIM("{column}") = \'\''

        sql = f"""
        SELECT
            COUNT(*) as total_rows,
            COUNT(CASE WHEN {pass_cond} THEN 1 END) as non_null_rows,
            COUNT(CASE WHEN {fail_cond} THEN 1 END) as null_rows,
            ROUND(100.0 * COUNT(CASE WHEN {pass_cond} THEN 1 END) / NULLIF(COUNT(*), 0), 2) as completeness_rate
        FROM {table}
        {where}"""

        violation_where = self._build_where_clause(filter_expression, fail_cond)
        violation_sql = f"""
        SELECT *
        FROM {table}
        {violation_where}"""

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
placeholders = {[p.strip().lower() for p in placeholders]}
total_rows = df.count()
non_null_rows = df.filter(
    F.col("{column}").isNotNull()
    & (F.trim(F.col("{column}")) != "")
    & (~F.lower(F.trim(F.col("{column}"))).isin(placeholders))
).count()
null_rows = total_rows - non_null_rows
completeness_rate = (non_null_rows / total_rows * 100) if total_rows > 0 else 0

violations_df = df.filter(
    F.col("{column}").isNull()
    | (F.trim(F.col("{column}")) == "")
    | F.lower(F.trim(F.col("{column}"))).isin(placeholders)
)
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql.replace("NULLIF", "IFNULL"),
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _completeness_conditional(
        self, table: str, column: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Compile conditional-mode completeness (field required only when condition is met)."""
        condition_column = parameters.get("condition_column")
        condition_value = parameters.get("condition_value")
        filter_expression = parameters.get("filter_expression")

        if not condition_column:
            return self._completeness_error_result(
                "Conditional completeness requires condition_column parameter"
            )
        if condition_value is None:
            return self._completeness_error_result(
                "Conditional completeness requires condition_value parameter"
            )

        # Build condition values list
        if isinstance(condition_value, list):
            values = condition_value
        else:
            values = [condition_value]
        condition_list = ", ".join(
            f"'{str(v).replace(chr(39), chr(39) + chr(39))}'" for v in values
        )

        # Condition WHERE: only rows where condition_column matches & is not null
        condition_where = (
            f'"{condition_column}" IS NOT NULL AND "{condition_column}" IN ({condition_list})'
        )
        where = self._build_where_clause(filter_expression, condition_where)

        sql = f"""
        SELECT
            COUNT(*) as total_rows,
            COUNT(CASE WHEN "{column}" IS NOT NULL THEN 1 END) as non_null_rows,
            COUNT(CASE WHEN "{column}" IS NULL THEN 1 END) as null_rows,
            ROUND(100.0 * COUNT(CASE WHEN "{column}" IS NOT NULL THEN 1 END) / NULLIF(COUNT(*), 0), 2) as completeness_rate
        FROM {table}
        {where}"""

        violation_cond = f'"{condition_column}" IS NOT NULL AND "{condition_column}" IN ({condition_list}) AND "{column}" IS NULL'
        violation_where = self._build_where_clause(filter_expression, violation_cond)
        violation_sql = f"""
        SELECT *
        FROM {table}
        {violation_where}"""

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
condition_values = {[str(v) for v in values]}
filtered_df = df.filter(F.col("{condition_column}").isNotNull() & F.col("{condition_column}").isin(condition_values))
total_rows = filtered_df.count()
non_null_rows = filtered_df.filter(F.col("{column}").isNotNull()).count()
null_rows = total_rows - non_null_rows
completeness_rate = (non_null_rows / total_rows * 100) if total_rows > 0 else 0

violations_df = filtered_df.filter(F.col("{column}").isNull())
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql.replace("NULLIF", "IFNULL"),
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _completeness_multi_field(
        self, table: str, column: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Compile multi-field-mode completeness (all/any across multiple columns)."""
        columns = parameters.get("columns", [])
        multi_field_mode = parameters.get("multi_field_mode", "all")
        filter_expression = parameters.get("filter_expression")

        if len(columns) < 2:
            return self._completeness_error_result(
                "Multi-field completeness requires at least 2 columns"
            )

        where = self._build_where_clause(filter_expression)

        if multi_field_mode == "any":
            # At least one non-null = pass; all null = fail
            coalesce_cols = ", ".join(f'"{c}"' for c in columns)
            pass_cond = f"COALESCE({coalesce_cols}) IS NOT NULL"
            fail_cond = " AND ".join(f'"{c}" IS NULL' for c in columns)
        else:
            # all: every column non-null = pass; any null = fail
            pass_cond = " AND ".join(f'"{c}" IS NOT NULL' for c in columns)
            fail_cond = " OR ".join(f'"{c}" IS NULL' for c in columns)

        sql = f"""
        SELECT
            COUNT(*) as total_rows,
            COUNT(CASE WHEN {pass_cond} THEN 1 END) as non_null_rows,
            COUNT(CASE WHEN {fail_cond} THEN 1 END) as null_rows,
            ROUND(100.0 * COUNT(CASE WHEN {pass_cond} THEN 1 END) / NULLIF(COUNT(*), 0), 2) as completeness_rate
        FROM {table}
        {where}"""

        violation_where = self._build_where_clause(filter_expression, fail_cond)
        violation_sql = f"""
        SELECT *
        FROM {table}
        {violation_where}"""

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
columns = {columns}
total_rows = df.count()
# multi_field_mode = "{multi_field_mode}"
if "{multi_field_mode}" == "any":
    non_null_rows = df.filter(F.coalesce(*[F.col(c) for c in columns]).isNotNull()).count()
else:
    cond = None
    for c in columns:
        if cond is None:
            cond = F.col(c).isNotNull()
        else:
            cond = cond & F.col(c).isNotNull()
    non_null_rows = df.filter(cond).count()
null_rows = total_rows - non_null_rows
completeness_rate = (non_null_rows / total_rows * 100) if total_rows > 0 else 0
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql.replace("NULLIF", "IFNULL"),
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _completeness_group(
        self, table: str, column: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Compile group-mode completeness (per-partition evaluation)."""
        group_by_columns = parameters.get("group_by_columns", [])
        filter_expression = parameters.get("filter_expression")

        if not group_by_columns:
            return self._completeness_error_result(
                "Group completeness requires group_by_columns parameter"
            )

        where = self._build_where_clause(filter_expression)
        group_cols_select = ", ".join(f'"{c}"' for c in group_by_columns)
        group_cols_list = ", ".join(f'"{c}"' for c in group_by_columns)

        # When no target column is given ('*'), use COUNT(*) — avoids quoting the asterisk
        if column == "*":
            count_expr = "COUNT(*)"
            null_count_expr = "0"
            rate_expr = "100.00"
        else:
            count_expr = f'COUNT("{column}")'
            null_count_expr = f'COUNT(*) - COUNT("{column}")'
            rate_expr = f'ROUND(100.0 * COUNT("{column}") / NULLIF(COUNT(*), 0), 2)'

        sql = f"""
        SELECT
            {group_cols_select},
            COUNT(*) as total_rows,
            {count_expr} as non_null_rows,
            {null_count_expr} as null_rows,
            {rate_expr} as completeness_rate
        FROM {table}
        {where}
        GROUP BY {group_cols_list}
        ORDER BY completeness_rate ASC"""

        # Violation SQL: all failing rows (not grouped)
        null_cond = f'"{column}" IS NULL' if column != "*" else "1=0"
        violation_where = self._build_where_clause(filter_expression, null_cond)
        violation_sql = f"""
        SELECT *
        FROM {table}
        {violation_where}"""

        if column == "*":
            spark_non_null = 'F.count("*")'
            spark_null = "F.lit(0)"
            spark_rate = "F.lit(100.0)"
            spark_violations = "df.filter(F.lit(False))"  # no violations when no column specified
        else:
            spark_non_null = f'F.count("{column}")'
            spark_null = f'F.count("*") - F.count("{column}")'
            spark_rate = f'F.round(100.0 * F.count("{column}") / F.count("*"), 2)'
            spark_violations = f'df.filter(F.col("{column}").isNull())'

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
group_columns = {group_by_columns}
result_df = df.groupBy(*group_columns).agg(
    F.count("*").alias("total_rows"),
    ({spark_non_null}).alias("non_null_rows"),
    ({spark_null}).alias("null_rows"),
    ({spark_rate}).alias("completeness_rate")
).orderBy("completeness_rate")

violations_df = {spark_violations}
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql.replace("NULLIF", "IFNULL"),
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    # --- F085: Validity check validation type constants and helpers ---

    VALID_VALIDATION_TYPES = {
        "allowed_values",
        "range",
        "regex",
        "reference_lookup",
        "business_rule",
        "cross_field",
        "date_logic",
        "negative",
    }

    @staticmethod
    def _infer_validation_type(parameters: dict[str, Any]) -> str:
        """Infer validation_type from legacy parameter keys for backward compatibility.

        Returns ``"unknown"`` when no signal is available — the caller (
        ``_compile_validity_rule``) maps this to a safe error result rather
        than silently emitting a regex-against-empty-pattern query.
        """
        if parameters.get("regex_pattern"):
            return "regex"
        if parameters.get("min_value") is not None or parameters.get("max_value") is not None:
            return "range"
        if parameters.get("allowed_values"):
            return "allowed_values"
        if parameters.get("reference_dataset") or parameters.get("reference_column"):
            return "reference_lookup"
        if parameters.get("expression") or parameters.get("filter_expression"):
            return "business_rule"
        return "unknown"

    def _validity_null_handling_sql(self, column: str, null_handling: str) -> tuple:
        """Return (total_expr, null_mode, extra_select) for null handling in validity SQL.

        * fail  – NULLs count as invalid  (default)
        * skip  – NULLs excluded from denominator; extra ``skipped_rows`` column
        * pass  – NULLs count as valid
        """
        if null_handling == "skip":
            return (
                f'COUNT(CASE WHEN "{column}" IS NOT NULL THEN 1 END)',
                "skipped_null",
                f'COUNT(CASE WHEN "{column}" IS NULL THEN 1 END) as skipped_rows',
            )
        elif null_handling == "pass":
            return ("COUNT(*)", "null_valid", "")
        else:  # "fail" (default)
            return ("COUNT(*)", "null_invalid", "")

    def _validity_error_result(self, message: str) -> dict[str, Any]:
        """Return an error result dict for validity compilation failures."""
        return {
            "compiled_sql": "",
            "compiled_postgres": "",
            "compiled_mysql": "",
            "compiled_snowflake": "",
            "compiled_spark": "",
            "violation_sql": "",
            "error": True,
            "error_message": message,
        }

    def _compile_validity_rule(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Compile validity rule — dispatches to per-type helper based on validation_type."""

        validation_type = parameters.get("validation_type", self._infer_validation_type(parameters))

        if validation_type not in self.VALID_VALIDATION_TYPES:
            return self._validity_error_result(
                f"Unknown validation_type '{validation_type}'. "
                f"Allowed: {', '.join(sorted(self.VALID_VALIDATION_TYPES))}"
            )

        # Validate filter_expression if present
        filter_expression = parameters.get("filter_expression")
        if filter_expression and not self._validate_filter_expression(filter_expression):
            return self._validity_error_result(
                "Filter expression contains forbidden SQL constructs"
            )

        dispatcher = {
            "allowed_values": self._validity_allowed_values,
            "range": self._validity_range,
            "regex": self._validity_regex,
            "reference_lookup": self._validity_reference_lookup,
            "business_rule": self._validity_business_rule,
            "cross_field": self._validity_cross_field,
            "date_logic": self._validity_date_logic,
            "negative": self._validity_negative,
        }

        return dispatcher[validation_type](table, column, condition, expectation, parameters)

    # ------------------------------------------------------------------
    # Temporary stubs for validation types implemented in P02-P06.
    # Each stub reproduces the pre-F085 SQL so existing behaviour is
    # preserved until the per-type packet normalises it.
    # ------------------------------------------------------------------

    def _validity_regex(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Regex validation with null handling and filter expression support."""
        regex_pattern = parameters.get("regex_pattern", "")
        null_handling = parameters.get("null_handling", "fail")
        filter_expression = parameters.get("filter_expression")
        where = self._build_where_clause(filter_expression) if filter_expression else ""

        total_expr, null_mode, extra_select = self._validity_null_handling_sql(
            column, null_handling
        )
        extra_col = f",\n                {extra_select}" if extra_select else ""

        if null_handling == "pass":
            valid_case = (
                f'CASE WHEN "{column}" ~ \'{regex_pattern}\' OR "{column}" IS NULL THEN 1 END'
            )
            invalid_case = (
                f'CASE WHEN "{column}" IS NOT NULL AND "{column}" !~ \'{regex_pattern}\' THEN 1 END'
            )
        elif null_handling == "skip":
            valid_case = (
                f'CASE WHEN "{column}" IS NOT NULL AND "{column}" ~ \'{regex_pattern}\' THEN 1 END'
            )
            invalid_case = (
                f'CASE WHEN "{column}" IS NOT NULL AND "{column}" !~ \'{regex_pattern}\' THEN 1 END'
            )
        else:  # fail
            valid_case = f"CASE WHEN \"{column}\" ~ '{regex_pattern}' THEN 1 END"
            invalid_case = (
                f'CASE WHEN "{column}" !~ \'{regex_pattern}\' OR "{column}" IS NULL THEN 1 END'
            )

        sql = f"""
            SELECT
                {total_expr} as total_rows,
                COUNT({valid_case}) as valid_rows,
                COUNT({invalid_case}) as invalid_rows,
                ROUND(100.0 * COUNT({valid_case}) / NULLIF({total_expr}, 0), 2) as validity_rate{extra_col}
            FROM {table}
            {where}"""

        violation_sql = f"""
            SELECT *
            FROM {table}
            WHERE "{column}" !~ '{regex_pattern}' OR "{column}" IS NULL"""

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
total_rows = df.count()
valid_rows = df.filter(F.col("{column}").rlike("{regex_pattern}")).count()
invalid_rows = total_rows - valid_rows
validity_rate = (valid_rows / total_rows * 100) if total_rows > 0 else 0

violations_df = df.filter(~F.col("{column}").rlike("{regex_pattern}") | F.col("{column}").isNull())
            """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql.replace("~", "REGEXP").replace("!~", "NOT REGEXP"),
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _validity_range(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Range validation with null handling and filter expression support."""
        min_value = parameters.get("min_value")
        max_value = parameters.get("max_value")

        if min_value is None and max_value is None:
            return self._validity_error_result(
                "Range validation requires at least min_value or max_value"
            )

        null_handling = parameters.get("null_handling", "fail")
        filter_expression = parameters.get("filter_expression")
        where = self._build_where_clause(filter_expression) if filter_expression else ""

        bounds = []
        if min_value is not None:
            bounds.append(f'"{column}" >= {min_value}')
        if max_value is not None:
            bounds.append(f'"{column}" <= {max_value}')
        range_condition = " AND ".join(bounds)

        total_expr, null_mode, extra_select = self._validity_null_handling_sql(
            column, null_handling
        )
        extra_col = f",\n                {extra_select}" if extra_select else ""

        if null_handling == "pass":
            valid_case = f'CASE WHEN ({range_condition}) OR "{column}" IS NULL THEN 1 END'
            invalid_case = (
                f'CASE WHEN "{column}" IS NOT NULL AND NOT ({range_condition}) THEN 1 END'
            )
        elif null_handling == "skip":
            valid_case = f'CASE WHEN "{column}" IS NOT NULL AND ({range_condition}) THEN 1 END'
            invalid_case = (
                f'CASE WHEN "{column}" IS NOT NULL AND NOT ({range_condition}) THEN 1 END'
            )
        else:  # fail
            valid_case = f"CASE WHEN {range_condition} THEN 1 END"
            invalid_case = f'CASE WHEN NOT ({range_condition}) OR "{column}" IS NULL THEN 1 END'

        sql = f"""
            SELECT
                {total_expr} as total_rows,
                COUNT({valid_case}) as valid_rows,
                COUNT({invalid_case}) as invalid_rows,
                ROUND(100.0 * COUNT({valid_case}) / NULLIF({total_expr}, 0), 2) as validity_rate{extra_col}
            FROM {table}
            {where}"""

        violation_sql = f"""
            SELECT *
            FROM {table}
            WHERE NOT ({range_condition}) OR "{column}" IS NULL"""

        spark_bounds = []
        if min_value is not None:
            spark_bounds.append(f'F.col("{column}") >= {min_value}')
        if max_value is not None:
            spark_bounds.append(f'F.col("{column}") <= {max_value}')
        spark_condition = " & ".join(spark_bounds)

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
total_rows = df.count()
valid_rows = df.filter({spark_condition}).count()
invalid_rows = total_rows - valid_rows
validity_rate = (valid_rows / total_rows * 100) if total_rows > 0 else 0

violations_df = df.filter(~({spark_condition}) | F.col("{column}").isNull())
            """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql,
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _validity_allowed_values(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Allowed values validation with case sensitivity, CTE optimisation, null handling and filter."""
        allowed_values = parameters.get("allowed_values", [])
        if not allowed_values:
            return self._validity_error_result(
                "Allowed values validation requires a non-empty allowed_values list"
            )

        null_handling = parameters.get("null_handling", "fail")
        case_sensitive = parameters.get("case_sensitive", True)
        filter_expression = parameters.get("filter_expression")
        where = self._build_where_clause(filter_expression) if filter_expression else ""

        total_expr, null_mode, extra_select = self._validity_null_handling_sql(
            column, null_handling
        )
        extra_col = f",\n                {extra_select}" if extra_select else ""

        # Build values list with quoting
        sanitized = [str(v).replace("'", "''") for v in allowed_values]

        use_cte = len(allowed_values) > 1000

        if use_cte:
            # CTE VALUES approach for large lists
            array_items = ", ".join(f"'{v}'" for v in sanitized)
            cte = f"WITH ref_values AS (SELECT unnest(ARRAY[{array_items}]) AS val)\n            "

            if case_sensitive:
                join_cond = f't."{column}" = ref_values.val'
            else:
                join_cond = f'LOWER(t."{column}") = LOWER(ref_values.val)'

            if null_handling == "pass":
                valid_case = (
                    f'CASE WHEN ref_values.val IS NOT NULL OR t."{column}" IS NULL THEN 1 END'
                )
                invalid_case = (
                    f'CASE WHEN t."{column}" IS NOT NULL AND ref_values.val IS NULL THEN 1 END'
                )
            elif null_handling == "skip":
                total_expr_cte = f'COUNT(CASE WHEN t."{column}" IS NOT NULL THEN 1 END)'
                valid_case = (
                    f'CASE WHEN t."{column}" IS NOT NULL AND ref_values.val IS NOT NULL THEN 1 END'
                )
                invalid_case = (
                    f'CASE WHEN t."{column}" IS NOT NULL AND ref_values.val IS NULL THEN 1 END'
                )
                extra_col = f',\n                COUNT(CASE WHEN t."{column}" IS NULL THEN 1 END) as skipped_rows'
                total_expr = total_expr_cte
            else:  # fail
                valid_case = "CASE WHEN ref_values.val IS NOT NULL THEN 1 END"
                invalid_case = (
                    f'CASE WHEN ref_values.val IS NULL OR t."{column}" IS NULL THEN 1 END'
                )

            sql = f"""{cte}SELECT
                {total_expr} as total_rows,
                COUNT({valid_case}) as valid_rows,
                COUNT({invalid_case}) as invalid_rows,
                ROUND(100.0 * COUNT({valid_case}) / NULLIF({total_expr}, 0), 2) as validity_rate{extra_col}
            FROM {table} t
            LEFT JOIN ref_values ON {join_cond}
            {where}"""

            violation_sql = f"""{cte}SELECT t.*
            FROM {table} t
            LEFT JOIN ref_values ON {join_cond}
            WHERE ref_values.val IS NULL OR t."{column}" IS NULL"""
        else:
            # Standard IN clause
            if case_sensitive:
                values_list = ", ".join(f"'{v}'" for v in sanitized)
                in_expr = f'"{column}" IN ({values_list})'
                not_in_expr = f'"{column}" NOT IN ({values_list})'
            else:
                values_list = ", ".join(f"'{v.lower()}'" for v in sanitized)
                in_expr = f'LOWER("{column}") IN ({values_list})'
                not_in_expr = f'LOWER("{column}") NOT IN ({values_list})'

            if null_handling == "pass":
                valid_case = f'CASE WHEN {in_expr} OR "{column}" IS NULL THEN 1 END'
                invalid_case = f'CASE WHEN "{column}" IS NOT NULL AND {not_in_expr} THEN 1 END'
            elif null_handling == "skip":
                valid_case = f'CASE WHEN "{column}" IS NOT NULL AND {in_expr} THEN 1 END'
                invalid_case = f'CASE WHEN "{column}" IS NOT NULL AND {not_in_expr} THEN 1 END'
            else:  # fail
                valid_case = f"CASE WHEN {in_expr} THEN 1 END"
                invalid_case = f'CASE WHEN {not_in_expr} OR "{column}" IS NULL THEN 1 END'

            sql = f"""
            SELECT
                {total_expr} as total_rows,
                COUNT({valid_case}) as valid_rows,
                COUNT({invalid_case}) as invalid_rows,
                ROUND(100.0 * COUNT({valid_case}) / NULLIF({total_expr}, 0), 2) as validity_rate{extra_col}
            FROM {table}
            {where}"""

            violation_sql = f"""
            SELECT *
            FROM {table}
            WHERE {not_in_expr} OR "{column}" IS NULL"""

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
allowed_values = {allowed_values}
total_rows = df.count()
valid_rows = df.filter(F.col("{column}").isin(allowed_values)).count()
invalid_rows = total_rows - valid_rows
validity_rate = (valid_rows / total_rows * 100) if total_rows > 0 else 0

violations_df = df.filter(~F.col("{column}").isin(allowed_values) | F.col("{column}").isNull())
            """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql.replace("~", "REGEXP").replace("!~", "NOT REGEXP"),
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _validity_reference_lookup(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Reference lookup validation via LEFT JOIN against a reference table."""
        ref_dataset = parameters.get("reference_dataset")
        ref_column = parameters.get("reference_column")

        if not ref_dataset or not ref_column:
            return self._validity_error_result(
                "reference_lookup requires both reference_dataset and reference_column"
            )

        # Validate identifiers (alphanumeric + underscore + dots for schema.table)
        ident_re = re.compile(r"^[\w.]+$")
        if not ident_re.match(ref_dataset) or not ident_re.match(ref_column):
            return self._validity_error_result(
                "reference_dataset and reference_column must be valid identifiers"
            )

        null_handling = parameters.get("null_handling", "fail")
        filter_expression = parameters.get("filter_expression")
        where_parts = []
        if filter_expression:
            where_parts.append(f"({filter_expression})")

        # Quote ref table — handle schema.table
        if "." in ref_dataset:
            ref_schema, ref_tbl = ref_dataset.split(".", 1)
            ref_full = f'"{ref_schema}"."{ref_tbl}"'
        else:
            ref_full = f'"{ref_dataset}"'

        join_cond = f't."{column}" = ref."{ref_column}"'

        if null_handling == "pass":
            valid_case = (
                f'CASE WHEN ref."{ref_column}" IS NOT NULL OR t."{column}" IS NULL THEN 1 END'
            )
            invalid_case = (
                f'CASE WHEN t."{column}" IS NOT NULL AND ref."{ref_column}" IS NULL THEN 1 END'
            )
            total_expr = "COUNT(*)"
            extra_col = ""
        elif null_handling == "skip":
            valid_case = (
                f'CASE WHEN t."{column}" IS NOT NULL AND ref."{ref_column}" IS NOT NULL THEN 1 END'
            )
            invalid_case = (
                f'CASE WHEN t."{column}" IS NOT NULL AND ref."{ref_column}" IS NULL THEN 1 END'
            )
            total_expr = f'COUNT(CASE WHEN t."{column}" IS NOT NULL THEN 1 END)'
            extra_col = f',\n                COUNT(CASE WHEN t."{column}" IS NULL THEN 1 END) as skipped_rows'
        else:  # fail
            valid_case = f'CASE WHEN ref."{ref_column}" IS NOT NULL THEN 1 END'
            invalid_case = (
                f'CASE WHEN ref."{ref_column}" IS NULL OR t."{column}" IS NULL THEN 1 END'
            )
            total_expr = "COUNT(*)"
            extra_col = ""

        where = ""
        if where_parts:
            where = "WHERE " + " AND ".join(where_parts)

        sql = f"""
            SELECT
                {total_expr} as total_rows,
                COUNT({valid_case}) as valid_rows,
                COUNT({invalid_case}) as invalid_rows,
                ROUND(100.0 * COUNT({valid_case}) / NULLIF({total_expr}, 0), 2) as validity_rate{extra_col}
            FROM {table} t
            LEFT JOIN {ref_full} ref ON {join_cond}
            {where}"""

        violation_sql = f"""
            SELECT t.*
            FROM {table} t
            LEFT JOIN {ref_full} ref ON {join_cond}
            WHERE ref."{ref_column}" IS NULL OR t."{column}" IS NULL"""

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
ref_df = spark.table("{ref_dataset}")
joined = df.join(ref_df, df["{column}"] == ref_df["{ref_column}"], "left")
total_rows = df.count()
valid_rows = joined.filter(F.col("{ref_column}").isNotNull()).count()
invalid_rows = total_rows - valid_rows
validity_rate = (valid_rows / total_rows * 100) if total_rows > 0 else 0

violations_df = joined.filter(F.col("{ref_column}").isNull())
            """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql,
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _validity_business_rule(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Business rule validation — arbitrary SQL boolean expression."""
        expression = parameters.get("business_rule_expression")
        if not expression:
            return self._validity_error_result("business_rule requires a business_rule_expression")

        if not self._validate_filter_expression(expression):
            return self._validity_error_result(
                "business_rule_expression contains forbidden SQL constructs"
            )

        null_handling = parameters.get("null_handling", "fail")
        filter_expression = parameters.get("filter_expression")
        where = self._build_where_clause(filter_expression) if filter_expression else ""

        total_expr, _, extra_select = self._validity_null_handling_sql(column, null_handling)
        extra_col = f",\n                {extra_select}" if extra_select else ""

        if null_handling == "pass":
            valid_case = f'CASE WHEN ({expression}) OR "{column}" IS NULL THEN 1 END'
            invalid_case = f'CASE WHEN "{column}" IS NOT NULL AND NOT ({expression}) THEN 1 END'
        elif null_handling == "skip":
            valid_case = f'CASE WHEN "{column}" IS NOT NULL AND ({expression}) THEN 1 END'
            invalid_case = f'CASE WHEN "{column}" IS NOT NULL AND NOT ({expression}) THEN 1 END'
        else:  # fail
            valid_case = f"CASE WHEN ({expression}) THEN 1 END"
            invalid_case = f'CASE WHEN NOT ({expression}) OR "{column}" IS NULL THEN 1 END'

        sql = f"""
            SELECT
                {total_expr} as total_rows,
                COUNT({valid_case}) as valid_rows,
                COUNT({invalid_case}) as invalid_rows,
                ROUND(100.0 * COUNT({valid_case}) / NULLIF({total_expr}, 0), 2) as validity_rate{extra_col}
            FROM {table}
            {where}"""

        violation_sql = f"""
            SELECT *
            FROM {table}
            WHERE NOT ({expression}) OR "{column}" IS NULL"""

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
total_rows = df.count()
valid_rows = df.filter(F.expr("{expression}")).count()
invalid_rows = total_rows - valid_rows
validity_rate = (valid_rows / total_rows * 100) if total_rows > 0 else 0

violations_df = df.filter(~F.expr("{expression}"))
            """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql,
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    VALID_COMPARISON_OPERATORS = {"=", "!=", "<", ">", "<=", ">="}

    # Aliases LLMs commonly emit for comparison operators. Maps to canonical
    # SQL symbols. Used by cross_field and date_logic compilers.
    _OP_ALIASES: dict[str, str] = {
        "=": "=",
        "==": "=",
        "eq": "=",
        "equal": "=",
        "equals": "=",
        "!=": "!=",
        "<>": "!=",
        "ne": "!=",
        "not_equal": "!=",
        "not_equals": "!=",
        "<": "<",
        "lt": "<",
        "less": "<",
        "less_than": "<",
        "before": "<",
        "<=": "<=",
        "lte": "<=",
        "less_equal": "<=",
        "less_than_or_equal": "<=",
        "on_or_before": "<=",
        "not_after": "<=",
        ">": ">",
        "gt": ">",
        "greater": ">",
        "greater_than": ">",
        "after": ">",
        ">=": ">=",
        "gte": ">=",
        "greater_equal": ">=",
        "greater_than_or_equal": ">=",
        "on_or_after": ">=",
        "not_before": ">=",
    }

    @classmethod
    def _normalize_comparison_operator(cls, raw: Any, default: str = "=") -> str:
        if raw is None:
            return default
        return cls._OP_ALIASES.get(str(raw).strip().lower(), str(raw))

    def _validity_cross_field(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Cross-field comparison validation."""
        comparison_column = parameters.get("comparison_column")
        raw_op = parameters.get("comparison_operator") or parameters.get("date_operator") or "="
        operator = self._normalize_comparison_operator(raw_op, default="=")

        if not comparison_column:
            return self._validity_error_result("cross_field requires comparison_column")

        if operator not in self.VALID_COMPARISON_OPERATORS:
            return self._validity_error_result(
                f"Invalid comparison_operator '{operator}'. Allowed: {', '.join(sorted(self.VALID_COMPARISON_OPERATORS))}"
            )

        null_handling = parameters.get("null_handling", "fail")
        filter_expression = parameters.get("filter_expression")
        where = self._build_where_clause(filter_expression) if filter_expression else ""

        cmp_expr = f'"{column}" {operator} "{comparison_column}"'
        either_null = f'("{column}" IS NULL OR "{comparison_column}" IS NULL)'

        total_expr, _, extra_select = self._validity_null_handling_sql(column, null_handling)
        extra_col = f",\n                {extra_select}" if extra_select else ""

        if null_handling == "pass":
            valid_case = f"CASE WHEN ({cmp_expr}) OR {either_null} THEN 1 END"
            invalid_case = f"CASE WHEN NOT {either_null} AND NOT ({cmp_expr}) THEN 1 END"
        elif null_handling == "skip":
            valid_case = f"CASE WHEN NOT {either_null} AND ({cmp_expr}) THEN 1 END"
            invalid_case = f"CASE WHEN NOT {either_null} AND NOT ({cmp_expr}) THEN 1 END"
            # Override total_expr: exclude rows where either column is NULL
            total_expr = f"COUNT(CASE WHEN NOT {either_null} THEN 1 END)"
            extra_col = (
                f",\n                COUNT(CASE WHEN {either_null} THEN 1 END) as skipped_rows"
            )
        else:  # fail
            valid_case = f"CASE WHEN ({cmp_expr}) THEN 1 END"
            invalid_case = f"CASE WHEN NOT ({cmp_expr}) OR {either_null} THEN 1 END"

        sql = f"""
            SELECT
                {total_expr} as total_rows,
                COUNT({valid_case}) as valid_rows,
                COUNT({invalid_case}) as invalid_rows,
                ROUND(100.0 * COUNT({valid_case}) / NULLIF({total_expr}, 0), 2) as validity_rate{extra_col}
            FROM {table}
            {where}"""

        violation_sql = f"""
            SELECT *
            FROM {table}
            WHERE NOT ({cmp_expr}) OR {either_null}"""

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
total_rows = df.count()
valid_rows = df.filter(F.col("{column}") {operator} F.col("{comparison_column}")).count()
invalid_rows = total_rows - valid_rows
validity_rate = (valid_rows / total_rows * 100) if total_rows > 0 else 0

violations_df = df.filter(~(F.col("{column}") {operator} F.col("{comparison_column}")))
            """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql,
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _validity_date_logic(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Date logic validation — cross-field comparison with explicit date cast."""
        comparison_column = parameters.get("comparison_column")
        raw_op = parameters.get("comparison_operator") or parameters.get("date_operator") or "<="
        operator = self._normalize_comparison_operator(raw_op, default="<=")

        if not comparison_column:
            return self._validity_error_result("date_logic requires comparison_column")

        if operator not in self.VALID_COMPARISON_OPERATORS:
            return self._validity_error_result(
                f"Invalid comparison_operator '{operator}'. Allowed: {', '.join(sorted(self.VALID_COMPARISON_OPERATORS))}"
            )

        null_handling = parameters.get("null_handling", "fail")
        filter_expression = parameters.get("filter_expression")
        where = self._build_where_clause(filter_expression) if filter_expression else ""

        cmp_expr = f'CAST("{column}" AS DATE) {operator} CAST("{comparison_column}" AS DATE)'
        either_null = f'("{column}" IS NULL OR "{comparison_column}" IS NULL)'

        total_expr, _, extra_select = self._validity_null_handling_sql(column, null_handling)
        extra_col = f",\n                {extra_select}" if extra_select else ""

        if null_handling == "pass":
            valid_case = f"CASE WHEN ({cmp_expr}) OR {either_null} THEN 1 END"
            invalid_case = f"CASE WHEN NOT {either_null} AND NOT ({cmp_expr}) THEN 1 END"
        elif null_handling == "skip":
            valid_case = f"CASE WHEN NOT {either_null} AND ({cmp_expr}) THEN 1 END"
            invalid_case = f"CASE WHEN NOT {either_null} AND NOT ({cmp_expr}) THEN 1 END"
            total_expr = f"COUNT(CASE WHEN NOT {either_null} THEN 1 END)"
            extra_col = (
                f",\n                COUNT(CASE WHEN {either_null} THEN 1 END) as skipped_rows"
            )
        else:  # fail
            valid_case = f"CASE WHEN ({cmp_expr}) THEN 1 END"
            invalid_case = f"CASE WHEN NOT ({cmp_expr}) OR {either_null} THEN 1 END"

        sql = f"""
            SELECT
                {total_expr} as total_rows,
                COUNT({valid_case}) as valid_rows,
                COUNT({invalid_case}) as invalid_rows,
                ROUND(100.0 * COUNT({valid_case}) / NULLIF({total_expr}, 0), 2) as validity_rate{extra_col}
            FROM {table}
            {where}"""

        violation_sql = f"""
            SELECT *
            FROM {table}
            WHERE NOT ({cmp_expr}) OR {either_null}"""

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
total_rows = df.count()
valid_rows = df.filter(F.col("{column}").cast("date") {operator} F.col("{comparison_column}").cast("date")).count()
invalid_rows = total_rows - valid_rows
validity_rate = (valid_rows / total_rows * 100) if total_rows > 0 else 0

violations_df = df.filter(~(F.col("{column}").cast("date") {operator} F.col("{comparison_column}").cast("date")))
            """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql,
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _validity_negative(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Negative constraint validation — rows matching expression are INVALID."""
        expression = parameters.get("negative_expression")
        if not expression:
            return self._validity_error_result("negative requires a negative_expression")

        if not self._validate_filter_expression(expression):
            return self._validity_error_result(
                "negative_expression contains forbidden SQL constructs"
            )

        null_handling = parameters.get("null_handling", "fail")
        filter_expression = parameters.get("filter_expression")
        where = self._build_where_clause(filter_expression) if filter_expression else ""

        total_expr, _, extra_select = self._validity_null_handling_sql(column, null_handling)
        extra_col = f",\n                {extra_select}" if extra_select else ""

        # Inverted logic: matching = invalid, NOT matching = valid
        if null_handling == "pass":
            valid_case = f'CASE WHEN NOT ({expression}) OR "{column}" IS NULL THEN 1 END'
            invalid_case = f'CASE WHEN "{column}" IS NOT NULL AND ({expression}) THEN 1 END'
        elif null_handling == "skip":
            valid_case = f'CASE WHEN "{column}" IS NOT NULL AND NOT ({expression}) THEN 1 END'
            invalid_case = f'CASE WHEN "{column}" IS NOT NULL AND ({expression}) THEN 1 END'
        else:  # fail
            valid_case = f"CASE WHEN NOT ({expression}) THEN 1 END"
            invalid_case = f'CASE WHEN ({expression}) OR "{column}" IS NULL THEN 1 END'

        sql = f"""
            SELECT
                {total_expr} as total_rows,
                COUNT({valid_case}) as valid_rows,
                COUNT({invalid_case}) as invalid_rows,
                ROUND(100.0 * COUNT({valid_case}) / NULLIF({total_expr}, 0), 2) as validity_rate{extra_col}
            FROM {table}
            {where}"""

        violation_sql = f"""
            SELECT *
            FROM {table}
            WHERE ({expression}) OR "{column}" IS NULL"""

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
total_rows = df.count()
invalid_rows = df.filter(F.expr("{expression}")).count()
valid_rows = total_rows - invalid_rows
validity_rate = (valid_rows / total_rows * 100) if total_rows > 0 else 0

violations_df = df.filter(F.expr("{expression}"))
            """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql,
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    # --- F086: Uniqueness check mode constants and helpers ---

    VALID_UNIQUENESS_MODES = {
        "exact",
        "composite",
        "scoped",
        "cross_dataset",
        "fuzzy",
        "temporal",
    }

    @staticmethod
    def _infer_uniqueness_mode(parameters: dict[str, Any]) -> str:
        """Infer uniqueness_mode from parameter keys for backward compatibility."""
        if parameters.get("scope_columns"):
            return "scoped"
        if parameters.get("cross_dataset_name"):
            return "cross_dataset"
        if parameters.get("fuzzy_algorithm"):
            return "fuzzy"
        if parameters.get("temporal_window"):
            return "temporal"
        columns = parameters.get("columns", [])
        if len(columns) > 1:
            return "composite"
        return "exact"

    def _uniqueness_null_handling_sql(
        self, columns: list, null_handling: str, case_sensitive: bool = True
    ) -> tuple:
        """Return (key_exprs, null_where_fragment) for uniqueness grouping.

        * exclude (default) – rows where any key column IS NULL are filtered out
        * include – NULLs are coalesced to a sentinel so they group together
        """
        col_exprs = []
        for col in columns:
            if case_sensitive:
                col_exprs.append(f'"{col}"')
            else:
                col_exprs.append(f'LOWER("{col}"::text)')

        if null_handling == "include":
            coalesced = [f"COALESCE({expr}::text, '__NULL__')" for expr in col_exprs]
            return coalesced, ""
        else:  # "exclude" (default)
            null_filters = [f'"{col}" IS NOT NULL' for col in columns]
            return col_exprs, " AND ".join(null_filters)

    def _uniqueness_error_result(self, message: str) -> dict[str, Any]:
        """Return an error result dict for uniqueness compilation failures."""
        return {
            "compiled_sql": "",
            "compiled_postgres": "",
            "compiled_mysql": "",
            "compiled_snowflake": "",
            "compiled_spark": "",
            "violation_sql": "",
            "error": True,
            "error_message": message,
        }

    @staticmethod
    def _parse_temporal_window(window: str) -> int:
        """Parse a temporal window string (e.g. '1d', '2h', '30m', '60s') to seconds.

        Returns -1 on invalid format.
        """
        import re

        m = re.match(r"^(\d+)([dhms])$", str(window).strip())
        if not m:
            return -1
        value = int(m.group(1))
        unit = m.group(2)
        multipliers = {"d": 86400, "h": 3600, "m": 60, "s": 1}
        return value * multipliers[unit]

    def _compile_uniqueness_rule(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Compile uniqueness rule — dispatches to per-mode helper based on uniqueness_mode."""

        uniqueness_mode = parameters.get("uniqueness_mode", self._infer_uniqueness_mode(parameters))

        if uniqueness_mode not in self.VALID_UNIQUENESS_MODES:
            return self._uniqueness_error_result(
                f"Unknown uniqueness_mode '{uniqueness_mode}'. "
                f"Allowed: {', '.join(sorted(self.VALID_UNIQUENESS_MODES))}"
            )

        # Validate filter_expression if present
        filter_expression = parameters.get("filter_expression")
        if filter_expression and not self._validate_filter_expression(filter_expression):
            return self._uniqueness_error_result(
                "Filter expression contains forbidden SQL constructs"
            )

        dispatcher = {
            "exact": self._uniqueness_exact,
            "composite": self._uniqueness_composite,
            "scoped": self._uniqueness_scoped,
            "cross_dataset": self._uniqueness_cross_dataset,
            "fuzzy": self._uniqueness_fuzzy,
            "temporal": self._uniqueness_temporal,
        }

        return dispatcher[uniqueness_mode](table, column, condition, expectation, parameters)

    # --- F086: Uniqueness mode helpers (P02–P06) ---

    def _uniqueness_exact(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """P02: Single-column exact uniqueness."""
        columns = parameters.get("columns", [column])
        if not columns:
            columns = [column]
        col = columns[0]
        null_handling = parameters.get("null_handling", "exclude")
        case_sensitive = parameters.get("case_sensitive", True)
        filter_expression = parameters.get("filter_expression")

        key_exprs, null_where = self._uniqueness_null_handling_sql(
            [col], null_handling, case_sensitive
        )
        key_expr = key_exprs[0]

        where_parts = []
        if null_where:
            where_parts.append(null_where)
        if filter_expression:
            where_parts.append(f"({filter_expression})")
        where = "WHERE " + " AND ".join(where_parts) if where_parts else ""

        sql = f"""
            WITH duplicates AS (
                SELECT {key_expr} as key_val, COUNT(*) as duplicate_count
                FROM {table}
                {where}
                GROUP BY {key_expr}
                HAVING COUNT(*) > 1
            )
            SELECT
                (SELECT COUNT(*) FROM {table} {where}) as total_rows,
                (SELECT COUNT(*) FROM duplicates) as duplicate_groups,
                (SELECT COALESCE(SUM(duplicate_count), 0) FROM duplicates) as duplicate_rows,
                (SELECT COALESCE(MAX(duplicate_count), 0) FROM duplicates) as max_group_size,
                ROUND(100.0 * ((SELECT COUNT(*) FROM {table} {where}) -
                    (SELECT COALESCE(SUM(duplicate_count), 0) FROM duplicates)) /
                    NULLIF((SELECT COUNT(*) FROM {table} {where}), 0), 2) as uniqueness_rate"""

        violation_sql = f"""
            SELECT t.*
            FROM {table} t
            WHERE {key_expr} IN (
                SELECT {key_expr}
                FROM {table}
                {where}
                GROUP BY {key_expr}
                HAVING COUNT(*) > 1
            )"""

        col_name = col
        spark_code = f"""
from pyspark.sql import functions as F
from pyspark.sql.window import Window

df = spark.table("{table}")
total_rows = df.count()
key_col = {"F.lower(F.col('" + col_name + "').cast('string'))" if not case_sensitive else "F.col('" + col_name + "')"}
window_spec = Window.partitionBy(key_col)
duplicates_df = df.withColumn("_dup_count", F.count("*").over(window_spec)).filter(F.col("_dup_count") > 1)
duplicate_rows = duplicates_df.count()
duplicate_groups = duplicates_df.select(key_col).distinct().count()
max_group_size = duplicates_df.agg(F.max("_dup_count")).collect()[0][0] or 0
uniqueness_rate = ((total_rows - duplicate_rows) / total_rows * 100) if total_rows > 0 else 100
violations_df = duplicates_df.drop("_dup_count")
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql,
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _uniqueness_composite(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """P02: Composite key uniqueness (multiple columns)."""
        columns = parameters.get("columns", [column])
        if not columns:
            columns = [column]
        if len(columns) <= 1:
            return self._uniqueness_exact(table, column, condition, expectation, parameters)

        null_handling = parameters.get("null_handling", "exclude")
        case_sensitive = parameters.get("case_sensitive", True)
        filter_expression = parameters.get("filter_expression")

        key_exprs, null_where = self._uniqueness_null_handling_sql(
            columns, null_handling, case_sensitive
        )
        key_list = ", ".join(key_exprs)

        where_parts = []
        if null_where:
            where_parts.append(null_where)
        if filter_expression:
            where_parts.append(f"({filter_expression})")
        where = "WHERE " + " AND ".join(where_parts) if where_parts else ""

        sql = f"""
            WITH duplicates AS (
                SELECT {key_list}, COUNT(*) as duplicate_count
                FROM {table}
                {where}
                GROUP BY {key_list}
                HAVING COUNT(*) > 1
            )
            SELECT
                (SELECT COUNT(*) FROM {table} {where}) as total_rows,
                (SELECT COUNT(*) FROM duplicates) as duplicate_groups,
                (SELECT COALESCE(SUM(duplicate_count), 0) FROM duplicates) as duplicate_rows,
                (SELECT COALESCE(MAX(duplicate_count), 0) FROM duplicates) as max_group_size,
                ROUND(100.0 * ((SELECT COUNT(*) FROM {table} {where}) -
                    (SELECT COALESCE(SUM(duplicate_count), 0) FROM duplicates)) /
                    NULLIF((SELECT COUNT(*) FROM {table} {where}), 0), 2) as uniqueness_rate"""

        violation_sql = f"""
            SELECT t.*
            FROM {table} t
            WHERE ({key_list}) IN (
                SELECT {key_list}
                FROM {table}
                {where}
                GROUP BY {key_list}
                HAVING COUNT(*) > 1
            )"""

        ", ".join([f'"{c}"' for c in columns])
        spark_code = f"""
from pyspark.sql import functions as F
from pyspark.sql.window import Window

df = spark.table("{table}")
total_rows = df.count()
key_cols = [{", ".join(['"' + c + '"' for c in columns])}]
window_spec = Window.partitionBy(*key_cols)
duplicates_df = df.withColumn("_dup_count", F.count("*").over(window_spec)).filter(F.col("_dup_count") > 1)
duplicate_rows = duplicates_df.count()
duplicate_groups = duplicates_df.select(*key_cols).distinct().count()
max_group_size = duplicates_df.agg(F.max("_dup_count")).collect()[0][0] or 0
uniqueness_rate = ((total_rows - duplicate_rows) / total_rows * 100) if total_rows > 0 else 100
violations_df = duplicates_df.drop("_dup_count")
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql,
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _uniqueness_scoped(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """P03: Scoped uniqueness — unique within partitions."""
        scope_columns = parameters.get("scope_columns", [])
        if not scope_columns:
            return self._uniqueness_error_result("Scoped uniqueness requires scope_columns")

        columns = parameters.get("columns", [column])
        if not columns:
            columns = [column]
        null_handling = parameters.get("null_handling", "exclude")
        case_sensitive = parameters.get("case_sensitive", True)
        filter_expression = parameters.get("filter_expression")

        key_exprs, null_where = self._uniqueness_null_handling_sql(
            columns, null_handling, case_sensitive
        )
        scope_exprs = [f'"{sc}"' for sc in scope_columns]
        all_group = ", ".join(scope_exprs + key_exprs)

        where_parts = []
        if null_where:
            where_parts.append(null_where)
        if filter_expression:
            where_parts.append(f"({filter_expression})")
        where = "WHERE " + " AND ".join(where_parts) if where_parts else ""

        sql = f"""
            WITH scoped_dups AS (
                SELECT {all_group}, COUNT(*) as duplicate_count
                FROM {table}
                {where}
                GROUP BY {all_group}
                HAVING COUNT(*) > 1
            )
            SELECT
                (SELECT COUNT(*) FROM {table} {where}) as total_rows,
                (SELECT COUNT(*) FROM scoped_dups) as duplicate_groups,
                (SELECT COALESCE(SUM(duplicate_count), 0) FROM scoped_dups) as duplicate_rows,
                (SELECT COALESCE(MAX(duplicate_count), 0) FROM scoped_dups) as max_group_size,
                ROUND(100.0 * ((SELECT COUNT(*) FROM {table} {where}) -
                    (SELECT COALESCE(SUM(duplicate_count), 0) FROM scoped_dups)) /
                    NULLIF((SELECT COUNT(*) FROM {table} {where}), 0), 2) as uniqueness_rate"""

        violation_sql = f"""
            SELECT t.*
            FROM {table} t
            WHERE ({all_group}) IN (
                SELECT {all_group}
                FROM {table}
                {where}
                GROUP BY {all_group}
                HAVING COUNT(*) > 1
            )"""

        spark_code = f"""
from pyspark.sql import functions as F
from pyspark.sql.window import Window

df = spark.table("{table}")
total_rows = df.count()
scope_cols = {scope_columns}
key_cols = {columns}
window_spec = Window.partitionBy(*(scope_cols + key_cols))
duplicates_df = df.withColumn("_dup_count", F.count("*").over(window_spec)).filter(F.col("_dup_count") > 1)
duplicate_rows = duplicates_df.count()
uniqueness_rate = ((total_rows - duplicate_rows) / total_rows * 100) if total_rows > 0 else 100
violations_df = duplicates_df.drop("_dup_count")
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql,
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _uniqueness_cross_dataset(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """P04: Cross-dataset uniqueness via INNER JOIN."""
        cross_name = parameters.get("cross_dataset_name")
        cross_col = parameters.get("cross_dataset_column")
        if not cross_name:
            return self._uniqueness_error_result("cross_dataset mode requires cross_dataset_name")
        if not cross_col:
            return self._uniqueness_error_result("cross_dataset mode requires cross_dataset_column")

        columns = parameters.get("columns", [column])
        if not columns:
            columns = [column]
        col = columns[0]
        case_sensitive = parameters.get("case_sensitive", True)
        filter_expression = parameters.get("filter_expression")

        if case_sensitive:
            join_cond = f't."{col}" = c."{cross_col}"'
            key_expr = f't."{col}"'
        else:
            join_cond = f'LOWER(t."{col}"::text) = LOWER(c."{cross_col}"::text)'
            key_expr = f'LOWER(t."{col}"::text)'

        where_parts = [f't."{col}" IS NOT NULL']
        if filter_expression:
            where_parts.append(f"({filter_expression})")
        where = "WHERE " + " AND ".join(where_parts)

        filter_where = ""
        if filter_expression:
            filter_where = f"WHERE ({filter_expression})"

        sql = f"""
            WITH overlaps AS (
                SELECT DISTINCT {key_expr} as key_val
                FROM {table} t
                INNER JOIN {cross_name} c ON {join_cond}
                {where}
            )
            SELECT
                (SELECT COUNT(*) FROM {table} t {filter_where}) as total_rows,
                (SELECT COUNT(*) FROM overlaps) as duplicate_groups,
                (SELECT COUNT(*) FROM {table} t WHERE {key_expr} IN (SELECT key_val FROM overlaps)) as duplicate_rows,
                1 as max_group_size,
                ROUND(100.0 * ((SELECT COUNT(*) FROM {table} t {filter_where}) -
                    (SELECT COUNT(*) FROM {table} t WHERE {key_expr} IN (SELECT key_val FROM overlaps))) /
                    NULLIF((SELECT COUNT(*) FROM {table} t {filter_where}), 0), 2) as uniqueness_rate"""

        violation_sql = f"""
            SELECT t.*
            FROM {table} t
            INNER JOIN {cross_name} c ON {join_cond}
            {where}"""

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
cross_df = spark.table("{cross_name}")
total_rows = df.count()
overlaps = df.join(cross_df, df["{col}"] == cross_df["{cross_col}"], "inner")
duplicate_rows = overlaps.select("{col}").distinct().count()
uniqueness_rate = ((total_rows - duplicate_rows) / total_rows * 100) if total_rows > 0 else 100
violations_df = overlaps
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql,
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _uniqueness_fuzzy(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """P05: Fuzzy duplicate detection using similarity algorithms."""
        columns = parameters.get("columns", [column])
        if not columns:
            columns = [column]
        col = columns[0]
        algorithm = parameters.get("fuzzy_algorithm", "levenshtein")
        threshold = parameters.get("fuzzy_threshold", 0.85)
        filter_expression = parameters.get("filter_expression")

        where_parts = [f'a."{col}" IS NOT NULL', f'b."{col}" IS NOT NULL']
        if filter_expression:
            where_parts.append(f"({filter_expression})")
        where = " AND ".join(where_parts)

        if algorithm == "soundex":
            similarity_cond = f'soundex(a."{col}"::text) = soundex(b."{col}"::text)'
            similarity_expr = f'CASE WHEN soundex(a."{col}"::text) = soundex(b."{col}"::text) THEN 1.0 ELSE 0.0 END'
        else:  # levenshtein
            similarity_expr = (
                f'1.0 - (levenshtein(a."{col}"::text, b."{col}"::text)::float / '
                f'GREATEST(length(a."{col}"::text), length(b."{col}"::text), 1))'
            )
            similarity_cond = f"{similarity_expr} >= {threshold}"

        filter_where = ""
        if filter_expression:
            filter_where = f"WHERE ({filter_expression})"

        sql = f"""
            WITH pairs AS (
                SELECT a.ctid as a_ctid, b.ctid as b_ctid,
                       a."{col}" as a_val, b."{col}" as b_val,
                       {similarity_expr} as similarity
                FROM {table} a
                CROSS JOIN {table} b
                WHERE a.ctid < b.ctid AND {where}
            ),
            fuzzy_matches AS (
                SELECT * FROM pairs WHERE similarity >= {threshold}
            )
            SELECT
                (SELECT COUNT(*) FROM {table} {filter_where}) as total_rows,
                (SELECT COUNT(*) FROM fuzzy_matches) as candidate_duplicate_pairs,
                (SELECT COUNT(DISTINCT a_val) + COUNT(DISTINCT b_val) FROM fuzzy_matches) as duplicate_rows,
                0 as duplicate_groups,
                0 as max_group_size,
                ROUND(100.0 * ((SELECT COUNT(*) FROM {table} {filter_where}) -
                    (SELECT COUNT(DISTINCT a_val) + COUNT(DISTINCT b_val) FROM fuzzy_matches)) /
                    NULLIF((SELECT COUNT(*) FROM {table} {filter_where}), 0), 2) as uniqueness_rate"""

        violation_sql = f"""
            SELECT a.*, b."{col}" as matched_value,
                   {similarity_expr} as similarity
            FROM {table} a
            CROSS JOIN {table} b
            WHERE a.ctid < b.ctid AND {where}
              AND {similarity_cond}"""

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
total_rows = df.count()
# Fuzzy matching requires pairwise comparison
# Levenshtein: F.levenshtein(col_a, col_b)
cross = df.alias("a").crossJoin(df.alias("b"))
cross = cross.filter(F.col("a.{col}") < F.col("b.{col}"))
cross = cross.withColumn("similarity",
    1.0 - F.levenshtein(F.col("a.{col}"), F.col("b.{col}")) /
    F.greatest(F.length(F.col("a.{col}")), F.length(F.col("b.{col}")), F.lit(1)))
violations_df = cross.filter(F.col("similarity") >= {threshold})
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql,
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _uniqueness_temporal(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """P06: Temporal uniqueness — unique within a time window."""
        temporal_column = parameters.get("temporal_column")
        temporal_window = parameters.get("temporal_window")
        if not temporal_column:
            return self._uniqueness_error_result("temporal mode requires temporal_column")
        if not temporal_window:
            return self._uniqueness_error_result("temporal mode requires temporal_window")
        window_seconds = self._parse_temporal_window(temporal_window)
        if window_seconds < 0:
            return self._uniqueness_error_result(
                f"Invalid temporal_window format: '{temporal_window}'. Use Nd, Nh, Nm, or Ns."
            )

        columns = parameters.get("columns", [column])
        if not columns:
            columns = [column]
        null_handling = parameters.get("null_handling", "exclude")
        case_sensitive = parameters.get("case_sensitive", True)
        filter_expression = parameters.get("filter_expression")

        key_exprs, null_where = self._uniqueness_null_handling_sql(
            columns, null_handling, case_sensitive
        )
        key_join_parts = []
        for ke in key_exprs:
            key_join_parts.append(
                f"a.{ke} = b.{ke}"
                if "(" not in ke
                else f"{ke.replace(chr(34), 'a.' + chr(34), 1)} = {ke.replace(chr(34), 'b.' + chr(34), 1)}"
            )

        # Simpler approach: use quoted column names directly for joins
        join_conds = []
        for col_name in columns:
            if case_sensitive:
                join_conds.append(f'a."{col_name}" = b."{col_name}"')
            else:
                join_conds.append(f'LOWER(a."{col_name}"::text) = LOWER(b."{col_name}"::text)')
        key_join = " AND ".join(join_conds)

        where_parts = ["a.ctid <> b.ctid"]
        if null_where:
            # Apply null filter to both aliases
            for col_name in columns:
                where_parts.append(f'a."{col_name}" IS NOT NULL')
                where_parts.append(f'b."{col_name}" IS NOT NULL')
        where_parts.append(
            f'ABS(EXTRACT(EPOCH FROM (a."{temporal_column}"::timestamp - '
            f'b."{temporal_column}"::timestamp))) <= {window_seconds}'
        )
        if filter_expression:
            where_parts.append(f"({filter_expression})")
        where = " AND ".join(where_parts)

        filter_where = ""
        if filter_expression:
            filter_where = f"WHERE ({filter_expression})"

        ", ".join(key_exprs)

        sql = f"""
            WITH temporal_dups AS (
                SELECT DISTINCT a.ctid as row_id
                FROM {table} a
                JOIN {table} b ON {key_join}
                WHERE {where}
            )
            SELECT
                (SELECT COUNT(*) FROM {table} {filter_where}) as total_rows,
                (SELECT COUNT(*) FROM temporal_dups) as duplicate_rows,
                0 as duplicate_groups,
                0 as max_group_size,
                ROUND(100.0 * ((SELECT COUNT(*) FROM {table} {filter_where}) -
                    (SELECT COUNT(*) FROM temporal_dups)) /
                    NULLIF((SELECT COUNT(*) FROM {table} {filter_where}), 0), 2) as uniqueness_rate"""

        violation_sql = f"""
            SELECT DISTINCT a.*
            FROM {table} a
            JOIN {table} b ON {key_join}
            WHERE {where}"""

        ", ".join([f'"{c}"' for c in columns])
        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
total_rows = df.count()
a = df.alias("a")
b = df.alias("b")
joined = a.join(b, [{" & ".join([f'F.col("a.{c}") == F.col("b.{c}")' for c in columns])}], "inner")
joined = joined.filter(F.col("a.{temporal_column}") != F.col("b.{temporal_column}"))
joined = joined.filter(
    F.abs(F.unix_timestamp(F.col("a.{temporal_column}")) - F.unix_timestamp(F.col("b.{temporal_column}"))) <= {window_seconds}
)
duplicate_rows = joined.select("a.*").distinct().count()
uniqueness_rate = ((total_rows - duplicate_rows) / total_rows * 100) if total_rows > 0 else 100
violations_df = joined.select("a.*").distinct()
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql,
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    # --- F087: Conformity check type constants and helpers ---

    CONFORMITY_STANDARDS = {
        # Technical / ISO names
        "iso_8601": r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:\d{2})?)?$",
        "e164": r"^\+[1-9]\d{1,14}$",
        "iso_4217": r"^[A-Z]{3}$",
        "iso_3166": r"^[A-Z]{2}$",
        "email_rfc5322": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
        "iban": r"^[A-Z]{2}\d{2}[A-Z0-9]{4,30}$",
        "url": r"^https?://[^\s/$.?#].[^\s]*$",
        "uuid": r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
        # UI-friendly aliases (used by the frontend dropdown)
        "email": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
        "phone": r"^\+?[\d\s\-\.\(\)]{7,}$",
        "date_iso": r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:\d{2})?)?$",
        "ip_address": r"^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$",
        "credit_card": r"^\d{13,19}$",
        "postal_code": r"^[A-Z0-9]{3,10}(-[A-Z0-9]{3,10})?$",
        "ssn": r"^\d{3}-\d{2}-\d{4}$",
    }

    VALID_CONFORMITY_TYPES = {
        "regex",
        "standard",
        "length",
        "charset",
        "case",
        "structural",
    }

    @staticmethod
    def _infer_conformity_type(parameters: dict[str, Any]) -> str:
        """Infer conformity_type from parameter keys for backward compatibility."""
        if parameters.get("regex_pattern"):
            return "regex"
        if parameters.get("standard_name"):
            return "standard"
        if parameters.get("min_length") is not None or parameters.get("max_length") is not None:
            return "length"
        if parameters.get("allowed_characters"):
            return "charset"
        if parameters.get("case_rule"):
            return "case"
        if parameters.get("structural_format"):
            return "structural"
        return "regex"

    @staticmethod
    def _conformity_null_handling_sql(column_expr: str, null_handling: str) -> tuple:
        """Return (where_clause, null_count_expr) based on null_handling mode.

        - skip (default): exclude nulls from total via WHERE IS NOT NULL
        - fail: no filter; nulls count as non-conforming (no CASE match)
        - pass: no filter; nulls count as conforming via COALESCE wrapper
        """
        if null_handling == "fail":
            return ("", "")
        elif null_handling == "pass":
            return ("", "pass")
        else:  # skip (default)
            return (f"WHERE {column_expr} IS NOT NULL", "")

    @staticmethod
    def _conformity_trim_sql(column: str, trim_whitespace: bool) -> str:
        """Wrap column in TRIM() if trim_whitespace is enabled."""
        if trim_whitespace:
            return f"TRIM({column})"
        return column

    @staticmethod
    def _conformity_error_result(message: str) -> dict[str, Any]:
        """Return a structured error for conformity compilation failures."""
        return {
            "error": message,
            "compiled_sql": f"-- ERROR: {message}",
            "compiled_postgres": f"-- ERROR: {message}",
            "compiled_spark": f"# ERROR: {message}",
        }

    def _compile_conformity_rule(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Compile conformity rule — dispatcher for all conformity types."""
        conformity_type = parameters.get("conformity_type")
        if not conformity_type:
            conformity_type = self._infer_conformity_type(parameters)

        if conformity_type not in self.VALID_CONFORMITY_TYPES:
            return self._conformity_error_result(
                f"Unknown conformity_type: {conformity_type}. "
                f"Allowed: {', '.join(sorted(self.VALID_CONFORMITY_TYPES))}"
            )

        filter_expression = parameters.get("filter_expression")
        if filter_expression and not self._validate_filter_expression(filter_expression):
            return self._conformity_error_result(
                "Invalid filter_expression — possible SQL injection"
            )

        columns = parameters.get("columns", [column] if column else [])
        col = columns[0] if columns else column

        dispatch = {
            "regex": self._conformity_regex,
            "standard": self._conformity_standard,
            "length": self._conformity_length,
            "charset": self._conformity_charset,
            "case": self._conformity_case,
            "structural": self._conformity_structural,
        }
        return dispatch[conformity_type](table, col, parameters)

    def _conformity_regex(
        self, table: str, column: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Conformity type: regex pattern matching."""
        pattern = parameters.get("regex_pattern") or parameters.get("pattern", "")
        if not pattern:
            return self._conformity_error_result(
                "regex conformity_type requires regex_pattern parameter"
            )

        null_handling = parameters.get("null_handling", "skip")
        trim_whitespace = parameters.get("trim_whitespace", True)
        filter_expression = parameters.get("filter_expression")

        col_ref = f'"{column}"'
        col_expr = self._conformity_trim_sql(col_ref, trim_whitespace)
        where_clause, null_mode = self._conformity_null_handling_sql(col_ref, null_handling)

        if filter_expression:
            if where_clause:
                where_clause += f" AND ({filter_expression})"
            else:
                where_clause = f"WHERE ({filter_expression})"

        # Build conforming CASE expression
        if null_mode == "pass":
            conform_case = f"CASE WHEN {col_ref} IS NULL OR {col_expr} ~ '{pattern}' THEN 1 END"
            non_conform_case = (
                f"CASE WHEN {col_ref} IS NOT NULL AND {col_expr} !~ '{pattern}' THEN 1 END"
            )
        else:
            conform_case = f"CASE WHEN {col_expr} ~ '{pattern}' THEN 1 END"
            non_conform_case = f"CASE WHEN {col_expr} !~ '{pattern}' THEN 1 END"

        sql = f"""
            SELECT
                COUNT(*) as total_rows,
                COUNT({conform_case}) as conforming_rows,
                COUNT({non_conform_case}) as non_conforming_rows
            FROM {table}
            {where_clause}
        """

        violation_sql = f"""
            SELECT *
            FROM {table}
            {where_clause}{"" if not where_clause else " AND"}{" WHERE" if not where_clause else ""} {col_expr} !~ '{pattern}'
        """

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
col_expr = {"F.trim(F.col('" + column + "'))" if trim_whitespace else "F.col('" + column + "')"}
{"df = df.filter(F.col('" + column + "').isNotNull())" if null_handling == "skip" else ""}
total_rows = df.count()
conforming_df = df.filter(col_expr.rlike('{pattern}'))
conforming_rows = conforming_df.count()
non_conforming_rows = total_rows - conforming_rows
conformity_rate = (conforming_rows / total_rows * 100) if total_rows > 0 else 100
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _conformity_standard(
        self, table: str, column: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Conformity type: named format standard from built-in library."""
        standard_name = parameters.get("standard_name", "")
        if not standard_name:
            return self._conformity_error_result(
                "standard conformity_type requires standard_name parameter"
            )
        if standard_name not in self.CONFORMITY_STANDARDS:
            return self._conformity_error_result(
                f"Unknown standard_name: {standard_name}. "
                f"Allowed: {', '.join(sorted(self.CONFORMITY_STANDARDS.keys()))}"
            )
        # Delegate to regex with the standard's pattern
        params = dict(parameters)
        params["regex_pattern"] = self.CONFORMITY_STANDARDS[standard_name]
        return self._conformity_regex(table, column, params)

    def _conformity_length(
        self, table: str, column: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Conformity type: string length constraints."""
        min_length = parameters.get("min_length")
        max_length = parameters.get("max_length")
        if min_length is None and max_length is None:
            return self._conformity_error_result(
                "length conformity_type requires min_length and/or max_length"
            )

        null_handling = parameters.get("null_handling", "skip")
        trim_whitespace = parameters.get("trim_whitespace", True)
        filter_expression = parameters.get("filter_expression")

        col_ref = f'"{column}"'
        col_expr = self._conformity_trim_sql(col_ref, trim_whitespace)
        len_expr = f"CHAR_LENGTH({col_expr})"
        where_clause, null_mode = self._conformity_null_handling_sql(col_ref, null_handling)

        if filter_expression:
            if where_clause:
                where_clause += f" AND ({filter_expression})"
            else:
                where_clause = f"WHERE ({filter_expression})"

        # Build condition parts
        conditions = []
        if min_length is not None:
            conditions.append(f"{len_expr} >= {int(min_length)}")
        if max_length is not None:
            conditions.append(f"{len_expr} <= {int(max_length)}")
        conform_cond = " AND ".join(conditions)

        if null_mode == "pass":
            conform_case = f"CASE WHEN {col_ref} IS NULL OR ({conform_cond}) THEN 1 END"
            non_conform_case = (
                f"CASE WHEN {col_ref} IS NOT NULL AND NOT ({conform_cond}) THEN 1 END"
            )
        else:
            conform_case = f"CASE WHEN {conform_cond} THEN 1 END"
            non_conform_case = f"CASE WHEN NOT ({conform_cond}) THEN 1 END"

        sql = f"""
            SELECT
                COUNT(*) as total_rows,
                COUNT({conform_case}) as conforming_rows,
                COUNT({non_conform_case}) as non_conforming_rows
            FROM {table}
            {where_clause}
        """

        violation_sql = f"""
            SELECT *
            FROM {table}
            {where_clause}{"" if not where_clause else " AND"}{" WHERE" if not where_clause else ""} NOT ({conform_cond})
        """

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
col_expr = {"F.length(F.trim(F.col('" + column + "')))" if trim_whitespace else "F.length(F.col('" + column + "'))"}
{"df = df.filter(F.col('" + column + "').isNotNull())" if null_handling == "skip" else ""}
total_rows = df.count()
conform_cond = {"(col_expr >= " + str(int(min_length)) + ")" if min_length is not None else "True"} & {"(col_expr <= " + str(int(max_length)) + ")" if max_length is not None else "True"}
conforming_rows = df.filter(conform_cond).count()
non_conforming_rows = total_rows - conforming_rows
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _conformity_charset(
        self, table: str, column: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Conformity type: character set validation."""
        allowed_characters = parameters.get("allowed_characters", "")
        if not allowed_characters:
            return self._conformity_error_result(
                "charset conformity_type requires allowed_characters parameter"
            )

        null_handling = parameters.get("null_handling", "skip")
        trim_whitespace = parameters.get("trim_whitespace", True)
        filter_expression = parameters.get("filter_expression")

        col_ref = f'"{column}"'
        col_expr = self._conformity_trim_sql(col_ref, trim_whitespace)
        charset_pattern = f"^[{allowed_characters}]*$"
        where_clause, null_mode = self._conformity_null_handling_sql(col_ref, null_handling)

        if filter_expression:
            if where_clause:
                where_clause += f" AND ({filter_expression})"
            else:
                where_clause = f"WHERE ({filter_expression})"

        if null_mode == "pass":
            conform_case = (
                f"CASE WHEN {col_ref} IS NULL OR {col_expr} ~ '{charset_pattern}' THEN 1 END"
            )
            non_conform_case = (
                f"CASE WHEN {col_ref} IS NOT NULL AND {col_expr} !~ '{charset_pattern}' THEN 1 END"
            )
        else:
            conform_case = f"CASE WHEN {col_expr} ~ '{charset_pattern}' THEN 1 END"
            non_conform_case = f"CASE WHEN {col_expr} !~ '{charset_pattern}' THEN 1 END"

        sql = f"""
            SELECT
                COUNT(*) as total_rows,
                COUNT({conform_case}) as conforming_rows,
                COUNT({non_conform_case}) as non_conforming_rows
            FROM {table}
            {where_clause}
        """

        violation_sql = f"""
            SELECT *
            FROM {table}
            {where_clause}{"" if not where_clause else " AND"}{" WHERE" if not where_clause else ""} {col_expr} !~ '{charset_pattern}'
        """

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
col_expr = {"F.trim(F.col('" + column + "'))" if trim_whitespace else "F.col('" + column + "')"}
{"df = df.filter(F.col('" + column + "').isNotNull())" if null_handling == "skip" else ""}
total_rows = df.count()
conforming_df = df.filter(col_expr.rlike('{charset_pattern}'))
conforming_rows = conforming_df.count()
non_conforming_rows = total_rows - conforming_rows
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _conformity_case(
        self, table: str, column: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Conformity type: case convention (upper, lower, title)."""
        case_rule = parameters.get("case_rule", "")
        if not case_rule:
            return self._conformity_error_result(
                "case conformity_type requires case_rule parameter"
            )

        case_functions = {"upper": "UPPER", "lower": "LOWER", "title": "INITCAP"}
        sql_func = case_functions.get(case_rule)
        if not sql_func:
            return self._conformity_error_result(
                f"Unknown case_rule: {case_rule}. Allowed: upper, lower, title"
            )

        null_handling = parameters.get("null_handling", "skip")
        trim_whitespace = parameters.get("trim_whitespace", True)
        filter_expression = parameters.get("filter_expression")

        col_ref = f'"{column}"'
        col_expr = self._conformity_trim_sql(col_ref, trim_whitespace)
        where_clause, null_mode = self._conformity_null_handling_sql(col_ref, null_handling)

        if filter_expression:
            if where_clause:
                where_clause += f" AND ({filter_expression})"
            else:
                where_clause = f"WHERE ({filter_expression})"

        if null_mode == "pass":
            conform_case = (
                f"CASE WHEN {col_ref} IS NULL OR {col_expr} = {sql_func}({col_expr}) THEN 1 END"
            )
            non_conform_case = f"CASE WHEN {col_ref} IS NOT NULL AND {col_expr} != {sql_func}({col_expr}) THEN 1 END"
        else:
            conform_case = f"CASE WHEN {col_expr} = {sql_func}({col_expr}) THEN 1 END"
            non_conform_case = f"CASE WHEN {col_expr} != {sql_func}({col_expr}) THEN 1 END"

        spark_func = {"upper": "F.upper", "lower": "F.lower", "title": "F.initcap"}[case_rule]

        sql = f"""
            SELECT
                COUNT(*) as total_rows,
                COUNT({conform_case}) as conforming_rows,
                COUNT({non_conform_case}) as non_conforming_rows
            FROM {table}
            {where_clause}
        """

        violation_sql = f"""
            SELECT *
            FROM {table}
            {where_clause}{"" if not where_clause else " AND"}{" WHERE" if not where_clause else ""} {col_expr} != {sql_func}({col_expr})
        """

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
col_expr = {"F.trim(F.col('" + column + "'))" if trim_whitespace else "F.col('" + column + "')"}
{"df = df.filter(F.col('" + column + "').isNotNull())" if null_handling == "skip" else ""}
total_rows = df.count()
conforming_df = df.filter(col_expr == {spark_func}(col_expr))
conforming_rows = conforming_df.count()
non_conforming_rows = total_rows - conforming_rows
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _conformity_structural(
        self, table: str, column: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Conformity type: structural format validation (JSON, XML)."""
        structural_format = parameters.get("structural_format", "")
        if not structural_format:
            return self._conformity_error_result(
                "structural conformity_type requires structural_format parameter"
            )

        null_handling = parameters.get("null_handling", "skip")
        filter_expression = parameters.get("filter_expression")

        col_ref = f'"{column}"'
        where_clause, null_mode = self._conformity_null_handling_sql(col_ref, null_handling)

        if filter_expression:
            if where_clause:
                where_clause += f" AND ({filter_expression})"
            else:
                where_clause = f"WHERE ({filter_expression})"

        if structural_format == "json":
            if null_mode == "pass":
                conform_case = f"CASE WHEN {col_ref} IS NULL OR ({col_ref} IS NOT NULL AND {col_ref}::json IS NOT NULL) THEN 1 END"
                non_conform_case = (
                    f"CASE WHEN {col_ref} IS NOT NULL AND {col_ref}::json IS NULL THEN 1 END"
                )
            else:
                conform_case = f"CASE WHEN {col_ref}::json IS NOT NULL THEN 1 END"
                non_conform_case = f"CASE WHEN {col_ref}::json IS NULL THEN 1 END"

            spark_parse = "F.from_json(F.col('" + column + "'), 'MAP<STRING,STRING>')"
        elif structural_format == "xml":
            if null_mode == "pass":
                conform_case = f"CASE WHEN {col_ref} IS NULL OR XMLPARSE(DOCUMENT {col_ref}) IS NOT NULL THEN 1 END"
                non_conform_case = f"CASE WHEN {col_ref} IS NOT NULL AND XMLPARSE(DOCUMENT {col_ref}) IS NULL THEN 1 END"
            else:
                conform_case = f"CASE WHEN XMLPARSE(DOCUMENT {col_ref}) IS NOT NULL THEN 1 END"
                non_conform_case = f"CASE WHEN XMLPARSE(DOCUMENT {col_ref}) IS NULL THEN 1 END"
            spark_parse = "# XML parsing requires custom UDF"
        else:
            return self._conformity_error_result(
                f"Unknown structural_format: {structural_format}. Allowed: json, xml"
            )

        sql = f"""
            SELECT
                COUNT(*) as total_rows,
                COUNT({conform_case}) as conforming_rows,
                COUNT({non_conform_case}) as non_conforming_rows
            FROM {table}
            {where_clause}
        """

        violation_sql = f"""
            SELECT *
            FROM {table}
            {where_clause}{"" if not where_clause else " AND"}{" WHERE" if not where_clause else ""} {non_conform_case.replace("CASE WHEN ", "").replace(" THEN 1 END", "")}
        """

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
{"df = df.filter(F.col('" + column + "').isNotNull())" if null_handling == "skip" else ""}
total_rows = df.count()
parsed = {spark_parse}
conforming_df = df.filter(parsed.isNotNull())
conforming_rows = conforming_df.count()
non_conforming_rows = total_rows - conforming_rows
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    # ── F088 Consistency constants ──────────────────────────────────
    VALID_CONSISTENCY_TYPES = {
        "intra_record",
        "formula",
        "temporal",
        "inter_record",
        "cross_table",
        "aggregation",
    }
    VALID_AGGREGATION_FUNCTIONS = {"SUM", "COUNT", "AVG", "MIN", "MAX"}
    VALID_TEMPORAL_OPERATORS = {">=", ">", "<=", "<", "="}

    @staticmethod
    def _infer_consistency_type(parameters: dict[str, Any]) -> str:
        if parameters.get("aggregation_function"):
            return "aggregation"
        if parameters.get("comparison_dataset") and parameters.get("join_keys"):
            return "cross_table"
        if parameters.get("group_by_columns") and parameters.get("comparison_columns"):
            return "inter_record"
        if parameters.get("comparison_column"):
            return "temporal"
        if parameters.get("expected_column"):
            return "formula"
        if parameters.get("reference_column"):
            return "intra_record"
        return "intra_record"

    @staticmethod
    def _consistency_null_handling_sql(
        columns: list[str], null_handling: str, table_alias: str = ""
    ) -> tuple:
        prefix = f'{table_alias}."' if table_alias else '"'
        suffix = '"'
        col_refs = [f"{prefix}{c}{suffix}" for c in columns]
        if null_handling == "skip":
            return " AND ".join(f"{c} IS NOT NULL" for c in col_refs), "skip"
        elif null_handling == "pass":
            return "", "pass"
        return "", "fail"

    @staticmethod
    def _consistency_tolerance_sql(
        actual_expr: str, expected_expr: str, tolerance_type: str, tolerance_value
    ) -> tuple:
        if tolerance_type == "none":
            match = f"({actual_expr}) = ({expected_expr})"
            mismatch = f"({actual_expr}) != ({expected_expr})"
        elif tolerance_type == "percentage":
            tol = tolerance_value if tolerance_value is not None else 1.0
            match = f"ABS(({actual_expr}) - ({expected_expr})) / NULLIF(ABS(({expected_expr})), 0) * 100 <= {tol}"
            mismatch = f"ABS(({actual_expr}) - ({expected_expr})) / NULLIF(ABS(({expected_expr})), 0) * 100 > {tol}"
        else:
            tol = tolerance_value if tolerance_value is not None else 0.01
            match = f"ABS(({actual_expr}) - ({expected_expr})) <= {tol}"
            mismatch = f"ABS(({actual_expr}) - ({expected_expr})) > {tol}"
        return match, mismatch

    @staticmethod
    def _consistency_error_result(message: str) -> dict[str, str]:
        return {
            "compiled_sql": f"-- ERROR: {message}",
            "compiled_postgres": f"-- ERROR: {message}",
            "compiled_spark": f"# ERROR: {message}",
            "violation_sql": f"-- ERROR: {message}",
            "error": message,
        }

    def _compile_consistency_rule(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Compile consistency rule — dispatches to per-type helpers."""
        consistency_type = parameters.get("consistency_type")
        if not consistency_type:
            consistency_type = self._infer_consistency_type(parameters)

        if consistency_type not in self.VALID_CONSISTENCY_TYPES:
            return self._consistency_error_result(f"Unknown consistency_type: {consistency_type}")

        filter_expr = parameters.get("filter_expression")
        if filter_expr and not self._validate_filter_expression(filter_expr):
            return self._consistency_error_result("Dangerous filter_expression rejected")

        rule_expr = parameters.get("rule_expression")
        if rule_expr and not self._validate_filter_expression(rule_expr):
            return self._consistency_error_result("Dangerous rule_expression rejected")

        router = {
            "intra_record": self._consistency_intra_record,
            "formula": self._consistency_formula,
            "temporal": self._consistency_temporal,
            "inter_record": self._consistency_inter_record,
            "cross_table": self._consistency_cross_table,
            "aggregation": self._consistency_aggregation,
        }
        return router[consistency_type](table, column, parameters)

    # ── Intra-record ─────────────────────────────────────────────
    def _consistency_intra_record(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        rule_expr = params.get("rule_expression")
        if not rule_expr:
            # backward compat: reference_column + operator
            ref_col = params.get("reference_column")
            if ref_col:
                op = params.get("operator", "=")
                rule_expr = f'"{column}" {op} "{ref_col}"'
            else:
                return self._consistency_error_result("intra_record requires rule_expression")

        null_handling = params.get("null_handling", "fail")
        filter_expr = params.get("filter_expression")

        where_parts = []
        if null_handling == "skip":
            cols = params.get("columns", [column])
            null_cond, _ = self._consistency_null_handling_sql(cols, "skip")
            if null_cond:
                where_parts.append(null_cond)
        if filter_expr:
            where_parts.append(f"({filter_expr})")
        where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        if null_handling == "pass":
            expr_check = f"COALESCE(({rule_expr}), TRUE)"
        else:
            expr_check = rule_expr

        sql = (
            f"SELECT COUNT(*) as total_rows, "
            f"COUNT(CASE WHEN ({expr_check}) THEN 1 END) as consistent_rows, "
            f"COUNT(CASE WHEN NOT ({expr_check}) THEN 1 END) as inconsistent_rows "
            f"FROM {table} {where_clause}"
        )

        violation_sql = f"SELECT * FROM {table} WHERE NOT ({rule_expr})"
        if filter_expr:
            violation_sql += f" AND ({filter_expr})"

        spark_code = (
            f"from pyspark.sql.functions import expr, count, when, lit\n"
            f"result = df.select(\n"
            f'    count(lit(1)).alias("total_rows"),\n'
            f'    count(when(expr("{rule_expr}"), lit(1))).alias("consistent_rows"),\n'
            f'    count(when(~expr("{rule_expr}"), lit(1))).alias("inconsistent_rows")\n'
            f")"
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    # ── Formula ──────────────────────────────────────────────────
    def _consistency_formula(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        rule_expr = params.get("rule_expression") or params.get("formula")
        if not rule_expr:
            return self._consistency_error_result("formula requires rule_expression")
        expected_col = params.get("expected_column")
        if not expected_col:
            return self._consistency_error_result("formula requires expected_column")

        # Many LLMs emit the rule as a full equation "<expected_col> = <rhs>"
        # rather than just the right-hand side. Strip the LHS when it matches
        # the expected column so the compiler receives the bare RHS.
        import re as _re

        _re_lhs = _re.compile(r'^\s*"?\s*' + _re.escape(expected_col) + r'\s*"?\s*=(?!=)\s*')
        rule_expr = _re_lhs.sub("", str(rule_expr)).strip()

        tol_type = params.get("tolerance_type", "absolute")
        tol_val = params.get("tolerance_value")
        null_handling = params.get("null_handling", "fail")
        filter_expr = params.get("filter_expression")

        actual_expr = f'"{expected_col}"'
        formula_expr = f"({rule_expr})"
        match_cond, mismatch_cond = self._consistency_tolerance_sql(
            actual_expr, formula_expr, tol_type, tol_val
        )

        where_parts = []
        if null_handling == "skip":
            where_parts.append(f'"{expected_col}" IS NOT NULL')
        if filter_expr:
            where_parts.append(f"({filter_expr})")
        where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        if null_handling == "pass":
            match_cond = f"COALESCE(({match_cond}), TRUE)"
            mismatch_cond = f"NOT COALESCE(({match_cond}), TRUE)"

        sql = (
            f"SELECT COUNT(*) as total_rows, "
            f"COUNT(CASE WHEN {match_cond} THEN 1 END) as consistent_rows, "
            f"COUNT(CASE WHEN {mismatch_cond} THEN 1 END) as inconsistent_rows "
            f"FROM {table} {where_clause}"
        )

        violation_sql = f"SELECT * FROM {table} WHERE {mismatch_cond}"
        if filter_expr:
            violation_sql += f" AND ({filter_expr})"

        tol = tol_val if tol_val is not None else (1.0 if tol_type == "percentage" else 0.01)
        spark_code = (
            f"from pyspark.sql.functions import expr, col, count, when, lit, abs as spark_abs\n"
            f'result = df.withColumn("_expected", expr("{rule_expr}")).select(\n'
            f'    count(lit(1)).alias("total_rows"),\n'
            f'    count(when(spark_abs(col("{expected_col}") - col("_expected")) <= {tol}, lit(1))).alias("consistent_rows"),\n'
            f'    count(when(spark_abs(col("{expected_col}") - col("_expected")) > {tol}, lit(1))).alias("inconsistent_rows")\n'
            f")"
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    # ── Temporal ─────────────────────────────────────────────────
    def _consistency_temporal(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        # Accept LLM aliases: comparison_column may be emitted as
        # right_column / start_column / end_column / reference_column.
        comp_col = (
            params.get("comparison_column")
            or params.get("right_column")
            or params.get("start_column")
            or params.get("reference_column")
        )
        # When start_column equals the target column, the comparison column
        # is end_column instead.
        if comp_col == column:
            comp_col = params.get("end_column") or comp_col
        if not comp_col:
            return self._consistency_error_result("temporal requires comparison_column")

        # Map word-form operators to symbols (LLMs often emit "greater_equal" etc.).
        _op_map = {
            "greater_equal": ">=",
            "greater": ">",
            "less_equal": "<=",
            "less": "<",
            "equal": "=",
            "equals": "=",
            "gte": ">=",
            "gt": ">",
            "lte": "<=",
            "lt": "<",
            "eq": "=",
            ">=": ">=",
            ">": ">",
            "<=": "<=",
            "<": "<",
            "=": "=",
        }
        raw_op = params.get("operator", ">=")
        op = _op_map.get(str(raw_op).lower(), ">=")
        if op not in self.VALID_TEMPORAL_OPERATORS:
            op = ">="
        null_handling = params.get("null_handling", "fail")
        filter_expr = params.get("filter_expression")

        # Build inverse operator for inconsistent counting
        inverse_ops = {">=": "<", ">": "<=", "<=": ">", "<": ">=", "=": "!="}
        inv_op = inverse_ops.get(op, "!=")

        where_parts = []
        if null_handling == "skip":
            where_parts.append(f'"{column}" IS NOT NULL AND "{comp_col}" IS NOT NULL')
        if filter_expr:
            where_parts.append(f"({filter_expr})")
        where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        match_expr = f'"{column}" {op} "{comp_col}"'
        mismatch_expr = f'"{column}" {inv_op} "{comp_col}"'
        if null_handling == "pass":
            match_expr = f'COALESCE(("{column}" {op} "{comp_col}"), TRUE)'
            mismatch_expr = f'NOT COALESCE(("{column}" {op} "{comp_col}"), TRUE)'

        sql = (
            f"SELECT COUNT(*) as total_rows, "
            f"COUNT(CASE WHEN {match_expr} THEN 1 END) as consistent_rows, "
            f"COUNT(CASE WHEN {mismatch_expr} THEN 1 END) as inconsistent_rows "
            f"FROM {table} {where_clause}"
        )

        violation_sql = f'SELECT * FROM {table} WHERE "{column}" {inv_op} "{comp_col}"'
        if filter_expr:
            violation_sql += f" AND ({filter_expr})"

        spark_code = (
            f"from pyspark.sql.functions import col, count, when, lit\n"
            f"result = df.select(\n"
            f'    count(lit(1)).alias("total_rows"),\n'
            f'    count(when(col("{column}") {op} col("{comp_col}"), lit(1))).alias("consistent_rows"),\n'
            f'    count(when(col("{column}") {inv_op} col("{comp_col}"), lit(1))).alias("inconsistent_rows")\n'
            f")"
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    # ── Inter-record ─────────────────────────────────────────────
    def _consistency_inter_record(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        group_cols = params.get("group_by_columns")
        if not group_cols:
            return self._consistency_error_result("inter_record requires group_by_columns")
        comp_cols = params.get("comparison_columns")
        if not comp_cols:
            return self._consistency_error_result("inter_record requires comparison_columns")

        null_handling = params.get("null_handling", "fail")
        filter_expr = params.get("filter_expression")

        comp_col = comp_cols[0]  # MVP: first comparison column
        group_by_quoted = ", ".join(f'"{c}"' for c in group_cols)

        where_parts = []
        if null_handling == "skip":
            where_parts.append(f'"{comp_col}" IS NOT NULL')
        if filter_expr:
            where_parts.append(f"({filter_expr})")
        where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        sql = (
            f"WITH group_stats AS ("
            f"SELECT {group_by_quoted}, "
            f'COUNT(DISTINCT "{comp_col}") as distinct_vals, '
            f"COUNT(*) as group_size "
            f"FROM {table} {where_clause} "
            f"GROUP BY {group_by_quoted}"
            f") "
            f"SELECT "
            f"SUM(group_size) as total_rows, "
            f"SUM(CASE WHEN distinct_vals <= 1 THEN group_size ELSE 0 END) as consistent_rows, "
            f"SUM(CASE WHEN distinct_vals > 1 THEN group_size ELSE 0 END) as inconsistent_rows "
            f"FROM group_stats"
        )

        violation_sql = (
            f"WITH group_stats AS ("
            f"SELECT {group_by_quoted}, "
            f'COUNT(DISTINCT "{comp_col}") as distinct_vals '
            f"FROM {table} {where_clause} "
            f"GROUP BY {group_by_quoted}"
            f") "
            f"SELECT t.* FROM {table} t "
            f"INNER JOIN group_stats g ON "
            + " AND ".join(f't."{c}" = g."{c}"' for c in group_cols)
            + " WHERE g.distinct_vals > 1"
        )

        spark_code = (
            f"from pyspark.sql.functions import col, count, countDistinct, when, lit, sum as spark_sum\n"
            f"group_stats = df.groupBy({[c for c in group_cols]}).agg(\n"
            f'    countDistinct("{comp_col}").alias("distinct_vals"),\n'
            f'    count(lit(1)).alias("group_size")\n'
            f")\n"
            f"result = group_stats.select(\n"
            f'    spark_sum("group_size").alias("total_rows"),\n'
            f'    spark_sum(when(col("distinct_vals") <= 1, col("group_size")).otherwise(0)).alias("consistent_rows"),\n'
            f'    spark_sum(when(col("distinct_vals") > 1, col("group_size")).otherwise(0)).alias("inconsistent_rows")\n'
            f")"
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    # ── Cross-table ──────────────────────────────────────────────
    def _consistency_cross_table(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        comp_dataset = params.get("comparison_dataset")
        if not comp_dataset:
            return self._consistency_error_result("cross_table requires comparison_dataset")
        join_keys = params.get("join_keys")
        if not join_keys:
            return self._consistency_error_result("cross_table requires join_keys")
        comp_cols = params.get("comparison_columns")
        if not comp_cols:
            return self._consistency_error_result("cross_table requires comparison_columns")

        filter_expr = params.get("filter_expression")

        join_conditions = " AND ".join(f'a."{k}" = b."{k}"' for k in join_keys)
        all_match = " AND ".join(f'a."{c}" = b."{c}"' for c in comp_cols)

        where_clause = ""
        if filter_expr:
            where_clause = f"WHERE ({filter_expr})"

        sql = (
            f"SELECT COUNT(*) as total_rows, "
            f"COUNT(CASE WHEN {all_match} THEN 1 END) as consistent_rows, "
            f"COUNT(CASE WHEN NOT ({all_match}) THEN 1 END) as inconsistent_rows "
            f"FROM {table} a "
            f"INNER JOIN {comp_dataset} b ON {join_conditions} {where_clause}"
        )

        violation_sql = (
            f"SELECT a.* FROM {table} a "
            f"INNER JOIN {comp_dataset} b ON {join_conditions} "
            f"WHERE NOT ({all_match})"
        )
        if filter_expr:
            violation_sql += f" AND ({filter_expr})"

        spark_code = (
            f"from pyspark.sql.functions import col, count, when, lit\n"
            f'joined = df.alias("a").join(df2.alias("b"), {[k for k in join_keys]}, "inner")\n'
            f"match_cond = "
            + " & ".join(f'(col("a.{c}") == col("b.{c}"))' for c in comp_cols)
            + "\n"
            "result = joined.select(\n"
            '    count(lit(1)).alias("total_rows"),\n'
            '    count(when(match_cond, lit(1))).alias("consistent_rows"),\n'
            '    count(when(~match_cond, lit(1))).alias("inconsistent_rows")\n'
            ")"
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    # ── Aggregation ──────────────────────────────────────────────
    def _consistency_aggregation(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        group_cols = params.get("group_by_columns")
        if not group_cols:
            return self._consistency_error_result("aggregation requires group_by_columns")
        agg_func = params.get("aggregation_function")
        if not agg_func:
            return self._consistency_error_result("aggregation requires aggregation_function")
        agg_func_upper = agg_func.upper()
        if agg_func_upper not in self.VALID_AGGREGATION_FUNCTIONS:
            return self._consistency_error_result(f"Invalid aggregation_function: {agg_func}")
        expected_col = params.get("expected_column")
        if not expected_col:
            return self._consistency_error_result("aggregation requires expected_column")

        tol_type = params.get("tolerance_type", "absolute")
        tol_val = params.get("tolerance_value")
        filter_expr = params.get("filter_expression")
        comp_dataset = params.get("comparison_dataset")

        group_by_quoted = ", ".join(f'"{c}"' for c in group_cols)

        where_clause = ""
        if filter_expr:
            where_clause = f"WHERE ({filter_expr})"

        expected_table = comp_dataset if comp_dataset else table

        match_cond, mismatch_cond = self._consistency_tolerance_sql(
            "a.computed_value", f'h."{expected_col}"', tol_type, tol_val
        )

        join_on = " AND ".join(f'a."{c}" = h."{c}"' for c in group_cols)

        sql = (
            f"WITH agg AS ("
            f'SELECT {group_by_quoted}, {agg_func_upper}("{column}") as computed_value '
            f"FROM {table} {where_clause} "
            f"GROUP BY {group_by_quoted}"
            f"), "
            f"header AS ("
            f'SELECT DISTINCT {group_by_quoted}, "{expected_col}" '
            f"FROM {expected_table}"
            f") "
            f"SELECT COUNT(*) as total_rows, "
            f"COUNT(CASE WHEN {match_cond} THEN 1 END) as consistent_rows, "
            f"COUNT(CASE WHEN {mismatch_cond} THEN 1 END) as inconsistent_rows "
            f"FROM agg a JOIN header h ON {join_on}"
        )

        violation_sql = (
            f"WITH agg AS ("
            f'SELECT {group_by_quoted}, {agg_func_upper}("{column}") as computed_value '
            f"FROM {table} {where_clause} "
            f"GROUP BY {group_by_quoted}"
            f"), "
            f"header AS ("
            f'SELECT DISTINCT {group_by_quoted}, "{expected_col}" '
            f"FROM {expected_table}"
            f") "
            f'SELECT a.*, h."{expected_col}" as expected_value '
            f"FROM agg a JOIN header h ON {join_on} "
            f"WHERE {mismatch_cond}"
        )

        tol = tol_val if tol_val is not None else (1.0 if tol_type == "percentage" else 0.01)
        spark_code = (
            f"from pyspark.sql.functions import col, count, when, lit, abs as spark_abs\n"
            f"from pyspark.sql.functions import sum as spark_sum, avg as spark_avg, min as spark_min, max as spark_max\n"
            f"agg_df = df.groupBy({[c for c in group_cols]}).agg(\n"
            f'    {agg_func.lower()}("{column}").alias("computed_value")\n'
            f")\n"
            f'header_df = {"df2" if comp_dataset else "df"}.select({[c for c in group_cols]} + ["{expected_col}"]).distinct()\n'
            f"compared = agg_df.join(header_df, {[c for c in group_cols]})\n"
            f"result = compared.select(\n"
            f'    count(lit(1)).alias("total_rows"),\n'
            f'    count(when(spark_abs(col("computed_value") - col("{expected_col}")) <= {tol}, lit(1))).alias("consistent_rows"),\n'
            f'    count(when(spark_abs(col("computed_value") - col("{expected_col}")) > {tol}, lit(1))).alias("inconsistent_rows")\n'
            f")"
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    # ── Timeliness constants ────────────────────────────────────────
    VALID_TIMELINESS_TYPES = {
        "freshness",
        "record_age",
        "latency",
        "processing_delay",
        "delivery_window",
        "heartbeat",
    }
    VALID_METRIC_TYPES = {"max", "avg", "p95", "p99"}
    DATASET_LEVEL_TYPES = {"freshness", "delivery_window", "heartbeat"}
    ROW_LEVEL_TYPES = {"record_age", "latency", "processing_delay"}

    @staticmethod
    def _parse_duration_to_seconds(value) -> int | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return int(value)
        s = str(value).strip()
        # Try numeric string
        try:
            return int(float(s))
        except (ValueError, TypeError):
            pass
        m = re.match(r"^(\d+(?:\.\d+)?)\s*(m|h|d)$", s, re.IGNORECASE)
        if not m:
            return None
        num = float(m.group(1))
        unit = m.group(2).lower()
        if unit == "m":
            return int(num * 60)
        elif unit == "h":
            return int(num * 3600)
        elif unit == "d":
            return int(num * 86400)
        return None

    @staticmethod
    def _parse_window_time(value) -> int | None:
        if value is None:
            return None
        s = str(value).strip()
        m = re.match(r"^(\d{1,2}):(\d{2})$", s)
        if not m:
            return None
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 23 or mi > 59:
            return None
        return h * 60 + mi

    @staticmethod
    def _infer_timeliness_type(parameters: dict[str, Any]) -> str:
        if parameters.get("comparison_timestamp"):
            return "latency"
        if parameters.get("delivery_window_start"):
            return "delivery_window"
        if parameters.get("expected_frequency"):
            return "heartbeat"
        return "freshness"

    @staticmethod
    def _timeliness_null_handling_sql(columns: list, null_handling: str) -> tuple:
        col_refs = [f'"{c}"' for c in columns]
        if null_handling == "skip":
            return " AND ".join(f"{c} IS NOT NULL" for c in col_refs), "skip"
        elif null_handling == "pass":
            return "", "pass"
        return "", "fail"

    @staticmethod
    def _timeliness_error_result(message: str) -> dict[str, str]:
        return {
            "compiled_sql": f"-- ERROR: {message}",
            "compiled_postgres": f"-- ERROR: {message}",
            "compiled_spark": f"# ERROR: {message}",
            "violation_sql": f"-- ERROR: {message}",
            "error": message,
        }

    def _compile_timeliness_rule(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        timeliness_type = parameters.get("timeliness_type") or self._infer_timeliness_type(
            parameters
        )
        if timeliness_type not in self.VALID_TIMELINESS_TYPES:
            return self._timeliness_error_result(f"Unknown timeliness type: {timeliness_type}")

        # Validate filter_expression
        filter_expr = parameters.get("filter_expression")
        if filter_expr and not self._validate_filter_expression(filter_expr):
            return self._timeliness_error_result(
                f"Dangerous filter expression rejected: {filter_expr}"
            )

        handlers = {
            "freshness": self._timeliness_freshness,
            "record_age": self._timeliness_record_age,
            "latency": self._timeliness_latency,
            "processing_delay": self._timeliness_processing_delay,
            "delivery_window": self._timeliness_delivery_window,
            "heartbeat": self._timeliness_heartbeat,
        }
        return handlers[timeliness_type](table, column, parameters)

    def _timeliness_freshness(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        ts_col = params.get("timestamp_column", column)
        max_age = params.get("max_age")
        if not ts_col:
            return self._timeliness_error_result(
                "timestamp_column is required for freshness checks"
            )
        max_seconds = self._parse_duration_to_seconds(max_age)
        if max_seconds is None:
            return self._timeliness_error_result(
                f"max_age is required for freshness checks (got: {max_age})"
            )

        filter_expr = params.get("filter_expression")
        where = f"WHERE {filter_expr}" if filter_expr else ""

        sql = (
            f"SELECT COUNT(*) AS total_rows, "
            f'MAX("{ts_col}") AS most_recent, '
            f'EXTRACT(EPOCH FROM (NOW() - MAX("{ts_col}"))) AS age_seconds, '
            f'CASE WHEN EXTRACT(EPOCH FROM (NOW() - MAX("{ts_col}"))) <= {max_seconds} '
            f"THEN COUNT(*) ELSE 0 END AS timely_rows, "
            f'CASE WHEN EXTRACT(EPOCH FROM (NOW() - MAX("{ts_col}"))) > {max_seconds} '
            f"THEN COUNT(*) ELSE 0 END AS untimely_rows "
            f"FROM {table} {where}"
        ).strip()

        spark_code = (
            f"from pyspark.sql import functions as F\n"
            f'result = df.agg(F.max(F.col("{ts_col}")).alias("most_recent")).collect()[0]\n'
            f'import datetime; age = (datetime.datetime.now() - result["most_recent"]).total_seconds()\n'
            f"timely = age <= {max_seconds}"
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": "",
        }

    def _timeliness_record_age(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        ts_col = params.get("timestamp_column", column)
        max_age = params.get("max_age")
        if not ts_col:
            return self._timeliness_error_result(
                "timestamp_column is required for record_age checks"
            )
        max_seconds = self._parse_duration_to_seconds(max_age)
        if max_seconds is None:
            return self._timeliness_error_result(
                f"max_age is required for record_age checks (got: {max_age})"
            )

        null_handling = params.get("null_handling", "fail")
        filter_expr = params.get("filter_expression")
        null_cond, null_mode = self._timeliness_null_handling_sql([ts_col], null_handling)

        where_parts = []
        if null_cond:
            where_parts.append(null_cond)
        if filter_expr:
            where_parts.append(f"({filter_expr})")
        where = "WHERE " + " AND ".join(where_parts) if where_parts else ""

        age_expr = f'EXTRACT(EPOCH FROM (NOW() - "{ts_col}"))'
        if null_mode == "pass":
            timely = f'SUM(CASE WHEN "{ts_col}" IS NULL OR {age_expr} <= {max_seconds} THEN 1 ELSE 0 END)'
            untimely = f'SUM(CASE WHEN "{ts_col}" IS NOT NULL AND {age_expr} > {max_seconds} THEN 1 ELSE 0 END)'
        else:
            timely = f"SUM(CASE WHEN {age_expr} <= {max_seconds} THEN 1 ELSE 0 END)"
            untimely = f"SUM(CASE WHEN {age_expr} > {max_seconds} THEN 1 ELSE 0 END)"

        sql = (
            f"SELECT COUNT(*) AS total_rows, "
            f"{timely} AS timely_rows, "
            f"{untimely} AS untimely_rows "
            f"FROM {table} {where}"
        ).strip()

        violation_sql = (
            f"SELECT *, {age_expr} AS record_age_seconds "
            f"FROM {table} "
            f"WHERE {age_expr} > {max_seconds}"
        )

        spark_code = (
            f"from pyspark.sql import functions as F\n"
            f'df2 = df.withColumn("_age_s", F.unix_timestamp(F.current_timestamp()) - F.unix_timestamp(F.col("{ts_col}")))\n'
            f'timely = df2.filter(F.col("_age_s") <= {max_seconds}).count()\n'
            f'untimely = df2.filter(F.col("_age_s") > {max_seconds}).count()'
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _timeliness_latency(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        return self._timeliness_delay_common(table, column, params, "latency")

    def _timeliness_processing_delay(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        return self._timeliness_delay_common(table, column, params, "processing_delay")

    def _timeliness_delay_common(
        self, table: str, column: str, params: dict[str, Any], delay_type: str
    ) -> dict[str, str]:
        ts_col = params.get("timestamp_column", column)
        comp_col = params.get("comparison_timestamp")
        max_age = params.get("max_age")
        if not comp_col:
            return self._timeliness_error_result(
                f"comparison_timestamp is required for {delay_type} checks"
            )
        if not ts_col:
            return self._timeliness_error_result(
                f"timestamp_column is required for {delay_type} checks"
            )
        max_seconds = self._parse_duration_to_seconds(max_age)
        if max_seconds is None:
            return self._timeliness_error_result(
                f"max_age is required for {delay_type} checks (got: {max_age})"
            )

        null_handling = params.get("null_handling", "fail")
        filter_expr = params.get("filter_expression")
        null_cond, null_mode = self._timeliness_null_handling_sql([ts_col, comp_col], null_handling)

        where_parts = []
        if null_cond:
            where_parts.append(null_cond)
        if filter_expr:
            where_parts.append(f"({filter_expr})")
        where = "WHERE " + " AND ".join(where_parts) if where_parts else ""

        # Use ABS so the check is robust to LLMs swapping start/end column
        # roles (e.g. processed_ts vs load_ts ordering).
        delay_expr = f'ABS(EXTRACT(EPOCH FROM ("{comp_col}" - "{ts_col}")))'
        if null_mode == "pass":
            timely = f'SUM(CASE WHEN "{ts_col}" IS NULL OR "{comp_col}" IS NULL OR {delay_expr} <= {max_seconds} THEN 1 ELSE 0 END)'
            untimely = f'SUM(CASE WHEN "{ts_col}" IS NOT NULL AND "{comp_col}" IS NOT NULL AND {delay_expr} > {max_seconds} THEN 1 ELSE 0 END)'
        else:
            timely = f"SUM(CASE WHEN {delay_expr} <= {max_seconds} THEN 1 ELSE 0 END)"
            untimely = f"SUM(CASE WHEN {delay_expr} > {max_seconds} THEN 1 ELSE 0 END)"

        sql = (
            f"SELECT COUNT(*) AS total_rows, "
            f"{timely} AS timely_rows, "
            f"{untimely} AS untimely_rows "
            f"FROM {table} {where}"
        ).strip()

        violation_sql = (
            f"SELECT *, {delay_expr} AS delay_seconds "
            f"FROM {table} "
            f"WHERE {delay_expr} > {max_seconds}"
        )

        spark_code = (
            f"from pyspark.sql import functions as F\n"
            f'df2 = df.withColumn("_delay_s", F.unix_timestamp(F.col("{comp_col}")) - F.unix_timestamp(F.col("{ts_col}")))\n'
            f'timely = df2.filter(F.col("_delay_s") <= {max_seconds}).count()\n'
            f'untimely = df2.filter(F.col("_delay_s") > {max_seconds}).count()'
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _timeliness_delivery_window(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        ts_col = params.get("timestamp_column", column)
        window_start = params.get("delivery_window_start")
        window_end = params.get("delivery_window_end")
        if not ts_col:
            return self._timeliness_error_result(
                "timestamp_column is required for delivery_window checks"
            )

        start_min = self._parse_window_time(window_start)
        if start_min is None:
            return self._timeliness_error_result(
                f"delivery_window_start is required and must be HH:MM format (got: {window_start})"
            )
        end_min = self._parse_window_time(window_end)
        if end_min is None:
            return self._timeliness_error_result(
                f"delivery_window_end is required and must be HH:MM format (got: {window_end})"
            )

        filter_expr = params.get("filter_expression")
        where = f"WHERE {filter_expr}" if filter_expr else ""

        # Per-row check: each row's timestamp must fall inside the window.
        per_row_minutes = f'EXTRACT(HOUR FROM "{ts_col}") * 60 + EXTRACT(MINUTE FROM "{ts_col}")'
        in_window = f"({per_row_minutes} BETWEEN {start_min} AND {end_min})"

        sql = (
            f"SELECT COUNT(*) AS total_rows, "
            f'MAX("{ts_col}") AS most_recent, '
            f"SUM(CASE WHEN {in_window} THEN 1 ELSE 0 END) AS timely_rows, "
            f"SUM(CASE WHEN NOT {in_window} THEN 1 ELSE 0 END) AS untimely_rows "
            f"FROM {table} {where}"
        ).strip()

        spark_code = (
            f"from pyspark.sql import functions as F\n"
            f'result = df.agg(F.max(F.col("{ts_col}")).alias("most_recent")).collect()[0]\n'
            f'mr = result["most_recent"]\n'
            f"minutes = mr.hour * 60 + mr.minute\n"
            f"timely = {start_min} <= minutes <= {end_min}"
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": "",
        }

    def _timeliness_heartbeat(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        ts_col = params.get("timestamp_column", column)
        expected_freq = params.get("expected_frequency")
        if not ts_col:
            return self._timeliness_error_result(
                "timestamp_column is required for heartbeat checks"
            )
        freq_seconds = self._parse_duration_to_seconds(expected_freq)
        if freq_seconds is None:
            return self._timeliness_error_result(
                f"expected_frequency is required for heartbeat checks (got: {expected_freq})"
            )

        filter_expr = params.get("filter_expression")
        where = f"WHERE {filter_expr}" if filter_expr else ""

        sql = (
            f"SELECT 1 AS total_rows, "
            f'MAX("{ts_col}") AS most_recent, '
            f"CASE WHEN COUNT(*) > 0 "
            f'AND EXTRACT(EPOCH FROM (NOW() - MAX("{ts_col}"))) <= {freq_seconds} '
            f"THEN 1 ELSE 0 END AS timely_rows, "
            f"CASE WHEN COUNT(*) = 0 "
            f'OR EXTRACT(EPOCH FROM (NOW() - MAX("{ts_col}"))) > {freq_seconds} '
            f"THEN 1 ELSE 0 END AS untimely_rows "
            f"FROM {table} {where}"
        ).strip()

        spark_code = (
            f"from pyspark.sql import functions as F\n"
            f'result = df.agg(F.max(F.col("{ts_col}")).alias("most_recent"), F.count("*").alias("cnt")).collect()[0]\n'
            f'import datetime; age = (datetime.datetime.now() - result["most_recent"]).total_seconds() if result["cnt"] > 0 else float("inf")\n'
            f'timely = result["cnt"] > 0 and age <= {freq_seconds}'
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": "",
        }

    # ══════════════════════════════════════════════════════════════
    #  RECONCILIATION DIMENSION
    # ══════════════════════════════════════════════════════════════

    VALID_RECONCILIATION_TYPES = {
        "record_count",
        "one_to_one",
        "aggregate",
        "field_level",
        "tolerance",
        "missing_extra",
    }
    VALID_AGGREGATE_FUNCTIONS = {"SUM", "COUNT", "AVG", "MIN", "MAX"}

    @staticmethod
    def _reconciliation_error_result(message: str) -> dict[str, str]:
        return {
            "compiled_sql": f"-- ERROR: {message}",
            "compiled_postgres": f"-- ERROR: {message}",
            "compiled_spark": f"# ERROR: {message}",
            "violation_sql": f"-- ERROR: {message}",
            "error": message,
        }

    def _compile_reconciliation_rule(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        recon_type = parameters.get("reconciliation_type")
        if recon_type not in self.VALID_RECONCILIATION_TYPES:
            return self._reconciliation_error_result(f"Unknown reconciliation type: {recon_type}")

        source_dataset = parameters.get("source_dataset")
        target_dataset = parameters.get("target_dataset")
        if not source_dataset:
            return self._reconciliation_error_result("source_dataset is required")
        if not target_dataset:
            return self._reconciliation_error_result("target_dataset is required")

        for fkey in ("source_filter", "target_filter"):
            fval = parameters.get(fkey)
            if fval and not self._validate_filter_expression(fval):
                return self._reconciliation_error_result(f"Dangerous {fkey} rejected: {fval}")

        handlers = {
            "record_count": self._reconciliation_record_count,
            "one_to_one": self._reconciliation_one_to_one,
            "aggregate": self._reconciliation_aggregate,
            "field_level": self._reconciliation_field_level,
            "tolerance": self._reconciliation_tolerance,
            "missing_extra": self._reconciliation_missing_extra,
        }

        # Normalize join_keys: accept both flat strings ["col"] and
        # UI dicts [{"source": "src_col", "target": "tgt_col"}]
        raw_keys = parameters.get("join_keys")
        if raw_keys and isinstance(raw_keys[0], dict):
            parameters = dict(parameters)
            parameters["join_keys"] = (
                raw_keys  # keep dicts; handlers below use _normalize_join_keys
            )

        return handlers[recon_type](table, column, parameters)

    @staticmethod
    def _normalize_join_keys(join_keys) -> list:
        """Return list of (src_col, tgt_col) tuples regardless of input format."""
        if not join_keys:
            return []
        if isinstance(join_keys[0], dict):
            return [
                (k.get("source", k.get("src")), k.get("target", k.get("tgt"))) for k in join_keys
            ]
        # plain strings — symmetric
        return [(k, k) for k in join_keys]

    @staticmethod
    def _join_condition(join_keys) -> str:
        pairs = RuleCompiler._normalize_join_keys(join_keys)
        return " AND ".join(f'a."{s}" = b."{t}"' for s, t in pairs)

    def _reconciliation_record_count(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        source = params["source_dataset"]
        target = params["target_dataset"]
        src_filter = params.get("source_filter")
        tgt_filter = params.get("target_filter")

        src_where = f" WHERE {src_filter}" if src_filter else ""
        tgt_where = f" WHERE {tgt_filter}" if tgt_filter else ""

        sql = (
            f"SELECT "
            f"(SELECT COUNT(*) FROM {source}{src_where}) AS source_count, "
            f"(SELECT COUNT(*) FROM {target}{tgt_where}) AS target_count"
        )

        violation_sql = (
            f"SELECT 'source' AS side, COUNT(*) AS row_count FROM {source}{src_where} "
            f"UNION ALL "
            f"SELECT 'target' AS side, COUNT(*) AS row_count FROM {target}{tgt_where}"
        )

        spark_code = (
            "from pyspark.sql.functions import count, lit\n"
            "source_count = df_source.count()\n"
            "target_count = df_target.count()\n"
            'result = spark.createDataFrame([{"source_count": source_count, "target_count": target_count}])'
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _reconciliation_one_to_one(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        source = params["source_dataset"]
        target = params["target_dataset"]
        join_keys = params.get("join_keys")
        if not join_keys:
            return self._reconciliation_error_result(
                "join_keys is required for one_to_one reconciliation"
            )

        src_filter = params.get("source_filter")
        tgt_filter = params.get("target_filter")

        join_pairs = self._normalize_join_keys(join_keys)
        join_cond = " AND ".join(f'a."{s}" = b."{t}"' for s, t in join_pairs)
        first_src, first_tgt = join_pairs[0]

        src_alias = (
            f"(SELECT * FROM {source} WHERE {src_filter}) a" if src_filter else f"{source} a"
        )
        tgt_alias = (
            f"(SELECT * FROM {target} WHERE {tgt_filter}) b" if tgt_filter else f"{target} b"
        )

        sql = (
            f"SELECT "
            f"(SELECT COUNT(*) FROM {src_alias.split(' a')[0].lstrip('(').rstrip(')')}) AS source_count, "
            f"(SELECT COUNT(*) FROM {tgt_alias.split(' b')[0].lstrip('(').rstrip(')')}) AS target_count, "
            f'COUNT(CASE WHEN a."{first_src}" IS NOT NULL AND b."{first_tgt}" IS NOT NULL THEN 1 END) AS matched_count, '
            f'COUNT(CASE WHEN a."{first_src}" IS NOT NULL AND b."{first_tgt}" IS NULL THEN 1 END) AS missing_in_target, '
            f'COUNT(CASE WHEN a."{first_src}" IS NULL AND b."{first_tgt}" IS NOT NULL THEN 1 END) AS extra_in_target '
            f"FROM {src_alias} FULL OUTER JOIN {tgt_alias} ON {join_cond}"
        )

        violation_sql = (
            f"SELECT a.*, 'missing_in_target' AS _recon_status FROM {src_alias} "
            f'LEFT JOIN {tgt_alias} ON {join_cond} WHERE b."{first_tgt}" IS NULL '
            f"UNION ALL "
            f"SELECT b.*, 'extra_in_target' AS _recon_status FROM {tgt_alias} "
            f'LEFT JOIN {src_alias} ON {join_cond} WHERE a."{first_src}" IS NULL'
        )

        flat_keys = [s for s, _ in join_pairs]
        spark_code = (
            f"from pyspark.sql.functions import col, count, when, lit\n"
            f'joined = df_source.alias("a").join(df_target.alias("b"), {flat_keys}, "full_outer")\n'
            f"result = joined.select(\n"
            f'    count(when(col("a.{first_src}").isNotNull() & col("b.{first_tgt}").isNotNull(), lit(1))).alias("matched_count"),\n'
            f'    count(when(col("a.{first_src}").isNotNull() & col("b.{first_tgt}").isNull(), lit(1))).alias("missing_in_target"),\n'
            f'    count(when(col("a.{first_src}").isNull() & col("b.{first_tgt}").isNotNull(), lit(1))).alias("extra_in_target")\n'
            f")"
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _reconciliation_aggregate(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        source = params["source_dataset"]
        target = params["target_dataset"]
        agg_col = params.get("aggregate_column")
        if not agg_col:
            return self._reconciliation_error_result(
                "aggregate_column is required for aggregate reconciliation"
            )

        agg_fn = params.get("aggregate_function", "SUM").upper()
        if agg_fn not in self.VALID_AGGREGATE_FUNCTIONS:
            return self._reconciliation_error_result(f"Invalid aggregate_function: {agg_fn}")

        src_filter = params.get("source_filter")
        tgt_filter = params.get("target_filter")
        group_by = params.get("group_by_columns")

        src_where = f" WHERE {src_filter}" if src_filter else ""
        tgt_where = f" WHERE {tgt_filter}" if tgt_filter else ""

        if group_by:
            group_cols = ", ".join(f'"{g}"' for g in group_by)
            sql = (
                f"SELECT s.{group_cols}, s.source_agg, t.target_agg FROM "
                f'(SELECT {group_cols}, {agg_fn}("{agg_col}") AS source_agg FROM {source}{src_where} GROUP BY {group_cols}) s '
                f"FULL OUTER JOIN "
                f'(SELECT {group_cols}, {agg_fn}("{agg_col}") AS target_agg FROM {target}{tgt_where} GROUP BY {group_cols}) t '
                f"ON " + " AND ".join(f's."{g}" = t."{g}"' for g in group_by)
            )
        else:
            sql = (
                f"SELECT "
                f'(SELECT {agg_fn}("{agg_col}") FROM {source}{src_where}) AS source_agg, '
                f'(SELECT {agg_fn}("{agg_col}") FROM {target}{tgt_where}) AS target_agg'
            )

        violation_sql = sql  # The aggregates themselves show the mismatch

        spark_code = (
            f"from pyspark.sql.functions import col, {agg_fn.lower()}\n"
            f'source_agg = df_source.select({agg_fn.lower()}(col("{agg_col}"))).collect()[0][0]\n'
            f'target_agg = df_target.select({agg_fn.lower()}(col("{agg_col}"))).collect()[0][0]\n'
            f'result = spark.createDataFrame([{{"source_agg": source_agg, "target_agg": target_agg}}])'
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _reconciliation_field_level(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        source = params["source_dataset"]
        target = params["target_dataset"]
        join_keys = params.get("join_keys")
        if not join_keys:
            return self._reconciliation_error_result(
                "join_keys is required for field_level reconciliation"
            )
        compare_cols = params.get("compare_columns")
        if not compare_cols:
            return self._reconciliation_error_result(
                "compare_columns is required for field_level reconciliation"
            )

        src_filter = params.get("source_filter")
        tgt_filter = params.get("target_filter")

        join_cond = self._join_condition(join_keys)
        all_match = " AND ".join(f'a."{c}" = b."{c}"' for c in compare_cols)

        src_alias = (
            f"(SELECT * FROM {source} WHERE {src_filter}) a" if src_filter else f"{source} a"
        )
        tgt_alias = (
            f"(SELECT * FROM {target} WHERE {tgt_filter}) b" if tgt_filter else f"{target} b"
        )

        sql = (
            f"SELECT "
            f"COUNT(*) AS matched_count, "
            f"COUNT(CASE WHEN {all_match} THEN 1 END) AS field_match_count, "
            f"COUNT(CASE WHEN NOT ({all_match}) THEN 1 END) AS field_mismatch_count "
            f"FROM {src_alias} INNER JOIN {tgt_alias} ON {join_cond}"
        )

        violation_sql = (
            f"SELECT a.*, b.* FROM {src_alias} INNER JOIN {tgt_alias} ON {join_cond} "
            f"WHERE NOT ({all_match})"
        )

        match_spark = " & ".join(f'(col("a.{c}") == col("b.{c}"))' for c in compare_cols)
        spark_code = (
            f"from pyspark.sql.functions import col, count, when, lit\n"
            f'joined = df_source.alias("a").join(df_target.alias("b"), {join_keys}, "inner")\n'
            f"match_cond = {match_spark}\n"
            f"result = joined.select(\n"
            f'    count(lit(1)).alias("matched_count"),\n'
            f'    count(when(match_cond, lit(1))).alias("field_match_count"),\n'
            f'    count(when(~match_cond, lit(1))).alias("field_mismatch_count")\n'
            f")"
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _reconciliation_tolerance(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        source = params["source_dataset"]
        target = params["target_dataset"]
        join_keys = params.get("join_keys")
        if not join_keys:
            return self._reconciliation_error_result(
                "join_keys is required for tolerance reconciliation"
            )

        tolerance_type = params.get("tolerance_type", "absolute")
        tolerance_value = params.get("tolerance_value")
        compare_col = params.get("compare_column", column)

        if tolerance_type in ("absolute", "percentage") and tolerance_value is None:
            return self._reconciliation_error_result(
                f"tolerance_value is required for {tolerance_type} tolerance"
            )

        if tolerance_type not in ("none", "absolute", "percentage"):
            return self._reconciliation_error_result(f"Invalid tolerance_type: {tolerance_type}")

        src_filter = params.get("source_filter")
        tgt_filter = params.get("target_filter")

        join_cond = self._join_condition(join_keys)
        actual_expr = f'a."{compare_col}"'
        expected_expr = f'b."{compare_col}"'
        match_cond, mismatch_cond = self._accuracy_tolerance_sql(
            actual_expr, expected_expr, tolerance_type, tolerance_value
        )

        src_alias = (
            f"(SELECT * FROM {source} WHERE {src_filter}) a" if src_filter else f"{source} a"
        )
        tgt_alias = (
            f"(SELECT * FROM {target} WHERE {tgt_filter}) b" if tgt_filter else f"{target} b"
        )

        sql = (
            f"SELECT "
            f"COUNT(*) AS matched_count, "
            f"COUNT(CASE WHEN {match_cond} THEN 1 END) AS within_tolerance, "
            f"COUNT(CASE WHEN {mismatch_cond} THEN 1 END) AS outside_tolerance "
            f"FROM {src_alias} INNER JOIN {tgt_alias} ON {join_cond}"
        )

        violation_sql = (
            f'SELECT a.*, b."{compare_col}" AS target_{compare_col} FROM {src_alias} '
            f"INNER JOIN {tgt_alias} ON {join_cond} WHERE {mismatch_cond}"
        )

        spark_code = (
            f"from pyspark.sql.functions import col, count, when, lit, abs as spark_abs\n"
            f'joined = df_source.alias("a").join(df_target.alias("b"), {join_keys}, "inner")\n'
            f'diff = spark_abs(col("a.{compare_col}") - col("b.{compare_col}"))\n'
            f"result = joined.select(\n"
            f'    count(lit(1)).alias("matched_count"),\n'
            f'    count(when(diff <= {tolerance_value}, lit(1))).alias("within_tolerance"),\n'
            f'    count(when(diff > {tolerance_value}, lit(1))).alias("outside_tolerance")\n'
            f")"
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _reconciliation_missing_extra(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        source = params["source_dataset"]
        target = params["target_dataset"]
        join_keys = params.get("join_keys")
        if not join_keys:
            return self._reconciliation_error_result(
                "join_keys is required for missing_extra reconciliation"
            )

        src_filter = params.get("source_filter")
        tgt_filter = params.get("target_filter")

        join_pairs = self._normalize_join_keys(join_keys)
        join_cond = " AND ".join(f'a."{s}" = b."{t}"' for s, t in join_pairs)
        first_src, first_tgt = join_pairs[0]

        src_alias = (
            f"(SELECT * FROM {source} WHERE {src_filter}) a" if src_filter else f"{source} a"
        )
        tgt_alias = (
            f"(SELECT * FROM {target} WHERE {tgt_filter}) b" if tgt_filter else f"{target} b"
        )
        src_count_from = f"(SELECT * FROM {source} WHERE {src_filter})" if src_filter else source
        tgt_count_from = f"(SELECT * FROM {target} WHERE {tgt_filter})" if tgt_filter else target

        join_cond_b2 = " AND ".join(f'a2."{s}" = b2."{t}"' for s, t in join_pairs)
        sql = (
            f"SELECT "
            f"(SELECT COUNT(*) FROM {src_count_from}) AS source_count, "
            f"(SELECT COUNT(*) FROM {tgt_count_from}) AS target_count, "
            f'(SELECT COUNT(*) FROM {src_alias} LEFT JOIN {tgt_alias} ON {join_cond} WHERE b."{first_tgt}" IS NULL) AS missing_in_target, '
            f'(SELECT COUNT(*) FROM {tgt_count_from} b2 LEFT JOIN {src_count_from} a2 ON {join_cond_b2} WHERE a2."{first_src}" IS NULL) AS extra_in_target'
        )

        violation_sql = (
            f"SELECT a.*, 'missing_in_target' AS _recon_status FROM {src_alias} "
            f'LEFT JOIN {tgt_alias} ON {join_cond} WHERE b."{first_tgt}" IS NULL '
            f"UNION ALL "
            f"SELECT b.*, 'extra_in_target' AS _recon_status FROM {tgt_alias} "
            f'LEFT JOIN {src_alias} ON {join_cond} WHERE a."{first_src}" IS NULL'
        )

        flat_keys = [s for s, _ in join_pairs]
        spark_code = (
            f"from pyspark.sql.functions import col, count, lit\n"
            f'missing = df_source.join(df_target, {flat_keys}, "left_anti")\n'
            f'extra = df_target.join(df_source, {flat_keys}, "left_anti")\n'
            f'result = spark.createDataFrame([{{"source_count": df_source.count(), "target_count": df_target.count(), '
            f'"missing_in_target": missing.count(), "extra_in_target": extra.count()}}])'
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    # ══════════════════════════════════════════════════════════════
    #  ACCURACY DIMENSION
    # ══════════════════════════════════════════════════════════════

    VALID_ACCURACY_TYPES = {
        "reference_comparison",
        "trusted_source",
        "tolerated_deviation",
        "statistical",
        "derived_value",
    }
    REFERENCE_BASED_TYPES = {"reference_comparison", "trusted_source", "tolerated_deviation"}
    SELF_REFERENTIAL_TYPES = {"statistical", "derived_value"}
    VALID_TOLERANCE_TYPES = {"none", "absolute", "percentage"}
    VALID_STATISTICAL_METHODS = {"zscore", "iqr"}

    @staticmethod
    def _infer_accuracy_type(params: dict[str, Any]) -> str:
        if params.get("statistical_method"):
            return "statistical"
        if params.get("formula"):
            return "derived_value"
        if params.get("tolerance_value") is not None and params.get("reference_dataset"):
            return "tolerated_deviation"
        return "reference_comparison"

    @staticmethod
    def _accuracy_tolerance_sql(
        actual_expr: str, expected_expr: str, tolerance_type: str, tolerance_value
    ) -> tuple:
        if tolerance_type == "percentage":
            tol = tolerance_value if tolerance_value is not None else 1.0
            match = f"ABS(({actual_expr}) - ({expected_expr})) / NULLIF(ABS(({expected_expr})), 0) * 100 <= {tol}"
            mismatch = f"ABS(({actual_expr}) - ({expected_expr})) / NULLIF(ABS(({expected_expr})), 0) * 100 > {tol}"
        elif tolerance_type == "absolute":
            tol = tolerance_value if tolerance_value is not None else 0.01
            match = f"ABS(({actual_expr}) - ({expected_expr})) <= {tol}"
            mismatch = f"ABS(({actual_expr}) - ({expected_expr})) > {tol}"
        else:
            # none / default → exact match
            match = f"({actual_expr}) = ({expected_expr})"
            mismatch = f"({actual_expr}) != ({expected_expr})"
        return match, mismatch

    @staticmethod
    def _accuracy_null_handling_sql(columns: list, null_handling: str):
        if null_handling == "skip":
            clause = " AND ".join(f'"{c}" IS NOT NULL' for c in columns)
            return f"WHERE {clause}", "skip"
        if null_handling == "pass":
            return None, "pass"
        return None, "fail"

    @staticmethod
    def _accuracy_error_result(message: str) -> dict[str, str]:
        return {
            "compiled_sql": f"-- ERROR: {message}",
            "compiled_postgres": f"-- ERROR: {message}",
            "compiled_spark": f"# ERROR: {message}",
            "violation_sql": f"-- ERROR: {message}",
            "error": message,
        }

    def _compile_accuracy_rule(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        accuracy_type = parameters.get("accuracy_type") or self._infer_accuracy_type(parameters)
        if accuracy_type not in self.VALID_ACCURACY_TYPES:
            return self._accuracy_error_result(f"Unknown accuracy type: {accuracy_type}")

        filter_expr = parameters.get("filter_expression")
        if filter_expr and not self._validate_filter_expression(filter_expr):
            return self._accuracy_error_result(
                f"Dangerous filter expression rejected: {filter_expr}"
            )

        handlers = {
            "reference_comparison": self._accuracy_reference,
            "trusted_source": self._accuracy_reference,
            "tolerated_deviation": self._accuracy_reference,
            "statistical": self._accuracy_statistical,
            "derived_value": self._accuracy_derived_value,
        }
        return handlers[accuracy_type](table, column, parameters)

    # ── Reference-based (reference_comparison, trusted_source, tolerated_deviation) ──

    def _accuracy_reference(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        ref_dataset = params.get("reference_dataset")
        if not ref_dataset:
            return self._accuracy_error_result(
                "reference_dataset is required for reference-based accuracy checks"
            )
        ref_column = params.get("reference_column", column)
        join_keys = params.get("join_keys")
        if not join_keys:
            return self._accuracy_error_result(
                "join_keys is required for reference-based accuracy checks"
            )

        accuracy_type = params.get("accuracy_type") or self._infer_accuracy_type(params)
        tolerance_type = params.get("tolerance_type", "none")
        tolerance_value = params.get("tolerance_value")

        if accuracy_type == "tolerated_deviation":
            if tolerance_type == "none" or tolerance_value is None:
                return self._accuracy_error_result(
                    "tolerated_deviation requires tolerance_type and tolerance_value"
                )

        if tolerance_type not in self.VALID_TOLERANCE_TYPES:
            return self._accuracy_error_result(f"Invalid tolerance_type: {tolerance_type}")

        filter_expr = params.get("filter_expression")
        null_handling = params.get("null_handling", "fail")

        join_cond = " AND ".join(f'a."{k}" = b."{k}"' for k in join_keys)
        actual_expr = f'a."{column}"'
        expected_expr = f'b."{ref_column}"'

        match_cond, mismatch_cond = self._accuracy_tolerance_sql(
            actual_expr, expected_expr, tolerance_type, tolerance_value
        )

        # Null handling for target column
        null_where, null_mode = self._accuracy_null_handling_sql([column], null_handling)

        base_where_parts = []
        if filter_expr:
            base_where_parts.append(f"({filter_expr})")

        where_clause = ""
        if null_mode == "skip":
            base_where_parts.append(f'a."{column}" IS NOT NULL')
        if base_where_parts:
            where_clause = "WHERE " + " AND ".join(base_where_parts)

        if null_mode == "pass":
            match_cond_full = f'(a."{column}" IS NULL OR ({match_cond}))'
            mismatch_cond_full = f'(a."{column}" IS NOT NULL AND {mismatch_cond})'
        else:
            match_cond_full = match_cond
            mismatch_cond_full = mismatch_cond

        sql = (
            f"SELECT COUNT(*) AS total_rows, "
            f'COUNT(b."{ref_column}") AS verified_rows, '
            f'COUNT(*) - COUNT(b."{ref_column}") AS unverifiable_rows, '
            f'COUNT(CASE WHEN b."{ref_column}" IS NOT NULL AND {match_cond_full} THEN 1 END) AS accurate_rows, '
            f'COUNT(CASE WHEN b."{ref_column}" IS NOT NULL AND {mismatch_cond_full} THEN 1 END) AS inaccurate_rows '
            f"FROM {table} a "
            f"LEFT JOIN {ref_dataset} b ON {join_cond} {where_clause}"
        ).strip()

        violation_sql = (
            f"SELECT a.* FROM {table} a "
            f"LEFT JOIN {ref_dataset} b ON {join_cond} "
            f'WHERE b."{ref_column}" IS NOT NULL AND {mismatch_cond_full}'
        )
        if filter_expr:
            violation_sql += f" AND ({filter_expr})"

        spark_code = (
            f"from pyspark.sql.functions import col, count, when, lit, abs as spark_abs\n"
            f'joined = df.alias("a").join(df_ref.alias("b"), {[k for k in join_keys]}, "left")\n'
            f"result = joined.select(\n"
            f'    count(lit(1)).alias("total_rows"),\n'
            f'    count(col("b.{ref_column}")).alias("verified_rows"),\n'
            f'    count(when(col("b.{ref_column}").isNull(), lit(1))).alias("unverifiable_rows"),\n'
            f'    count(when(col("b.{ref_column}").isNotNull() & (col("a.{column}") == col("b.{ref_column}")), lit(1))).alias("accurate_rows"),\n'
            f'    count(when(col("b.{ref_column}").isNotNull() & (col("a.{column}") != col("b.{ref_column}")), lit(1))).alias("inaccurate_rows")\n'
            f")"
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    # ── Statistical (zscore / iqr) ──

    def _accuracy_statistical(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        if not column or column == "*":
            return self._accuracy_error_result(
                "statistical accuracy check requires a target column to be selected"
            )

        # Accept aliases: proposal/NL layer may emit "method" / "outlier_threshold"
        # while the compiler historically used "statistical_method" / "statistical_threshold".
        method = params.get("statistical_method") or params.get("method") or "zscore"
        if method not in self.VALID_STATISTICAL_METHODS:
            return self._accuracy_error_result(f"Invalid statistical_method: {method}")
        if "statistical_threshold" not in params:
            if "outlier_threshold" in params and params.get("outlier_threshold") is not None:
                params["statistical_threshold"] = params["outlier_threshold"]

        filter_expr = params.get("filter_expression")
        null_handling = params.get("null_handling", "fail")
        where_parts = []
        if filter_expr:
            where_parts.append(f"({filter_expr})")

        null_where, null_mode = self._accuracy_null_handling_sql([column], null_handling)
        if null_mode == "skip":
            where_parts.append(f'"{column}" IS NOT NULL')

        stats_where = "WHERE " + " AND ".join(where_parts) if where_parts else ""
        main_where = stats_where

        if method == "zscore":
            threshold = params.get("statistical_threshold", 3.0)

            if null_mode == "pass":
                in_bounds = f'CASE WHEN t."{column}" IS NULL OR ABS(t."{column}" - s.mu) / NULLIF(s.sigma, 0) <= {threshold} THEN 1 END'
                out_bounds = f'CASE WHEN t."{column}" IS NOT NULL AND ABS(t."{column}" - s.mu) / NULLIF(s.sigma, 0) > {threshold} THEN 1 END'
            else:
                in_bounds = f'CASE WHEN ABS(t."{column}" - s.mu) / NULLIF(s.sigma, 0) <= {threshold} THEN 1 END'
                out_bounds = f'CASE WHEN ABS(t."{column}" - s.mu) / NULLIF(s.sigma, 0) > {threshold} THEN 1 END'

            sql = (
                f'WITH stats AS (SELECT AVG("{column}") AS mu, STDDEV("{column}") AS sigma FROM {table} {stats_where}) '
                f"SELECT COUNT(*) AS total_rows, "
                f"COUNT(*) AS verified_rows, "
                f"0 AS unverifiable_rows, "
                f"COUNT({in_bounds}) AS accurate_rows, "
                f"COUNT({out_bounds}) AS inaccurate_rows "
                f"FROM {table} t CROSS JOIN stats s {main_where}"
            ).strip()

            violation_sql = (
                f'WITH stats AS (SELECT AVG("{column}") AS mu, STDDEV("{column}") AS sigma FROM {table} {stats_where}) '
                f"SELECT t.* FROM {table} t CROSS JOIN stats s "
                f'WHERE ABS(t."{column}" - s.mu) / NULLIF(s.sigma, 0) > {threshold}'
            )
            if filter_expr:
                violation_sql += f" AND ({filter_expr})"

            spark_code = (
                f"from pyspark.sql.functions import col, count, when, lit, avg, stddev, abs as spark_abs\n"
                f'stats = df.select(avg(col("{column}")).alias("mu"), stddev(col("{column}")).alias("sigma")).collect()[0]\n'
                f'mu, sigma = stats["mu"], stats["sigma"]\n'
                f"result = df.select(\n"
                f'    count(lit(1)).alias("total_rows"),\n'
                f'    count(when(spark_abs(col("{column}") - mu) / sigma <= {threshold}, lit(1))).alias("accurate_rows"),\n'
                f'    count(when(spark_abs(col("{column}") - mu) / sigma > {threshold}, lit(1))).alias("inaccurate_rows")\n'
                f")"
            )

        else:  # iqr
            multiplier = params.get("statistical_threshold", 1.5)

            if null_mode == "pass":
                in_bounds = f'CASE WHEN t."{column}" IS NULL OR (t."{column}" >= s.q1 - {multiplier} * (s.q3 - s.q1) AND t."{column}" <= s.q3 + {multiplier} * (s.q3 - s.q1)) THEN 1 END'
                out_bounds = f'CASE WHEN t."{column}" IS NOT NULL AND (t."{column}" < s.q1 - {multiplier} * (s.q3 - s.q1) OR t."{column}" > s.q3 + {multiplier} * (s.q3 - s.q1)) THEN 1 END'
            else:
                in_bounds = f'CASE WHEN t."{column}" >= s.q1 - {multiplier} * (s.q3 - s.q1) AND t."{column}" <= s.q3 + {multiplier} * (s.q3 - s.q1) THEN 1 END'
                out_bounds = f'CASE WHEN t."{column}" < s.q1 - {multiplier} * (s.q3 - s.q1) OR t."{column}" > s.q3 + {multiplier} * (s.q3 - s.q1) THEN 1 END'

            sql = (
                f"WITH stats AS ("
                f'SELECT percentile_cont(0.25) WITHIN GROUP (ORDER BY "{column}") AS q1, '
                f'percentile_cont(0.75) WITHIN GROUP (ORDER BY "{column}") AS q3 '
                f"FROM {table} {stats_where}) "
                f"SELECT COUNT(*) AS total_rows, "
                f"COUNT(*) AS verified_rows, "
                f"0 AS unverifiable_rows, "
                f"COUNT({in_bounds}) AS accurate_rows, "
                f"COUNT({out_bounds}) AS inaccurate_rows "
                f"FROM {table} t CROSS JOIN stats s {main_where}"
            ).strip()

            violation_sql = (
                f"WITH stats AS ("
                f'SELECT percentile_cont(0.25) WITHIN GROUP (ORDER BY "{column}") AS q1, '
                f'percentile_cont(0.75) WITHIN GROUP (ORDER BY "{column}") AS q3 '
                f"FROM {table} {stats_where}) "
                f"SELECT t.* FROM {table} t CROSS JOIN stats s "
                f'WHERE t."{column}" < s.q1 - {multiplier} * (s.q3 - s.q1) OR t."{column}" > s.q3 + {multiplier} * (s.q3 - s.q1)'
            )
            if filter_expr:
                violation_sql += f" AND ({filter_expr})"

            spark_code = (
                f"from pyspark.sql.functions import col, count, when, lit, percentile_approx\n"
                f'quantiles = df.select(percentile_approx(col("{column}"), [0.25, 0.75])).collect()[0][0]\n'
                f"q1, q3 = quantiles[0], quantiles[1]; iqr = q3 - q1\n"
                f"result = df.select(\n"
                f'    count(lit(1)).alias("total_rows"),\n'
                f'    count(when((col("{column}") >= q1 - {multiplier}*iqr) & (col("{column}") <= q3 + {multiplier}*iqr), lit(1))).alias("accurate_rows"),\n'
                f'    count(when((col("{column}") < q1 - {multiplier}*iqr) | (col("{column}") > q3 + {multiplier}*iqr), lit(1))).alias("inaccurate_rows")\n'
                f")"
            )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    # ── Derived Value ──

    def _accuracy_derived_value(
        self, table: str, column: str, params: dict[str, Any]
    ) -> dict[str, str]:
        formula = params.get("formula")
        if not formula:
            return self._accuracy_error_result(
                "formula is required for derived_value accuracy checks"
            )

        if not self._validate_filter_expression(formula):
            return self._accuracy_error_result(f"Dangerous formula rejected: {formula}")

        tolerance_type = params.get("tolerance_type", "none")
        tolerance_value = params.get("tolerance_value")
        filter_expr = params.get("filter_expression")
        null_handling = params.get("null_handling", "fail")

        if tolerance_type not in self.VALID_TOLERANCE_TYPES:
            return self._accuracy_error_result(f"Invalid tolerance_type: {tolerance_type}")

        actual_expr = f'"{column}"'
        expected_expr = f"({formula})"

        match_cond, mismatch_cond = self._accuracy_tolerance_sql(
            actual_expr, expected_expr, tolerance_type, tolerance_value
        )

        null_where, null_mode = self._accuracy_null_handling_sql([column], null_handling)
        where_parts = []
        if filter_expr:
            where_parts.append(f"({filter_expr})")
        if null_mode == "skip":
            where_parts.append(f'"{column}" IS NOT NULL')

        where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""

        if null_mode == "pass":
            match_cond_full = f'("{column}" IS NULL OR ({match_cond}))'
            mismatch_cond_full = f'("{column}" IS NOT NULL AND {mismatch_cond})'
        else:
            match_cond_full = match_cond
            mismatch_cond_full = mismatch_cond

        sql = (
            f"SELECT COUNT(*) AS total_rows, "
            f"COUNT(*) AS verified_rows, "
            f"0 AS unverifiable_rows, "
            f"COUNT(CASE WHEN {match_cond_full} THEN 1 END) AS accurate_rows, "
            f"COUNT(CASE WHEN {mismatch_cond_full} THEN 1 END) AS inaccurate_rows "
            f"FROM {table} {where_clause}"
        ).strip()

        violation_sql = f"SELECT * FROM {table} WHERE {mismatch_cond_full}"
        if filter_expr:
            violation_sql += f" AND ({filter_expr})"

        spark_code = (
            f"from pyspark.sql.functions import col, count, when, lit, abs as spark_abs\n"
            f"result = df.select(\n"
            f'    count(lit(1)).alias("total_rows"),\n'
            f'    count(when(col("{column}") == ({formula}), lit(1))).alias("accurate_rows"),\n'
            f'    count(when(col("{column}") != ({formula}), lit(1))).alias("inaccurate_rows")\n'
            f")"
        )

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _compile_statistical_rule(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Compile statistical rule (mean, stddev, outliers)."""

        sql = f"""
        WITH stats AS (
            SELECT 
                AVG("{column}") as mean_value,
                STDDEV("{column}") as stddev_value,
                MIN("{column}") as min_value,
                MAX("{column}") as max_value
            FROM {table}
            WHERE "{column}" IS NOT NULL
        )
        SELECT 
            COUNT(*) as total_rows,
            (SELECT mean_value FROM stats) as mean_value,
            (SELECT stddev_value FROM stats) as stddev_value,
            (SELECT min_value FROM stats) as min_value,
            (SELECT max_value FROM stats) as max_value
        FROM {table}
        """

        violation_sql = f"""
        WITH stats AS (
            SELECT 
                AVG("{column}") as mean_value,
                STDDEV("{column}") as stddev_value
            FROM {table}
            WHERE "{column}" IS NOT NULL
        )
        SELECT t.*
        FROM {table} t, stats
        WHERE "{column}" < (stats.mean_value - 3 * stats.stddev_value)
           OR "{column}" > (stats.mean_value + 3 * stats.stddev_value)
        """

        spark_code = f"""
from pyspark.sql import functions as F

df = spark.table("{table}")
stats = df.select(
    F.mean("{column}").alias("mean_value"),
    F.stddev("{column}").alias("stddev_value"),
    F.min("{column}").alias("min_value"),
    F.max("{column}").alias("max_value")
).collect()[0]

# Find outliers (> 3 standard deviations from mean)
violations_df = df.filter(
    (F.col("{column}") < (stats.mean_value - 3 * stats.stddev_value)) |
    (F.col("{column}") > (stats.mean_value + 3 * stats.stddev_value))
)
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql,
            "compiled_snowflake": sql,
            "compiled_spark": spark_code,
            "violation_sql": violation_sql,
        }

    def _compile_generic_rule(
        self, table: str, column: str, condition: str, expectation: str, parameters: dict[str, Any]
    ) -> dict[str, str]:
        """Compile generic rule."""

        sql = f"""
        SELECT 
            COUNT(*) as total_rows,
            COUNT(CASE WHEN {condition} THEN 1 END) as passed_rows,
            COUNT(CASE WHEN NOT ({condition}) THEN 1 END) as failed_rows
        FROM {table}
        """

        violation_sql = f"""
        SELECT *
        FROM {table}
        WHERE NOT ({condition})
        """

        return {
            "compiled_sql": sql,
            "compiled_postgres": sql,
            "compiled_mysql": sql,
            "compiled_snowflake": sql,
            "compiled_spark": "# Generic rule - implement based on condition",
            "violation_sql": violation_sql,
        }

    def validate_rule_syntax(self, canonical_rule: dict[str, Any]) -> dict[str, Any]:
        """
        Validate canonical rule syntax.

        Returns:
            Dictionary with validation results
        """
        errors = []
        warnings = []

        # Required fields
        required_fields = ["dimension", "entity", "condition", "expectation", "severity"]
        for field in required_fields:
            if field not in canonical_rule:
                errors.append(f"Missing required field: {field}")

        # Validate dimension
        valid_dimensions = [cat.value for cat in RuleCategory]
        if canonical_rule.get("dimension") not in valid_dimensions:
            errors.append(f"Invalid dimension. Must be one of: {', '.join(valid_dimensions)}")

        # Validate entity format
        entity = canonical_rule.get("entity", "")
        if not entity:
            errors.append("Entity cannot be empty")

        # Validate expectation format
        expectation = canonical_rule.get("expectation", "")
        if not expectation:
            warnings.append("Expectation is empty")

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}
