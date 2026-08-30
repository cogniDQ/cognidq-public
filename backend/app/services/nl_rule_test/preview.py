"""
F107 — NL Rule Test Preview Service.

Provides preview/dry-run of a compiled rule against actual dataset data:
- sample rows from the target dataset
- aggregate pass/fail counts
- example violation rows
- technical expression string
- type / null warnings
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.nl_compiler import CompiledCheckConfig
from app.schemas.nl_rule_test import (
    TestPreviewRequest,
    TestPreviewResponse,
    TestStatistics,
)

logger = logging.getLogger(__name__)

# ── Numeric / date type families (re-used for warnings) ──

_NUMERIC_TYPES = frozenset(
    {
        "int",
        "integer",
        "bigint",
        "smallint",
        "tinyint",
        "numeric",
        "decimal",
        "float",
        "double",
        "real",
        "number",
    }
)
_DATE_TYPES = frozenset({"date", "timestamp", "datetime", "timestamptz"})


class NLRuleTestPreview:
    """Deterministic test-preview of a compiled DQ rule."""

    # ── public entry point ──────────────────────────────────────────────

    def preview(
        self,
        db: Session,
        workspace_id: UUID,
        request: TestPreviewRequest,
    ) -> TestPreviewResponse:
        cfg = request.compiled_config

        # 1. Validate dataset_id present
        if not cfg.dataset_id:
            return TestPreviewResponse(
                status="error",
                error_message="compiled_config.dataset_id is required for test preview",
            )

        # 2. Resolve dataset metadata
        ds_meta = self._get_dataset_meta(db, workspace_id, cfg.dataset_id)
        if ds_meta is None:
            return TestPreviewResponse(
                status="error",
                error_message=f"Dataset {cfg.dataset_id} not found",
            )

        schema_name: str | None = ds_meta.get("schema_name")
        table_name: str = ds_meta["table_name"]
        fields: list[dict[str, Any]] = ds_meta.get("fields", [])
        data_source_id: str | None = ds_meta.get("data_source_id")

        # 3. Build technical expression
        expression = self._build_expression(cfg)

        # 4. Detect type/null warnings
        warnings = self._detect_warnings(cfg, fields)

        # 6. Build WHERE condition for the rule
        condition = self._build_condition(cfg)

        # F3 fix — sample/count/violation queries must run against the
        # actual data source, NOT the metadata DB. The earlier implementation
        # ran `db.execute(...)` against the FastAPI metadata session, which
        # never sees the customer table, so every query raised "relation does
        # not exist" and was swallowed by the broad except → 0/0/0/[].
        target_conn = None
        connect_error: str | None = None
        if data_source_id:
            try:
                target_conn = self._open_target_connection(db, workspace_id, data_source_id)
            except Exception as exc:  # noqa: BLE001
                connect_error = str(exc)
                logger.warning(
                    "NL test-preview: failed to open data source connection: %s",
                    exc,
                )

        try:
            if target_conn is not None:
                sample_data = self._fetch_sample_target(
                    target_conn, schema_name, table_name, request.sample_size
                )
                statistics = self._estimate_counts_target(
                    target_conn, schema_name, table_name, condition
                )
                violations = self._fetch_violations_target(
                    target_conn,
                    schema_name,
                    table_name,
                    condition,
                    request.violation_limit,
                )
            else:
                # Fallback to metadata session (e.g. CSV/Excel datasets that
                # were loaded into the metadata DB). Keeps prior behaviour
                # for non-DB sources.
                sample_data = self._fetch_sample(db, schema_name, table_name, request.sample_size)
                statistics = self._estimate_counts(db, schema_name, table_name, condition)
                violations = self._fetch_violations(
                    db,
                    schema_name,
                    table_name,
                    condition,
                    request.violation_limit,
                )
        finally:
            if target_conn is not None:
                try:
                    target_conn.close()
                except Exception:  # noqa: BLE001
                    pass

        if connect_error:
            warnings.append(
                f"Preview ran against metadata only — could not reach data source: {connect_error}"
            )

        return TestPreviewResponse(
            status="success",
            sample_data=sample_data,
            statistics=statistics,
            violations=violations,
            expression=expression,
            warnings=warnings,
        )

    # ── dataset metadata ────────────────────────────────────────────────

    def _get_dataset_meta(
        self, db: Session, workspace_id: UUID, dataset_id: str
    ) -> dict[str, Any] | None:
        row = db.execute(
            text(
                "SELECT d.dataset_id, d.physical_identifier, d.schema_name, d.data_source_id "
                "FROM control.datasets d "
                "WHERE d.dataset_id = :did AND d.workspace_id = :wid"
            ),
            {"did": dataset_id, "wid": str(workspace_id)},
        ).fetchone()
        if not row:
            return None

        # Fetch fields
        field_rows = db.execute(
            text(
                "SELECT field_name, data_type, nullable "
                "FROM control.dataset_fields "
                "WHERE dataset_id = :did "
                "ORDER BY ordinal_position"
            ),
            {"did": dataset_id},
        ).fetchall()

        fields = [
            {"field_name": r[0], "data_type": (r[1] or "").lower(), "nullable": r[2]}
            for r in field_rows
        ]

        return {
            "table_name": row[1],
            "schema_name": row[2],
            "data_source_id": str(row[3]) if row[3] else None,
            "fields": fields,
        }

    # ── sample data ─────────────────────────────────────────────────────

    def _fetch_sample(
        self,
        db: Session,
        schema_name: str | None,
        table_name: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        fqn = self._fqn(schema_name, table_name)
        try:
            result = db.execute(text(f"SELECT * FROM {fqn} LIMIT :lim"), {"lim": limit})
            cols = list(result.keys())
            return [dict(zip(cols, r)) for r in result.fetchall()]
        except Exception as exc:
            logger.warning("sample fetch failed: %s", exc)
            return []

    # ── row counts ──────────────────────────────────────────────────────

    def _estimate_counts(
        self,
        db: Session,
        schema_name: str | None,
        table_name: str,
        condition: str | None,
    ) -> TestStatistics:
        fqn = self._fqn(schema_name, table_name)
        try:
            total = db.execute(text(f"SELECT COUNT(*) FROM {fqn}")).scalar() or 0
            if condition:
                failed = (
                    db.execute(text(f"SELECT COUNT(*) FROM {fqn} WHERE {condition}")).scalar() or 0
                )
            else:
                failed = 0
            passed = total - failed
            rate = (passed / total * 100) if total > 0 else 0.0
            return TestStatistics(
                total_rows=total,
                rows_passed=passed,
                rows_failed=failed,
                pass_rate=round(rate, 2),
            )
        except Exception as exc:
            logger.warning("count estimation failed: %s", exc)
            return TestStatistics()

    # ── violation examples ──────────────────────────────────────────────

    def _fetch_violations(
        self,
        db: Session,
        schema_name: str | None,
        table_name: str,
        condition: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        if not condition:
            return []
        fqn = self._fqn(schema_name, table_name)
        try:
            result = db.execute(
                text(f"SELECT * FROM {fqn} WHERE {condition} LIMIT :lim"),
                {"lim": limit},
            )
            cols = list(result.keys())
            return [dict(zip(cols, r)) for r in result.fetchall()]
        except Exception as exc:
            logger.warning("violation fetch failed: %s", exc)
            return []

    # ── build WHERE condition from compiled config ──────────────────────

    def _build_condition(self, cfg: CompiledCheckConfig) -> str | None:
        """Turn a CompiledCheckConfig into a SQL WHERE fragment detecting *violating* rows."""
        columns = cfg.config.get("columns", [])
        col = columns[0] if columns else None
        subtype = cfg.subtype

        if subtype == "null" and col:
            return f'"{col}" IS NULL'

        if subtype == "not_null" and col:
            return f'"{col}" IS NOT NULL'

        if subtype == "range" and col:
            op = cfg.config.get("operator", ">")
            val = cfg.config.get("value")
            if val is not None:
                inv = self._invert_op(op)
                return f'"{col}" {inv} {val}'

        if subtype == "allowed_values" and col:
            vals = cfg.config.get("value_list", [])
            if vals:
                quoted = ", ".join(f"'{v}'" for v in vals)
                return f'"{col}" NOT IN ({quoted})'

        if subtype == "regex" and col:
            pattern = cfg.config.get("regex_pattern", "")
            if pattern:
                return f"\"{col}\" !~ '{pattern}'"

        if subtype == "length" and col:
            op = cfg.config.get("operator", "<=")
            val = cfg.config.get("value")
            if val is not None:
                inv = self._invert_op(op)
                return f'LENGTH("{col}") {inv} {val}'

        if subtype in ("unique", "uniqueness") and col:
            return f'"{col}" IN (SELECT "{col}" FROM {self._fqn(None, "__self__")} GROUP BY "{col}" HAVING COUNT(*) > 1)'

        if subtype == "date_comparison" and col:
            op = cfg.config.get("operator", ">")
            val = cfg.config.get("value")
            compare_col = cfg.config.get("compare_column")
            if compare_col:
                inv = self._invert_op(op)
                return f'"{col}" {inv} "{compare_col}"'
            if val is not None:
                inv = self._invert_op(op)
                return f"\"{col}\" {inv} '{val}'"

        if subtype == "column_comparison" and col:
            compare_col = cfg.config.get("compare_column")
            op = cfg.config.get("operator", "=")
            if compare_col:
                inv = self._invert_op(op)
                return f'"{col}" {inv} "{compare_col}"'

        # Fallback: no condition generatable
        return None

    # ── technical expression ────────────────────────────────────────────

    def _build_expression(self, cfg: CompiledCheckConfig) -> str:
        """Human-readable technical expression."""
        canonical = cfg.canonical_rule or {}
        if canonical.get("condition"):
            return (
                f"{cfg.check_type}.{cfg.subtype}: "
                f"{canonical['condition']} "
                f"(expect {canonical.get('expectation', 'N/A')})"
            )
        columns = cfg.config.get("columns", [])
        col_str = ", ".join(columns) if columns else "*"
        return f"{cfg.check_type}.{cfg.subtype}: CHECK({col_str})"

    # ── type / null warnings ────────────────────────────────────────────

    def _detect_warnings(self, cfg: CompiledCheckConfig, fields: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        field_map = {f["field_name"]: f for f in fields}
        columns = cfg.config.get("columns", [])

        for col_name in columns:
            fld = field_map.get(col_name)
            if fld is None:
                warnings.append(f"Column '{col_name}' not found in dataset metadata.")
                continue

            dtype = fld.get("data_type", "")
            nullable = fld.get("nullable", True)

            # Null check on NOT NULL column
            if cfg.subtype == "null" and not nullable:
                warnings.append(
                    f"Column '{col_name}' is NOT NULL; null check will never find violations."
                )

            # Numeric operator on non-numeric column
            if cfg.subtype == "range" and dtype not in _NUMERIC_TYPES:
                warnings.append(f"Range check on non-numeric column '{col_name}' (type: {dtype}).")

            # Date comparison on non-date column
            if cfg.subtype == "date_comparison" and dtype not in _DATE_TYPES:
                warnings.append(f"Date comparison on non-date column '{col_name}' (type: {dtype}).")

            # Length check on non-string column
            if cfg.subtype == "length" and dtype in _NUMERIC_TYPES:
                warnings.append(f"Length check on numeric column '{col_name}' (type: {dtype}).")

        return warnings

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _fqn(schema_name: str | None, table_name: str) -> str:
        if schema_name:
            return f'"{schema_name}"."{table_name}"'
        return f'"{table_name}"'

    @staticmethod
    def _invert_op(op: str) -> str:
        """Return the inverse comparison operator (violation = NOT satisfying rule)."""
        inv = {
            ">": "<=",
            ">=": "<",
            "<": ">=",
            "<=": ">",
            "=": "!=",
            "!=": "=",
            "<>": "=",
        }
        return inv.get(op, op)

    # ── target data-source connection (F3) ──────────────────────────────

    @staticmethod
    def _open_target_connection(db: Session, workspace_id: UUID, data_source_id: str):
        """Open a read-only psycopg2 connection to the dataset's data source.

        Honours both workspace-owned sources and tenant-owned sources that
        have been assigned to the workspace via
        ``control.workspace_connection_assignments`` (mirrors source_node).
        Returns a psycopg2 connection on success; caller is responsible for
        closing it. Raises on any error.
        """
        from app.services.data_sources import credential_service as cred_svc

        row = db.execute(
            text(
                """
                SELECT data_source_id, source_type, credential_reference
                FROM control.data_sources
                WHERE data_source_id = CAST(:ds_id AS UUID)
                  AND archived_at IS NULL
                  AND (
                        workspace_id = CAST(:ws_id AS UUID)
                     OR (
                            workspace_id IS NULL
                        AND data_source_id IN (
                            SELECT connection_id
                            FROM control.workspace_connection_assignments
                            WHERE workspace_id = CAST(:ws_id AS UUID)
                        )
                     )
                  )
                """
            ),
            {"ds_id": data_source_id, "ws_id": str(workspace_id)},
        ).fetchone()

        if not row:
            raise RuntimeError(
                f"Data source {data_source_id} not visible to workspace {workspace_id}"
            )

        ds_type, cred_ref = row[1], row[2]
        if (ds_type or "").lower() != "postgresql":
            raise RuntimeError(
                f"Test-preview only supports postgresql data sources (got {ds_type})"
            )

        if cred_ref is None:
            raise RuntimeError("Data source has no credentials")

        cred_row = db.execute(
            text(
                """
                SELECT encrypted_payload
                FROM control.data_source_credentials
                WHERE credential_id = CAST(:cred_id AS UUID)
                  AND superseded_at IS NULL
                """
            ),
            {"cred_id": str(cred_ref)},
        ).fetchone()
        if not cred_row or not cred_row[0]:
            raise RuntimeError("Data source credentials missing")

        creds = cred_svc.decrypt(bytes(cred_row[0]))

        import psycopg2 as pg2

        conn = pg2.connect(
            host=creds.get("host"),
            port=int(creds.get("port", 5432)),
            database=creds.get("database"),
            user=creds.get("username"),
            password=creds.get("password"),
            connect_timeout=10,
        )
        conn.set_session(readonly=True, autocommit=True)
        return conn

    # ── target queries (F3) ─────────────────────────────────────────────

    def _fetch_sample_target(
        self,
        conn,
        schema_name: str | None,
        table_name: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        fqn = self._fqn(schema_name, table_name)
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM {fqn} LIMIT %s", (limit,))
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            cur.close()
            return [{c: self._jsonify(v) for c, v in zip(cols, r)} for r in rows]
        except Exception as exc:  # noqa: BLE001
            logger.warning("target sample fetch failed: %s", exc)
            return []

    def _estimate_counts_target(
        self,
        conn,
        schema_name: str | None,
        table_name: str,
        condition: str | None,
    ) -> TestStatistics:
        fqn = self._fqn(schema_name, table_name)
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {fqn}")
            total = cur.fetchone()[0] or 0
            if condition:
                cur.execute(f"SELECT COUNT(*) FROM {fqn} WHERE {condition}")
                failed = cur.fetchone()[0] or 0
            else:
                failed = 0
            cur.close()
            passed = total - failed
            rate = (passed / total * 100) if total > 0 else 0.0
            return TestStatistics(
                total_rows=total,
                rows_passed=passed,
                rows_failed=failed,
                pass_rate=round(rate, 2),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("target count estimation failed: %s", exc)
            return TestStatistics()

    def _fetch_violations_target(
        self,
        conn,
        schema_name: str | None,
        table_name: str,
        condition: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        if not condition:
            return []
        fqn = self._fqn(schema_name, table_name)
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM {fqn} WHERE {condition} LIMIT %s", (limit,))
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            cur.close()
            return [{c: self._jsonify(v) for c, v in zip(cols, r)} for r in rows]
        except Exception as exc:  # noqa: BLE001
            logger.warning("target violation fetch failed: %s", exc)
            return []

    @staticmethod
    def _jsonify(value: Any) -> Any:
        """Make psycopg2 row values JSON-serialisable."""
        import datetime as _dt
        from decimal import Decimal

        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
            return value.isoformat()
        try:
            return str(value)
        except Exception:  # noqa: BLE001
            return None
