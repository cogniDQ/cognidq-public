/**
 * F004 — Data Source TypeScript interfaces
 *
 * All shapes mirror the JSON produced by `/api/v1/workspaces/{workspace_id}/data-sources/*`.
 */

// ─── Enumerations ─────────────────────────────────────────────────────────────

export type SourceType = 'postgresql' | 'mysql' | 'mssql' | 'oracle' | 'snowflake' | 'bigquery';
export type ConnectionMode = 'direct' | 'agent';
export type DataSourceEnvironment = 'development' | 'staging' | 'production';
export type DataSourceStatus = 'active' | 'archived';
export type LastTestStatus = 'untested' | 'reachable' | 'unreachable' | 'test_failed';

// ─── Core shapes ──────────────────────────────────────────────────────────────

export interface DataSource {
  data_source_id: string;
  workspace_id: string;
  tenant_id: string;
  source_name: string;
  source_type: SourceType;
  connection_mode: ConnectionMode;
  environment: DataSourceEnvironment;
  description: string | null;
  status: DataSourceStatus;
  last_test_status: LastTestStatus;
  last_tested_at: string | null;
  credential_reference: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  created_by: string | null;
  updated_by: string | null;
  archived_at: string | null;
  archived_by: string | null;
}

export interface DataSourceListMeta {
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface DataSourceListResponse {
  items: DataSource[];
  meta: DataSourceListMeta;
}

export interface DataSourceDetailResponse {
  data_source_id: string;
  workspace_id: string;
  tenant_id: string;
  source_name: string;
  source_type: SourceType;
  connection_mode: ConnectionMode;
  environment: DataSourceEnvironment;
  description: string | null;
  status: DataSourceStatus;
  last_test_status: LastTestStatus;
  last_tested_at: string | null;
  credential_reference: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  created_by: string | null;
  updated_by: string | null;
  archived_at: string | null;
  archived_by: string | null;
}

// ─── Credential shapes (write-only; never returned by API) ────────────────────

export interface JdbcCredentials {
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
  ssl?: boolean;
}

export interface SnowflakeCredentials {
  account_identifier: string;
  account: string;
  warehouse: string;
  database: string;
  username: string;
  password: string;
}

export interface BigQueryCredentials {
  project_id: string;
  service_account_json: string; // JSON string
}

export type DataSourceCredentials = JdbcCredentials | SnowflakeCredentials | BigQueryCredentials;

// ─── Request/Response shapes ──────────────────────────────────────────────────

export interface CreateDataSourcePayload {
  source_name: string;
  source_type: SourceType;
  connection_mode: ConnectionMode;
  environment: DataSourceEnvironment;
  description?: string | null;
  credentials: DataSourceCredentials;
}

export interface UpdateDataSourcePayload {
  source_name?: string;
  environment?: DataSourceEnvironment;
  description?: string | null;
  credentials?: DataSourceCredentials;
}

export interface ConnectionTestResult {
  status: LastTestStatus;
  tested_at: string;
  error_summary: string | null;
  latency_ms: number | null;
}

export interface AuditLogEntry {
  log_id: string;
  workspace_id?: string;
  action_type: string;
  actor_id: string | null;
  actor_role?: string | null;
  entity_type?: string;
  entity_id?: string;
  old_data?: Record<string, unknown> | null;
  new_data?: Record<string, unknown> | null;
  previous_data?: Record<string, unknown> | null;
  occurred_at: string | null;
}

export interface AuditLogResponse {
  items: AuditLogEntry[];
  meta: DataSourceListMeta;
}

// ─── Filter params ────────────────────────────────────────────────────────────

export interface DataSourceListParams {
  page?: number;
  page_size?: number;
  status?: DataSourceStatus | '';
  source_type?: SourceType | '';
  environment?: DataSourceEnvironment | '';
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
}
