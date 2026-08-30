"""
F134 P06 — general_dq Demo Template Seeder

Implements TemplateSeederProtocol for the ``general_dq`` template.

Scenario: e-commerce company (Acme Shop) — customers / orders / products
seed data demonstrating common data quality problems.

Idempotency: checks for existing rows tagged with
``seed_source = 'template:general_dq'`` and ``workspace_id``; returns
early if content already present.

All IDs are deterministic (UUID5 from workspace_id + item name) so the
seeder is safe to call multiple times without duplication.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import NAMESPACE_DNS, UUID, uuid5

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SEED_SOURCE = "template:general_dq"
_NAMESPACE = NAMESPACE_DNS


def _uid(workspace_id: UUID, name: str) -> UUID:
    """Deterministic UUID5 from workspace_id + name."""
    return uuid5(_NAMESPACE, f"{workspace_id}:{name}")


def _now() -> datetime:
    return datetime.now(UTC)


def _pg_array_quote(value: str) -> str:
    """Quote a single string for inclusion in a Postgres TEXT[] literal.

    Escapes backslashes and double quotes, then wraps in double quotes so the
    value is interpreted as a single element regardless of commas or spaces.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class GeneralDQSeeder:
    """Demo content seeder for the general_dq template."""

    template_id = "general_dq"

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Public API ────────────────────────────────────────────────────────

    def seed(self, tenant_id: UUID, workspace_id: UUID) -> None:
        """
        Populate the sandbox workspace with general_dq demo content.

        Idempotent: if seed_source rows already exist for this workspace,
        returns immediately without modifying any data.
        """
        if self._already_seeded(workspace_id):
            logger.info("general_dq: workspace %s already seeded — skipping.", workspace_id)
            return

        logger.info("general_dq: seeding workspace %s.", workspace_id)
        now = _now()

        ds_id = self._seed_data_source(tenant_id, workspace_id, now)
        d_ids = self._seed_datasets(tenant_id, workspace_id, ds_id, now)
        self._seed_dataset_fields(d_ids, now)
        r_ids = self._seed_rules(workspace_id, ds_id, d_ids, now)
        flow_id = self._seed_flow(workspace_id, r_ids, now)
        exec_id = self._seed_flow_execution(workspace_id, flow_id, r_ids, now)
        self._seed_issues(tenant_id, workspace_id, exec_id, r_ids, d_ids, now)
        self._seed_dashboard(workspace_id, now)
        self._seed_glossary(tenant_id, workspace_id, now)

        logger.info("general_dq: seeding complete for workspace %s.", workspace_id)

    # ── Idempotency check ─────────────────────────────────────────────────

    def _already_seeded(self, workspace_id: UUID) -> bool:
        row = self._db.execute(
            text(
                "SELECT 1 FROM control.datasets "
                "WHERE workspace_id = :wid AND seed_source = :src LIMIT 1"
            ),
            {"wid": str(workspace_id), "src": SEED_SOURCE},
        ).fetchone()
        return row is not None

    # ── Data source ───────────────────────────────────────────────────────

    def _seed_data_source(self, tenant_id: UUID, workspace_id: UUID, now: datetime) -> UUID:
        ds_id = _uid(workspace_id, "demo_data_source")
        self._db.execute(
            text("""
                INSERT INTO control.data_sources (
                    data_source_id, workspace_id, tenant_id,
                    source_name, source_type, connection_mode,
                    environment, description, status, last_test_status,
                    created_at, updated_at, created_by, seed_source
                ) VALUES (
                    :id, :workspace_id, :tenant_id,
                    'Acme Shop Demo DB', 'postgresql', 'direct',
                    'development', 'Synthetic demo database for the general_dq template.',
                    'active', 'reachable',
                    :now, :now, :created_by, :seed_source
                )
                ON CONFLICT (data_source_id) DO NOTHING
            """),
            {
                "id": str(ds_id),
                "workspace_id": str(workspace_id),
                "tenant_id": str(tenant_id),
                "now": now,
                "created_by": str(tenant_id),
                "seed_source": SEED_SOURCE,
            },
        )
        return ds_id

    # ── Datasets ──────────────────────────────────────────────────────────

    def _seed_datasets(
        self,
        tenant_id: UUID,
        workspace_id: UUID,
        data_source_id: UUID,
        now: datetime,
    ) -> list[UUID]:
        specs = [
            ("ds_customers", "customers", "table", "public", "Customer master table"),
            ("ds_orders", "orders", "table", "public", "Transactional orders table"),
            ("ds_products", "products", "table", "public", "Product catalog table"),
        ]
        ids: list[UUID] = []
        for key, name, dtype, schema, desc in specs:
            did = _uid(workspace_id, key)
            ids.append(did)
            self._db.execute(
                text("""
                    INSERT INTO control.datasets (
                        dataset_id, workspace_id, tenant_id, data_source_id,
                        dataset_name, dataset_type, physical_identifier,
                        schema_name, description, criticality, status,
                        created_at, updated_at, created_by, seed_source
                    ) VALUES (
                        :id, :workspace_id, :tenant_id, :ds_id,
                        :name, :dtype, :name,
                        :schema, :desc, 'medium', 'active',
                        :now, :now, :created_by, :seed_source
                    )
                    ON CONFLICT (dataset_id) DO NOTHING
                """),
                {
                    "id": str(did),
                    "workspace_id": str(workspace_id),
                    "tenant_id": str(tenant_id),
                    "ds_id": str(data_source_id),
                    "name": name,
                    "dtype": dtype,
                    "schema": schema,
                    "desc": desc,
                    "now": now,
                    "created_by": str(tenant_id),
                    "seed_source": SEED_SOURCE,
                },
            )
        return ids

    # ── Dataset fields (E2 — sample value preview) ────────────────────────

    # Customers / Orders / Products field catalogues. The 0/1/2 indices match
    # the order specs are inserted in `_seed_datasets`.
    _DATASET_FIELDS = [
        # customers
        [
            ("id", "uuid", False, ["c1a4-001", "c1a4-002", "c1a4-003"]),
            (
                "email",
                "varchar",
                True,
                ["alice@acme.io", "bob@example.com", "carol@example.com", "", "not-an-email"],
            ),
            ("first_name", "varchar", True, ["Alice", "Bob", "Carol", "Dan"]),
            ("last_name", "varchar", True, ["Smith", "Jones", "Patel", "Müller"]),
            ("country_code", "varchar", True, ["US", "FR", "DE", "GB", "MA"]),
            ("created_at", "timestamp", False, ["2024-09-01 10:00:00", "2024-12-14 02:33:11"]),
        ],
        # orders
        [
            ("id", "uuid", False, ["o1a4-001", "o1a4-002"]),
            ("customer_id", "uuid", False, ["c1a4-001", "c1a4-002", "c1a4-003"]),
            ("amount", "numeric", False, ["19.99", "45.00", "0.00", "-3.50"]),
            ("status", "varchar", True, ["paid", "pending", "refunded", ""]),
            ("ordered_at", "timestamp", False, ["2025-01-01 09:12:00", "2024-09-30 14:55:00"]),
            ("updated_at", "timestamp", True, ["2025-01-02 10:00:00", "2024-10-01 09:00:00"]),
        ],
        # products
        [
            ("id", "uuid", False, ["p1a4-001", "p1a4-002"]),
            ("name", "varchar", False, ["Widget A", "Widget &amp; B", "Gadget &lt;Pro&gt;"]),
            ("price", "numeric", False, ["9.99", "19.50", "0.00"]),
            ("category", "varchar", True, ["Tools", "Apparel", "Home"]),
            ("active", "boolean", False, ["true", "false"]),
        ],
    ]

    def _seed_dataset_fields(self, dataset_ids: list[UUID], now: datetime) -> None:
        for dataset_id, fields in zip(dataset_ids, self._DATASET_FIELDS):
            for ordinal, (fname, dtype, nullable, samples) in enumerate(fields):
                self._db.execute(
                    text("""
                        INSERT INTO control.dataset_fields (
                            field_id, dataset_id, field_name, data_type,
                            nullable, sensitivity_classification, is_key_candidate,
                            ordinal_position, sample_values, sample_values_updated_at,
                            created_at, updated_at
                        ) VALUES (
                            :id, :dataset_id, :fname, :dtype,
                            :nullable, 'internal', :is_key,
                            :ord, CAST(:samples AS TEXT[]), :now,
                            :now, :now
                        )
                        ON CONFLICT (dataset_id, lower(field_name)) DO NOTHING
                    """),
                    {
                        "id": str(_uid(dataset_id, f"field_{fname}")),
                        "dataset_id": str(dataset_id),
                        "fname": fname,
                        "dtype": dtype,
                        "nullable": nullable,
                        "is_key": fname == "id",
                        "ord": ordinal,
                        "samples": "{" + ",".join(_pg_array_quote(v) for v in samples) + "}",
                        "now": now,
                    },
                )

    # ── Rules ─────────────────────────────────────────────────────────────

    def _seed_rules(
        self,
        workspace_id: UUID,
        data_source_id: UUID,
        dataset_ids: list[UUID],
        now: datetime,
    ) -> list[UUID]:
        customers_id, orders_id, products_id = dataset_ids
        specs = [
            {
                "key": "rule_email_not_null",
                "name": "customers.email — Not Null",
                "category": "completeness",
                "rule_type": "null_check",
                "target_table": "customers",
                "target_columns": ["email"],
                "dataset_id": customers_id,
                "desc": "Email must not be null for any customer record.",
            },
            {
                "key": "rule_email_format",
                "name": "customers.email — Valid Format",
                "category": "validity",
                "rule_type": "regex_check",
                "target_table": "customers",
                "target_columns": ["email"],
                "dataset_id": customers_id,
                "desc": "Email must match standard RFC-5322 pattern.",
            },
            {
                "key": "rule_order_amount_positive",
                "name": "orders.total_amount — Positive",
                "category": "validity",
                "rule_type": "range_check",
                "target_table": "orders",
                "target_columns": ["total_amount"],
                "dataset_id": orders_id,
                "desc": "Every order must have a positive total amount.",
            },
            {
                "key": "rule_order_status_completeness",
                "name": "orders.status — Completeness",
                "category": "completeness",
                "rule_type": "null_check",
                "target_table": "orders",
                "target_columns": ["status"],
                "dataset_id": orders_id,
                "desc": "Order status must not be null.",
            },
            {
                "key": "rule_product_price_positive",
                "name": "products.price — Positive",
                "category": "validity",
                "rule_type": "range_check",
                "target_table": "products",
                "target_columns": ["price"],
                "dataset_id": products_id,
                "desc": "Product price must be greater than zero.",
            },
        ]
        ids: list[UUID] = []
        for spec in specs:
            rid = _uid(workspace_id, spec["key"])
            ids.append(rid)
            canonical = {
                "rule_type": spec["rule_type"],
                "target_table": spec["target_table"],
                "target_columns": spec["target_columns"],
            }
            self._db.execute(
                text("""
                    INSERT INTO public.dq_rules (
                        id, workspace_id, name, description, category, rule_type,
                        canonical_rule, target_table, target_columns,
                        status, is_active, created_at, updated_at, seed_source
                    ) VALUES (
                        :id, :workspace_id, :name, :desc, :category, :rule_type,
                        CAST(:canonical AS JSONB), :target_table,
                        CAST(:cols AS TEXT[]),
                        'active', TRUE, :now, :now, :seed_source
                    )
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": str(rid),
                    "workspace_id": str(workspace_id),
                    "name": spec["name"],
                    "desc": spec["desc"],
                    "category": spec["category"],
                    "rule_type": spec["rule_type"],
                    "canonical": json.dumps(canonical),
                    "target_table": spec["target_table"],
                    "cols": "{" + ",".join(spec["target_columns"]) + "}",
                    "now": now,
                    "seed_source": SEED_SOURCE,
                },
            )
        return ids

    # ── Flow ──────────────────────────────────────────────────────────────

    def _seed_flow(self, workspace_id: UUID, rule_ids: list[UUID], now: datetime) -> UUID:
        flow_id = _uid(workspace_id, "flow_nightly_dq")
        nodes = [
            {"id": f"node_{i}", "type": "rule_check", "rule_id": str(rid)}
            for i, rid in enumerate(rule_ids)
        ]
        flow_def = {
            "version": 1,
            "name": "Nightly DQ Sweep",
            "nodes": nodes,
            "edges": [],
        }
        self._db.execute(
            text("""
                INSERT INTO public.dq_flows (
                    id, workspace_id, name, description,
                    flow_definition, status, is_active,
                    created_at, updated_at, seed_source
                ) VALUES (
                    :id, :workspace_id, 'Nightly DQ Sweep',
                    'Runs all general_dq checks every night.',
                    CAST(:flow_def AS JSONB), 'active', TRUE,
                    :now, :now, :seed_source
                )
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": str(flow_id),
                "workspace_id": str(workspace_id),
                "flow_def": json.dumps(flow_def),
                "now": now,
                "seed_source": SEED_SOURCE,
            },
        )
        return flow_id

    # ── Flow Execution ────────────────────────────────────────────────────

    def _seed_flow_execution(
        self,
        workspace_id: UUID,
        flow_id: UUID,
        rule_ids: list[UUID],
        now: datetime,
    ) -> UUID:
        exec_id = _uid(workspace_id, "flow_exec_demo_01")
        summary = {
            "rules_evaluated": len(rule_ids),
            "rules_passed": max(0, len(rule_ids) - 5),
            "rules_failed": 5,
            "seed": SEED_SOURCE,
        }
        self._db.execute(
            text("""
                INSERT INTO public.flow_executions (
                    id, flow_id, execution_type, status,
                    started_at, completed_at, duration_seconds,
                    nodes_executed, nodes_passed, nodes_failed, nodes_skipped,
                    result_summary, created_at
                ) VALUES (
                    :id, :flow_id, 'scheduled', 'completed',
                    :started, :now, 42,
                    :total, :passed, :failed, 0,
                    CAST(:summary AS JSONB), :now
                )
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": str(exec_id),
                "flow_id": str(flow_id),
                "started": now,
                "now": now,
                "total": len(rule_ids),
                "passed": max(0, len(rule_ids) - 5),
                "failed": 5,
                "summary": json.dumps(summary),
            },
        )
        return exec_id

    # ── Issues ────────────────────────────────────────────────────────────

    def _seed_issues(
        self,
        tenant_id: UUID,
        workspace_id: UUID,
        flow_execution_id: UUID,
        rule_ids: list[UUID],
        dataset_ids: list[UUID],
        now: datetime,
    ) -> None:
        customers_id, orders_id, products_id = dataset_ids
        (
            rule_email_null,
            rule_email_fmt,
            rule_order_amount,
            rule_order_status,
            rule_product_price,
        ) = rule_ids

        # issue_type: threshold_breach | execution_error
        # severity:   critical | major | minor | informational
        # status:     open | in_progress | resolved | closed | reopened
        issue_specs = [
            (
                "issue_01",
                "Missing email addresses detected",
                "threshold_breach",
                "major",
                "open",
                rule_email_null,
                customers_id,
                342,
                15000,
                0.977,
            ),
            (
                "issue_02",
                "Malformed email addresses in customers",
                "threshold_breach",
                "minor",
                "open",
                rule_email_fmt,
                customers_id,
                87,
                15000,
                0.994,
            ),
            (
                "issue_03",
                "Negative order totals found",
                "threshold_breach",
                "critical",
                "open",
                rule_order_amount,
                orders_id,
                12,
                48200,
                0.9998,
            ),
            (
                "issue_04",
                "Orders missing status field",
                "threshold_breach",
                "major",
                "open",
                rule_order_status,
                orders_id,
                156,
                48200,
                0.997,
            ),
            (
                "issue_05",
                "Products with zero price",
                "threshold_breach",
                "critical",
                "open",
                rule_product_price,
                products_id,
                8,
                9300,
                0.9991,
            ),
            (
                "issue_06",
                "Stale order records older than 90 days without update",
                "threshold_breach",
                "minor",
                "in_progress",
                rule_order_status,
                orders_id,
                1204,
                48200,
                0.975,
            ),
            (
                "issue_07",
                "Duplicate email addresses in customers",
                "threshold_breach",
                "major",
                "open",
                rule_email_fmt,
                customers_id,
                23,
                15000,
                0.9985,
            ),
            (
                "issue_08",
                "Product names contain HTML entities",
                "threshold_breach",
                "informational",
                "open",
                rule_product_price,
                products_id,
                45,
                9300,
                0.9952,
            ),
            (
                "issue_09",
                "Orders referencing non-existent customers",
                "threshold_breach",
                "critical",
                "open",
                rule_order_amount,
                orders_id,
                3,
                48200,
                0.999938,
            ),
            (
                "issue_10",
                "Customers with no orders in 180 days",
                "threshold_breach",
                "informational",
                "open",
                rule_email_null,
                customers_id,
                890,
                15000,
                0.941,
            ),
        ]

        for spec in issue_specs:
            (
                key,
                title,
                itype,
                severity,
                status,
                rule_id,
                dataset_id,
                fail_count,
                rows_scanned,
                pass_rate,
            ) = spec
            iid = _uid(workspace_id, key)
            self._db.execute(
                text("""
                    INSERT INTO public.issues (
                        id, workspace_id, tenant_id,
                        flow_execution_id, rule_id, dataset_id,
                        issue_type, severity, status, title,
                        failure_count, rows_scanned, pass_rate,
                        opened_at, created_at, updated_at,
                        seed_source
                    ) VALUES (
                        :id, :workspace_id, :tenant_id,
                        :exec_id, :rule_id, :dataset_id,
                        :issue_type, :severity, :status, :title,
                        :failure_count, :rows_scanned, :pass_rate,
                        :now, :now, :now,
                        :seed_source
                    )
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": str(iid),
                    "workspace_id": str(workspace_id),
                    "tenant_id": str(tenant_id),
                    "exec_id": str(flow_execution_id),
                    "rule_id": str(rule_id),
                    "dataset_id": str(dataset_id),
                    "issue_type": itype,
                    "severity": severity,
                    "status": status,
                    "title": title,
                    "failure_count": fail_count,
                    "rows_scanned": rows_scanned,
                    "pass_rate": pass_rate,
                    "now": now,
                    "seed_source": SEED_SOURCE,
                },
            )

    # ── Dashboard ─────────────────────────────────────────────────────────

    def _seed_dashboard(self, workspace_id: UUID, now: datetime) -> UUID:
        dash_id = _uid(workspace_id, "dashboard_dq_overview")
        layout = {
            "panels": [
                {
                    "id": "p1",
                    "type": "metric",
                    "title": "Open Issues",
                    "metric": "open_issues_count",
                },
                {
                    "id": "p2",
                    "type": "metric",
                    "title": "Pass Rate (7d avg)",
                    "metric": "pass_rate_7d",
                },
                {
                    "id": "p3",
                    "type": "chart",
                    "title": "Issues by Severity",
                    "chart": "severity_donut",
                },
                {
                    "id": "p4",
                    "type": "table",
                    "title": "Recent Failures",
                    "query": "recent_failures",
                },
            ]
        }
        self._db.execute(
            text("""
                INSERT INTO public.dashboards (
                    id, workspace_id, name, description,
                    layout, is_public, created_at, updated_at, seed_source
                ) VALUES (
                    :id, :workspace_id,
                    'DQ Overview — Acme Shop',
                    'Pre-built data quality overview dashboard for the demo environment.',
                    CAST(:layout AS JSONB), TRUE,
                    :now, :now, :seed_source
                )
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": str(dash_id),
                "workspace_id": str(workspace_id),
                "layout": json.dumps(layout),
                "now": now,
                "seed_source": SEED_SOURCE,
            },
        )
        return dash_id

    # ── Glossary terms ────────────────────────────────────────────────────

    def _seed_glossary(self, tenant_id: UUID, workspace_id: UUID, now: datetime) -> None:
        terms = [
            (
                "gls_completeness",
                "Completeness",
                "completeness",
                "The degree to which required data values are present.",
                "DQ Dimension",
            ),
            (
                "gls_accuracy",
                "Accuracy",
                "accuracy",
                "The degree to which data correctly represents the real-world construct.",
                "DQ Dimension",
            ),
            (
                "gls_consistency",
                "Consistency",
                "consistency",
                "The absence of contradiction between data values across systems.",
                "DQ Dimension",
            ),
            (
                "gls_timeliness",
                "Timeliness",
                "timeliness",
                "The degree to which data is current for the business requirement.",
                "DQ Dimension",
            ),
            (
                "gls_uniqueness",
                "Uniqueness",
                "uniqueness",
                "No record or attribute is recorded more than once.",
                "DQ Dimension",
            ),
            (
                "gls_validity",
                "Validity",
                "validity",
                "Data conforms to defined formats, types, and value ranges.",
                "DQ Dimension",
            ),
            (
                "gls_pass_rate",
                "Pass Rate",
                "pass_rate",
                "Percentage of rows that satisfy a DQ rule out of total rows scanned.",
                "KPI",
            ),
            (
                "gls_issue",
                "DQ Issue",
                "dq_issue",
                "A recorded violation of a data quality rule above threshold.",
                "Platform Entity",
            ),
            (
                "gls_data_source",
                "Data Source",
                "data_source",
                "A registered connection to a database, file store, or API.",
                "Platform Entity",
            ),
            (
                "gls_sandbox",
                "Demo Sandbox",
                "sandbox",
                "An isolated, time-limited platform workspace provisioned for prospect evaluation.",
                "Platform Entity",
            ),
        ]

        for key, business_name, technical_name, definition, domain in terms:
            term_id = _uid(workspace_id, key)
            self._db.execute(
                text("""
                    INSERT INTO control.metadata_term_index (
                        term_id, workspace_id, tenant_id,
                        business_name, technical_name, definition,
                        synonyms, domain, linked_asset_ids,
                        source, trust_level,
                        created_at, updated_at, seed_source
                    ) VALUES (
                        :id, :workspace_id, :tenant_id,
                        :business_name, :technical_name, :definition,
                        '[]'::JSONB, :domain, '[]'::JSONB,
                        'template:general_dq', 'authoritative',
                        :now, :now, :seed_source
                    )
                    ON CONFLICT (term_id) DO NOTHING
                """),
                {
                    "id": str(term_id),
                    "workspace_id": str(workspace_id),
                    "tenant_id": str(tenant_id),
                    "business_name": business_name,
                    "technical_name": technical_name,
                    "definition": definition,
                    "domain": domain,
                    "now": now,
                    "seed_source": SEED_SOURCE,
                },
            )
