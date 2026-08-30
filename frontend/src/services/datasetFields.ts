/**
 * E2 — candidate enrichment with table preview.
 *
 * Lightweight client for `/workspaces/:wid/datasets/:dataset_id/fields`,
 * used by the NL Rule Builder to preview representative values for a
 * candidate column.
 */
import { api } from './api';

export interface DatasetFieldSummary {
  field_id: string;
  field_name: string;
  data_type: string;
  nullable: boolean;
  business_definition: string | null;
  sensitivity_classification: string;
  is_key_candidate: boolean;
  ordinal_position: number;
  sample_values: string[];
  sample_values_updated_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export async function listDatasetFields(
  workspaceId: string,
  datasetId: string,
): Promise<DatasetFieldSummary[]> {
  const response = await api.get<DatasetFieldSummary[]>(
    `/workspaces/${workspaceId}/datasets/${datasetId}/fields`,
  );
  return response.data;
}

export async function getDatasetFieldSample(
  workspaceId: string,
  datasetId: string,
  fieldName: string,
): Promise<DatasetFieldSummary | null> {
  const fields = await listDatasetFields(workspaceId, datasetId);
  const lower = fieldName.trim().toLowerCase();
  return (
    fields.find((f) => (f.field_name ?? '').toLowerCase() === lower) ?? null
  );
}
