/**
 * F-CONN-UX — Connector Catalog API service
 *
 * Wraps the read-only `/api/v1/connectors` endpoints exposed by F-CONN-CORE
 * (`backend/app/api/v1/endpoints/connector_catalog.py`). The connector
 * registry drives the catalog grid and the credential-form renderer, so the
 * UI no longer hard-codes per-connector branches.
 *
 * Field shapes mirror `ConnectorSpec.to_dict()` and `CredentialField.to_dict()`.
 */
import { api } from './api';

// ── Types ────────────────────────────────────────────────────────────────────

export type ConnectorCategory =
  | 'database'
  | 'warehouse'
  | 'lakehouse'
  | 'file'
  | 'object_storage'
  | 'query_engine'
  | 'metadata_catalog'
  | 'bi_exported_dataset';

export type ConnectorPriority = 'P0' | 'P1';

export type ConnectorStatus = 'ready' | 'integration_ready' | 'deferred';

/**
 * Field types as enumerated by the backend `CredentialField` registry.
 * Mirrors `services/datasources/connectors/registry.py::CredentialFieldType`.
 */
export type CredentialFieldType =
  | 'string'
  | 'number'
  | 'secret'
  | 'select'
  | 'boolean'
  | 'json'
  | 'multiline';

export interface CredentialField {
  name: string;
  type: CredentialFieldType;
  label: string;
  required: boolean;
  default?: unknown;
  options?: string[];
  placeholder?: string;
  help_text?: string;
}

export interface ConnectorCapabilities {
  supports_connection_test: boolean;
  supports_metadata_discovery: boolean;
  supports_schema_discovery: boolean;
  supports_table_discovery: boolean;
  supports_file_discovery: boolean;
  supports_dataset_preview: boolean;
  supports_check_execution: boolean;
  supports_sampling: boolean;
  supports_pushdown_sql: boolean;
  supports_parquet: boolean;
  requires_external_credentials: boolean;
  local_test_available: boolean;
}

export interface ConnectorSpec {
  type: string;
  display_name: string;
  description: string;
  category: ConnectorCategory;
  priority: ConnectorPriority;
  status: ConnectorStatus;
  capabilities: ConnectorCapabilities;
  credential_schema: CredentialField[];
  docs_url?: string;
  icon?: string;
  deferred_reason?: string;
}

export interface ConnectorListResponse {
  items: ConnectorSpec[];
  total: number;
}

// ── API ──────────────────────────────────────────────────────────────────────

export interface ListConnectorsFilters {
  category?: ConnectorCategory;
  priority?: ConnectorPriority;
  status?: ConnectorStatus;
  local_only?: boolean;
}

export async function listConnectors(
  filters: ListConnectorsFilters = {},
): Promise<ConnectorListResponse> {
  const params: Record<string, unknown> = {};
  if (filters.category) params.category = filters.category;
  if (filters.priority) params.priority = filters.priority;
  if (filters.status) params.status = filters.status;
  if (filters.local_only !== undefined) params.local_only = filters.local_only;

  const { data } = await api.get<ConnectorListResponse>('/connectors', { params });
  return data;
}

export async function getConnector(type: string): Promise<ConnectorSpec> {
  const { data } = await api.get<ConnectorSpec>(`/connectors/${type}`);
  return data;
}

// ── Display helpers ──────────────────────────────────────────────────────────

export const CATEGORY_LABELS: Record<ConnectorCategory, string> = {
  database: 'Databases',
  warehouse: 'Warehouses',
  lakehouse: 'Lakehouses',
  file: 'Files',
  object_storage: 'Object Storage',
  query_engine: 'Query Engines',
  metadata_catalog: 'Metadata & Catalog',
  bi_exported_dataset: 'BI / Exported Datasets',
};

export const STATUS_LABELS: Record<ConnectorStatus, string> = {
  ready: 'Ready',
  integration_ready: 'Integration Ready',
  deferred: 'Coming Soon',
};

export const STATUS_BADGE_CLASS: Record<ConnectorStatus, string> = {
  ready: 'bg-green-100 text-green-700 border-green-200',
  integration_ready: 'bg-blue-100 text-blue-700 border-blue-200',
  deferred: 'bg-gray-100 text-gray-500 border-gray-200',
};

// ── Customer-facing presentation (spec §5, §11) ──────────────────────────────
//
// Internal connector metadata (priority P0/P1, ConnectorStatus values like
// `integration_ready`, capability flags, `local_test_available`) is useful to
// developers but confusing for customers. The helpers below project that
// metadata into plain-English labels for the SaaS catalog UI, while the raw
// values stay available for admin/dev surfaces.

export type CustomerStatus = 'available' | 'beta' | 'coming_soon';

export const CUSTOMER_STATUS_LABEL: Record<CustomerStatus, string> = {
  available: 'Available',
  beta: 'Beta',
  coming_soon: 'Coming soon',
};

export const CUSTOMER_STATUS_BADGE_CLASS: Record<CustomerStatus, string> = {
  available: 'bg-green-900/40 text-green-400 border-green-800',
  beta: 'bg-amber-900/40 text-amber-400 border-amber-800',
  coming_soon: 'bg-dark-700 text-gray-500 border-dark-600',
};

/** Project the engineering `ConnectorStatus` to the customer-facing badge. */
export function customerStatusFor(spec: ConnectorSpec): CustomerStatus {
  switch (spec.status) {
    case 'ready':
      return 'available';
    case 'integration_ready':
      return 'beta';
    case 'deferred':
    default:
      return 'coming_soon';
  }
}

/**
 * Customer-facing top-level groupings shown on the onboarding catalog. These
 * are derived from the existing `ConnectorCategory` so we don't duplicate
 * registry data. "Start fast" = files (CSV/Excel/JSON), "Connect a database"
 * = relational engines, "Enterprise warehouses" = cloud DWHs, "Enterprise
 * lakehouses" = lakehouse engines + object storage + query engines.
 */
export type CustomerGroup =
  | 'start_fast'
  | 'connect_database'
  | 'enterprise_warehouse'
  | 'enterprise_lakehouse'
  | 'other';

export const CUSTOMER_GROUP_LABEL: Record<CustomerGroup, string> = {
  start_fast: 'Start fast',
  connect_database: 'Connect a database',
  enterprise_warehouse: 'Enterprise warehouses',
  enterprise_lakehouse: 'Enterprise lakehouses',
  other: 'Other sources',
};

export const CUSTOMER_GROUP_DESCRIPTION: Record<CustomerGroup, string> = {
  start_fast:
    'Upload CSV, Excel, or JSON files to test quality checks quickly.',
  connect_database:
    'Connect PostgreSQL, MySQL, SQL Server, or Oracle to validate operational data.',
  enterprise_warehouse:
    'Connect Snowflake, BigQuery, Redshift, or Synapse for analytics workloads.',
  enterprise_lakehouse:
    'Connect Databricks SQL / Unity Catalog or Iceberg-based lakehouses.',
  other: 'Additional connectors and integrations.',
};

export function customerGroupFor(spec: ConnectorSpec): CustomerGroup {
  switch (spec.category) {
    case 'file':
      return 'start_fast';
    case 'database':
      return 'connect_database';
    case 'warehouse':
      return 'enterprise_warehouse';
    case 'lakehouse':
    case 'object_storage':
    case 'query_engine':
      return 'enterprise_lakehouse';
    default:
      return 'other';
  }
}

/** Highlights for a connector card / details panel — at most three. */
export interface CustomerCapability {
  key: string;
  label: string;
}

export function customerCapabilitiesFor(
  spec: ConnectorSpec,
): CustomerCapability[] {
  const caps = spec.capabilities;
  const out: CustomerCapability[] = [];
  if (caps.supports_metadata_discovery) {
    out.push({ key: 'metadata', label: 'Metadata discovery' });
  }
  if (caps.supports_dataset_preview) {
    out.push({ key: 'preview', label: 'Dataset preview' });
  }
  if (caps.supports_check_execution) {
    out.push({ key: 'checks', label: 'Quality checks' });
  }
  if (caps.supports_pushdown_sql) {
    out.push({ key: 'rules', label: 'Rule execution' });
  }
  return out;
}

export function isConnectorLocalOnly(spec: ConnectorSpec): boolean {
  return (
    spec.capabilities.local_test_available &&
    !spec.capabilities.requires_external_credentials
  );
}

export function groupConnectorsByCategory(
  items: ConnectorSpec[],
): Array<{ category: ConnectorCategory; label: string; items: ConnectorSpec[] }> {
  const buckets = new Map<ConnectorCategory, ConnectorSpec[]>();
  for (const item of items) {
    const bucket = buckets.get(item.category) ?? [];
    bucket.push(item);
    buckets.set(item.category, bucket);
  }
  return (Object.keys(CATEGORY_LABELS) as ConnectorCategory[])
    .filter((c) => buckets.has(c))
    .map((c) => ({
      category: c,
      label: CATEGORY_LABELS[c],
      items: (buckets.get(c) ?? []).slice().sort((a, b) =>
        a.display_name.localeCompare(b.display_name),
      ),
    }));
}

const CUSTOMER_GROUP_ORDER: CustomerGroup[] = [
  'start_fast',
  'connect_database',
  'enterprise_warehouse',
  'enterprise_lakehouse',
  'other',
];

const STATUS_RANK: Record<ConnectorStatus, number> = {
  ready: 0,
  integration_ready: 1,
  deferred: 2,
};

/**
 * Group connectors by customer-facing buckets (Start fast, Database, etc.).
 * Sort order inside a group: status (Ready → Beta → Coming soon), then by
 * display name. This is what the onboarding catalog renders.
 */
export function groupConnectorsForCustomers(
  items: ConnectorSpec[],
): Array<{ group: CustomerGroup; label: string; description: string; items: ConnectorSpec[] }> {
  const buckets = new Map<CustomerGroup, ConnectorSpec[]>();
  for (const item of items) {
    const group = customerGroupFor(item);
    const bucket = buckets.get(group) ?? [];
    bucket.push(item);
    buckets.set(group, bucket);
  }
  return CUSTOMER_GROUP_ORDER.filter((g) => buckets.has(g)).map((g) => ({
    group: g,
    label: CUSTOMER_GROUP_LABEL[g],
    description: CUSTOMER_GROUP_DESCRIPTION[g],
    items: (buckets.get(g) ?? []).slice().sort((a, b) => {
      const r = STATUS_RANK[a.status] - STATUS_RANK[b.status];
      if (r !== 0) return r;
      return a.display_name.localeCompare(b.display_name);
    }),
  }));
}
