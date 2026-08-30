/**
 * F005 — Dataset TypeScript interfaces
 *
 * All shapes mirror the JSON produced by `/api/v1/workspaces/{workspace_id}/datasets/*`.
 */

// ─── Enumerations ─────────────────────────────────────────────────────────────

export type DatasetStatus = 'draft' | 'active' | 'inactive' | 'archived';
export type DatasetType = 'table' | 'view' | 'file' | 'logical';
export type Criticality = 'low' | 'medium' | 'high' | 'critical';
export type SensitivityClassification = 'public' | 'internal' | 'confidential' | 'restricted';

// ─── Core shapes ──────────────────────────────────────────────────────────────

export interface DatasetField {
  field_id: string;
  field_name: string;
  data_type: string;
  nullable: boolean;
  business_definition: string | null;
  sensitivity_classification: SensitivityClassification;
  is_key_candidate: boolean;
  ordinal_position: number;
  created_at: string;
  updated_at: string;
  // F121 — profile-derived enrichment (populated after Run Profile)
  null_count?: number | null;
  distinct_count?: number | null;
  min_value?: string | null;
  max_value?: string | null;
  profile_stats?: Record<string, unknown> | null;
  profiled_at?: string | null;
}

export interface Dataset {
  dataset_id: string;
  workspace_id: string;
  tenant_id: string;
  data_source_id: string | null;
  data_source_name: string | null;
  dataset_name: string;
  dataset_type: DatasetType;
  physical_identifier: string;
  schema_name: string | null;
  description: string | null;
  business_domain: string | null;
  criticality: Criticality;
  owner_user_id: string | null;
  freshness_expectation: string | null;
  status: DatasetStatus;
  field_count: number;
  fields?: DatasetField[];
  created_at: string;
  updated_at: string;
  created_by: string | null;
  updated_by: string | null;
  activated_at: string | null;
  archived_at: string | null;
  archived_by: string | null;
  // F121 — last profile run
  last_profiled_at?: string | null;
  last_profile?: Record<string, unknown> | null;
}

export interface DatasetListItem {
  dataset_id: string;
  workspace_id: string;
  dataset_name: string;
  dataset_type: DatasetType;
  data_source_id: string | null;
  data_source_name: string | null;
  physical_identifier: string;
  business_domain: string | null;
  criticality: Criticality;
  owner_user_id: string | null;
  status: DatasetStatus;
  field_count: number;
  created_at: string;
  updated_at: string;
}

export interface DatasetListResponse {
  items: DatasetListItem[];
  total: number;
  page: number;
  page_size: number;
}

// ─── Request shapes ───────────────────────────────────────────────────────────

export interface DatasetListParams {
  page?: number;
  page_size?: number;
  status?: DatasetStatus | '';
  data_source_id?: string;
  owner_user_id?: string;
  business_domain?: string;
  criticality?: string;
  dataset_type?: DatasetType | '';
  search?: string;
  sort_by?: string;
  sort_dir?: string;
}

export interface CreateDatasetPayload {
  data_source_id?: string | null;
  dataset_name: string;
  dataset_type: DatasetType;
  physical_identifier: string;
  schema_name?: string | null;
  description?: string | null;
  business_domain?: string | null;
  criticality?: Criticality;
  owner_user_id?: string | null;
  freshness_expectation?: string | null;
}

export interface UpdateDatasetPayload {
  dataset_name?: string;
  description?: string | null;
  business_domain?: string | null;
  criticality?: Criticality;
  owner_user_id?: string | null;
  freshness_expectation?: string | null;
  schema_name?: string | null;
}

export interface AddFieldPayload {
  field_name: string;
  data_type: string;
  nullable?: boolean;
  business_definition?: string | null;
  sensitivity_classification?: SensitivityClassification;
  is_key_candidate?: boolean;
}

export interface BulkImportFieldsPayload {
  mode: 'append' | 'replace';
  fields: AddFieldPayload[];
}

export interface BulkImportFieldsResponse {
  imported_count: number;
  mode: string;
  fields: DatasetField[];
}
