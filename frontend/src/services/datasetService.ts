/**
 * F005 — Dataset API service
 *
 * Wraps all dataset endpoints.
 */
import { api } from './api';
import type {
  AddFieldPayload,
  BulkImportFieldsPayload,
  BulkImportFieldsResponse,
  CreateDatasetPayload,
  Dataset,
  DatasetField,
  DatasetListParams,
  DatasetListResponse,
  UpdateDatasetPayload,
} from '../types/dataset';

const base = (workspaceId: string) =>
  `/workspaces/${workspaceId}/datasets`;

export async function listDatasets(
  workspaceId: string,
  params: DatasetListParams = {},
): Promise<DatasetListResponse> {
  const res = await api.get<DatasetListResponse>(base(workspaceId), { params });
  return res.data;
}

export async function getDataset(
  workspaceId: string,
  datasetId: string,
): Promise<Dataset> {
  const res = await api.get<Dataset>(`${base(workspaceId)}/${datasetId}`);
  return res.data;
}

export async function createDataset(
  workspaceId: string,
  payload: CreateDatasetPayload,
): Promise<Dataset> {
  const res = await api.post<Dataset>(base(workspaceId), payload);
  return res.data;
}

export async function updateDataset(
  workspaceId: string,
  datasetId: string,
  payload: UpdateDatasetPayload,
): Promise<Dataset> {
  const res = await api.patch<Dataset>(`${base(workspaceId)}/${datasetId}`, payload);
  return res.data;
}

export async function activateDataset(
  workspaceId: string,
  datasetId: string,
): Promise<Dataset> {
  const res = await api.post<Dataset>(`${base(workspaceId)}/${datasetId}/activate`);
  return res.data;
}

export async function deactivateDataset(
  workspaceId: string,
  datasetId: string,
): Promise<Dataset> {
  const res = await api.post<Dataset>(`${base(workspaceId)}/${datasetId}/deactivate`);
  return res.data;
}

export async function reactivateDataset(
  workspaceId: string,
  datasetId: string,
): Promise<Dataset> {
  const res = await api.post<Dataset>(`${base(workspaceId)}/${datasetId}/reactivate`);
  return res.data;
}

export async function archiveDataset(
  workspaceId: string,
  datasetId: string,
): Promise<Dataset> {
  const res = await api.post<Dataset>(`${base(workspaceId)}/${datasetId}/archive`);
  return res.data;
}

export async function getDatasetAuditLogs(
  workspaceId: string,
  datasetId: string,
  page = 1,
): Promise<{ items: any[]; total: number; page: number; page_size: number }> {
  const res = await api.get(
    `${base(workspaceId)}/${datasetId}/audit-logs`,
    { params: { page, page_size: 20 } },
  );
  return res.data;
}

export async function listFields(
  workspaceId: string,
  datasetId: string,
): Promise<DatasetField[]> {
  const res = await api.get<DatasetField[]>(
    `${base(workspaceId)}/${datasetId}/fields`,
  );
  return res.data;
}

export async function addField(
  workspaceId: string,
  datasetId: string,
  payload: AddFieldPayload,
): Promise<DatasetField> {
  const res = await api.post<DatasetField>(
    `${base(workspaceId)}/${datasetId}/fields`,
    payload,
  );
  return res.data;
}

export async function bulkImportFields(
  workspaceId: string,
  datasetId: string,
  payload: BulkImportFieldsPayload,
): Promise<BulkImportFieldsResponse> {
  const res = await api.post<BulkImportFieldsResponse>(
    `${base(workspaceId)}/${datasetId}/fields/bulk-import`,
    payload,
  );
  return res.data;
}

export async function removeField(
  workspaceId: string,
  datasetId: string,
  fieldId: string,
): Promise<void> {
  await api.delete(`${base(workspaceId)}/${datasetId}/fields/${fieldId}`);
}

// F121 — Dataset Profiling
export interface DatasetProfile {
  dataset_id: string;
  total_rows: number;
  total_columns: number;
  columns: ColumnProfile[];
  profiled_at: string | null;
  message?: string;
}

export interface ColumnProfile {
  name: string;
  data_type: string;
  total_count: number;
  null_count: number;
  null_percentage: number;
  unique_count: number;
  cardinality: number;
  min_value: any;
  max_value: any;
  mean: number | null;
  median: number | null;
  std_dev: number | null;
  top_values: { value: string; count: number }[];
  suggested_checks: string[];
}

export async function profileDataset(
  workspaceId: string,
  datasetId: string,
  sampleSize: number = 10000,
): Promise<DatasetProfile> {
  const res = await api.post<DatasetProfile>(
    `${base(workspaceId)}/${datasetId}/profile`,
    null,
    { params: { sample_size: sampleSize } },
  );
  return res.data;
}

// F-CONN-P0 — Live dataset preview backed by the connector registry.
// See `backend/app/api/v1/endpoints/datasets.py::preview_dataset`.
export interface DatasetPreviewResponse {
  dataset_id: string;
  schema_name: string | null;
  table_name: string;
  row_limit: number;
  row_count: number;
  columns: string[];
  rows: Record<string, unknown>[];
  truncated_columns: string[];
}

export const DATASET_PREVIEW_MIN_ROWS = 1;
export const DATASET_PREVIEW_MAX_ROWS = 1000;
export const DATASET_PREVIEW_DEFAULT_ROWS = 100;

export async function getDatasetPreview(
  workspaceId: string,
  datasetId: string,
  limit: number = DATASET_PREVIEW_DEFAULT_ROWS,
): Promise<DatasetPreviewResponse> {
  const res = await api.get<DatasetPreviewResponse>(
    `${base(workspaceId)}/${datasetId}/preview`,
    { params: { limit } },
  );
  return res.data;
}
