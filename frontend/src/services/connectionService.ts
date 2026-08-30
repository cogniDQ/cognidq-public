/**
 * F130 — Tenant Connection API service
 *
 * Wraps all 8 `/api/v1/tenants/{tenant_id}/connections` endpoints.
 * tenantId is always derived from the caller (usually from the JWT claim).
 */
import { api } from './api';

// ── Types ────────────────────────────────────────────────────────────────────

export type ConnectionEnvironment = 'development' | 'staging' | 'production';
export type ConnectionMode = 'direct' | 'agent';

export interface Connection {
  connection_id: string;
  tenant_id: string;
  source_name: string;
  source_type: string;
  connection_mode: ConnectionMode;
  environment: ConnectionEnvironment;
  description: string | null;
  status: string;
  last_test_status: string | null;
  last_tested_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConnectionListResponse {
  items: Connection[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateConnectionPayload {
  name: string;
  source_type: string;
  connection_mode: ConnectionMode;
  environment: ConnectionEnvironment;
  description?: string;
  credentials: Record<string, unknown>;
  workspace_ids: string[];
}

export interface UpdateConnectionPayload {
  name?: string;
  description?: string;
  environment?: ConnectionEnvironment;
}

export interface WorkspaceAssignment {
  workspace_id: string;
  assigned_at: string;
}

export interface ConnectionTestResult {
  success: boolean;
  message: string;
  latency_ms: number | null;
}

// ── API helpers ───────────────────────────────────────────────────────────────

const base = (tenantId: string) =>
  `/tenants/${tenantId}/connections`;

export async function listConnections(
  tenantId: string,
  params: {
    page?: number;
    page_size?: number;
    search?: string;
    status?: string;
    workspace_id?: string;
  } = {},
): Promise<ConnectionListResponse> {
  const res = await api.get<ConnectionListResponse>(base(tenantId), { params });
  return res.data;
}

export async function createConnection(
  tenantId: string,
  payload: CreateConnectionPayload,
): Promise<Connection> {
  // Tenant-scoped create: a single atomic call that inserts the data_source
  // row, encrypts credentials, and assigns the connection to the chosen
  // workspaces. workspace_id is intentionally not persisted on data_sources
  // any more — access is governed by control.workspace_connection_assignments.
  const { name, ...rest } = payload;
  const body = { source_name: name, ...rest };
  const res = await api.post<{ connection_id: string } & Record<string, unknown>>(
    base(tenantId),
    body,
  );
  return res.data as unknown as Connection;
}

export async function getConnection(
  tenantId: string,
  connectionId: string,
): Promise<Connection> {
  const res = await api.get<Connection>(`${base(tenantId)}/${connectionId}`);
  return res.data;
}

export async function updateConnection(
  tenantId: string,
  connectionId: string,
  payload: UpdateConnectionPayload,
): Promise<Connection> {
  const res = await api.patch<Connection>(
    `${base(tenantId)}/${connectionId}`,
    payload,
  );
  return res.data;
}

export async function deleteConnection(
  tenantId: string,
  connectionId: string,
): Promise<void> {
  await api.delete(`${base(tenantId)}/${connectionId}`);
}

export async function testConnection(
  tenantId: string,
  connectionId: string,
): Promise<ConnectionTestResult> {
  const res = await api.post<ConnectionTestResult>(
    `${base(tenantId)}/${connectionId}/test`,
  );
  return res.data;
}

/**
 * Test a connection configuration *before* saving.
 * Calls POST /workspaces/{workspaceId}/data-sources/test-config
 */
export async function testConnectionConfig(
  workspaceId: string,
  sourceType: string,
  credentials: Record<string, unknown>,
): Promise<ConnectionTestResult> {
  const res = await api.post<ConnectionTestResult>(
    `/workspaces/${workspaceId}/data-sources/test-config`,
    { type: sourceType, connection_config: credentials },
  );
  return res.data;
}

export async function getConnectionAssignments(
  tenantId: string,
  connectionId: string,
): Promise<WorkspaceAssignment[]> {
  const res = await api.get<{ items: WorkspaceAssignment[] } | WorkspaceAssignment[]>(
    `${base(tenantId)}/${connectionId}/workspaces`,
  );
  // Backend wraps in { items: [...] }
  const data = res.data as { items?: WorkspaceAssignment[] };
  return data.items ?? (res.data as WorkspaceAssignment[]);
}

export async function replaceConnectionAssignments(
  tenantId: string,
  connectionId: string,
  workspaceIds: string[],
): Promise<WorkspaceAssignment[]> {
  const res = await api.put<{ items: WorkspaceAssignment[] } | WorkspaceAssignment[]>(
    `${base(tenantId)}/${connectionId}/workspaces`,
    { workspace_ids: workspaceIds },
  );
  const data = res.data as { items?: WorkspaceAssignment[] };
  return data.items ?? (res.data as WorkspaceAssignment[]);
}
