/**
 * F004 — Data Source API service
 *
 * Wraps all 8 `/api/v1/workspaces/{workspace_id}/data-sources` endpoints.
 */
import { api } from './api';
import type {
  CreateDataSourcePayload,
  UpdateDataSourcePayload,
  DataSourceListParams,
  DataSourceListResponse,
  DataSourceDetailResponse,
  ConnectionTestResult,
  AuditLogResponse,
} from '../types/dataSource';

const base = (workspaceId: string) =>
  `/workspaces/${workspaceId}/data-sources`;

export async function listDataSources(
  workspaceId: string,
  params: DataSourceListParams = {},
): Promise<DataSourceListResponse> {
  const res = await api.get<DataSourceListResponse>(base(workspaceId), {
    params,
  });
  return res.data;
}

export async function getDataSource(
  workspaceId: string,
  dataSourceId: string,
): Promise<DataSourceDetailResponse> {
  const res = await api.get<DataSourceDetailResponse>(
    `${base(workspaceId)}/${dataSourceId}`,
  );
  return res.data;
}

export async function createDataSource(
  workspaceId: string,
  payload: CreateDataSourcePayload,
): Promise<DataSourceDetailResponse> {
  const res = await api.post<DataSourceDetailResponse>(
    base(workspaceId),
    payload,
  );
  return res.data;
}

export async function updateDataSource(
  workspaceId: string,
  dataSourceId: string,
  payload: UpdateDataSourcePayload,
): Promise<DataSourceDetailResponse> {
  const res = await api.patch<DataSourceDetailResponse>(
    `${base(workspaceId)}/${dataSourceId}`,
    payload,
  );
  return res.data;
}

export async function testConnection(
  workspaceId: string,
  dataSourceId: string,
): Promise<ConnectionTestResult> {
  const res = await api.post<ConnectionTestResult>(
    `${base(workspaceId)}/${dataSourceId}/test-connection`,
  );
  return res.data;
}

export async function archiveDataSource(
  workspaceId: string,
  dataSourceId: string,
): Promise<DataSourceDetailResponse> {
  const res = await api.post<DataSourceDetailResponse>(
    `${base(workspaceId)}/${dataSourceId}/archive`,
  );
  return res.data;
}

export async function restoreDataSource(
  workspaceId: string,
  dataSourceId: string,
): Promise<DataSourceDetailResponse> {
  const res = await api.post<DataSourceDetailResponse>(
    `${base(workspaceId)}/${dataSourceId}/restore`,
  );
  return res.data;
}

export async function getDataSourceAuditLogs(
  workspaceId: string,
  dataSourceId: string,
  page = 1,
): Promise<AuditLogResponse> {
  const res = await api.get<AuditLogResponse>(
    `${base(workspaceId)}/${dataSourceId}/audit-logs`,
    { params: { page, page_size: 20 } },
  );
  return res.data;
}

// ─── Schema browsing ──────────────────────────────────────────────────────────

export interface BrowseColumnInfo {
  column_name: string;
  data_type: string;
  ordinal_position: number;
  nullable: boolean;
  is_primary_key: boolean;
}

export interface BrowseSchemaObject {
  object_name: string;
  object_type: 'table' | 'view';
  schema_name: string;
  columns: BrowseColumnInfo[];
}

export interface BrowseSchema {
  schema_name: string;
  objects: BrowseSchemaObject[];
}

export interface BrowseDataSourceResponse {
  data_source_id: string;
  source_type: string;
  schemas: BrowseSchema[];
}

export async function browseDataSource(
  workspaceId: string,
  dataSourceId: string,
): Promise<BrowseDataSourceResponse> {
  const res = await api.get<BrowseDataSourceResponse>(
    `${base(workspaceId)}/${dataSourceId}/browse`,
  );
  return res.data;
}

// Backward-compatibility shim so legacy imports (`import datasourceService from './datasource'`)
// don't crash the module graph. The old hub page (DataSources.tsx) and wizard still use the
// default export; new F004 pages use the named exports above.
const datasourceService = {
  getAll: async (orgId: string) => {
    const res = await api.get(`/workspaces/${orgId}/data-sources`);
    const items: DataSource[] = res.data?.items ?? [];
    // Map F004 fields to legacy field names expected by DataSources.tsx
    return items.map(ds => ({
      ...ds,
      id: ds.data_source_id,
      name: ds.source_name,
      type: ds.source_type,
      connection_config: (ds as DataSource & { connection_config?: Record<string, unknown> }).connection_config,
    }));
  },
  getById: async (orgId: string, id: string) => {
    const res = await api.get(`/workspaces/${orgId}/data-sources/${id}`);
    const ds = res.data as DataSource & { connection_config?: Record<string, unknown> };
    return { ...ds, id: ds.data_source_id, name: ds.source_name, type: ds.source_type };
  },
  create: async (orgId: string, data: { name?: string; source_name?: string; type?: string; source_type?: string; connection_config?: Record<string, unknown>; credentials?: Record<string, unknown>; connection_mode?: string; environment?: string; description?: string }) => {
    const res = await api.post(
      `/workspaces/${orgId}/data-sources`,
      {
        source_name: data.source_name ?? data.name,
        source_type: data.source_type ?? data.type,
        connection_mode: data.connection_mode ?? 'direct',
        environment: data.environment ?? 'development',
        description: data.description,
        credentials: data.credentials ?? data.connection_config ?? {},
      },
    );
    return res.data;
  },
  update: async (_orgId: string, _id: string, _data: unknown) => null as never,
  delete: async (_orgId: string, _id: string) => {},
  testConnectionConfig: async (orgId: string, req: { type: string; connection_config: Record<string, unknown> }) => {
    const res = await api.post<{ success: boolean; message: string; details?: Record<string, unknown>; tested_at: string }>(
      `/workspaces/${orgId}/data-sources/test-config`,
      req,
    );
    return res.data;
  },
  testConnection: async (_orgId: string, _id: string) => null as never,
  refreshSchema: async (_orgId: string, _id: string) => null as never,
  getSchemas: async (_orgId: string, _id: string) => null as never,
  getTablePreview: async () => null as never,
};
export default datasourceService;

// Legacy type aliases for old imports
export type { DataSource } from '../types/dataSource';
export type SchemaInfo = Record<string, unknown>;
