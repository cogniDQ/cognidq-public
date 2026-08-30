/**
 * API client for F001 tenant management endpoints.
 *
 * All calls go through the project-wide axios instance (`api`) which
 * automatically attaches the Bearer token from localStorage.
 */
import { api } from './api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TenantStatus = 'draft' | 'active' | 'suspended' | 'archived';
export type TenantRegion = 'eu-west' | 'eu-central' | 'us-east' | 'us-west';
export type TenantPlan = 'starter' | 'growth' | 'enterprise';
export type SortBy = 'created_at' | 'updated_at';
export type SortDir = 'asc' | 'desc';

export interface Tenant {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  status: TenantStatus;
  region: TenantRegion;
  plan: TenantPlan;
  created_at: string;
  updated_at: string;
}

export interface ListTenantsParams {
  status?: string;
  region?: string;
  plan?: string;
  q?: string;
  sort_by?: SortBy;
  sort_dir?: SortDir;
  include_archived?: boolean;
  page?: number;
  page_size?: number;
}

export interface ListTenantsResponse {
  data: Tenant[];
  meta: {
    total: number;
    page: number;
    page_size: number;
    has_next: boolean;
  };
}

// ---------------------------------------------------------------------------
// API methods
// ---------------------------------------------------------------------------

/**
 * Fetch a paginated, filtered list of tenants from the platform API.
 *
 * Undefined / empty-string parameters are stripped before building the
 * request so the backend receives clean query strings.
 */
export async function listTenants(
  params: ListTenantsParams = {}
): Promise<ListTenantsResponse> {
  // Strip undefined / empty values so the URL stays clean
  const query: Record<string, string | number | boolean> = {};

  if (params.status) query.status = params.status;
  if (params.region) query.region = params.region;
  if (params.plan) query.plan = params.plan;
  if (params.q) query.q = params.q;
  if (params.sort_by) query.sort_by = params.sort_by;
  if (params.sort_dir) query.sort_dir = params.sort_dir;
  if (params.include_archived != null) query.include_archived = params.include_archived;
  if (params.page != null) query.page = params.page;
  if (params.page_size != null) query.page_size = params.page_size;

  const response = await api.get<ListTenantsResponse>('/tenants', {
    params: query,
  });

  return response.data;
}

// ---------------------------------------------------------------------------
// Create Tenant
// ---------------------------------------------------------------------------

export interface CreateTenantRequest {
  tenant_name: string;
  tenant_slug: string;
  region: TenantRegion;
  plan: TenantPlan;
  initial_status?: 'draft' | 'active';
  service_start_date?: string;
  tenant_notes?: string;
}

/** Full tenant object returned from POST /api/v1/tenants (201 Created). */
export interface TenantDetail {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  status: TenantStatus;
  status_reason: string | null;
  region: TenantRegion;
  plan: TenantPlan;
  service_start_date: string | null;
  tenant_notes: string | null;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
}

export interface CreateTenantResponse {
  data: TenantDetail;
}

/** Structured API error field item from 422 responses. */
export interface ApiFieldError {
  field: string;
  reason: string;
}

/** Structured API error body shape returned on 4xx/5xx responses. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    fields: ApiFieldError[] | null;
  };
}

// ---------------------------------------------------------------------------
// Tenant Detail
// ---------------------------------------------------------------------------

/**
 * Full tenant object returned from GET /api/v1/tenants/{tenant_id}.
 * Extends TenantDetail with count fields and the audit summary link.
 */
export interface TenantDetailRecord {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  status: TenantStatus;
  status_reason: string | null;
  region: TenantRegion;
  plan: TenantPlan;
  service_start_date: string | null;
  tenant_notes: string | null;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
  /** Count of workspaces linked to this tenant. 0 when unavailable. */
  workspace_count: number;
  /** False when the Workspace Registry timed out or failed. */
  workspace_count_available: boolean;
  /** Count of users linked to this tenant. 0 when unavailable. */
  user_count: number;
  /** False when the User Registry timed out or failed. */
  user_count_available: boolean;
  /** Always `/api/v1/tenants/{id}/audit-logs` */
  audit_summary_link: string;
}

export interface TenantDetailResponse {
  data: TenantDetailRecord;
}

/**
 * Fetch a single tenant by ID via GET /api/v1/tenants/{tenant_id}.
 * Requires Platform Admin or Platform Viewer role.
 */
export async function getTenantDetail(tenant_id: string): Promise<TenantDetailResponse> {
  const response = await api.get<TenantDetailResponse>(`/tenants/${tenant_id}`);
  return response.data;
}

// ---------------------------------------------------------------------------
// Create Tenant
// ---------------------------------------------------------------------------

/**
 * Create a new tenant via POST /api/v1/tenants.
 * Requires Platform Admin role (enforced server-side; route-guarded client-side).
 */
export async function createTenant(
  body: CreateTenantRequest,
): Promise<CreateTenantResponse> {
  const response = await api.post<CreateTenantResponse>('/tenants', body);
  return response.data;
}

// ---------------------------------------------------------------------------
// Update Tenant Metadata (PATCH)
// ---------------------------------------------------------------------------

/**
 * Mutable fields only — immutable fields (slug, region) must never be sent.
 * Only include fields whose value has changed (change-set detection).
 * TDD §3.5.
 */
export interface UpdateTenantRequest {
  tenant_name?: string;
  plan?: TenantPlan;
  /** null clears an existing reason; not allowed while tenant is suspended/archived. */
  status_reason?: string | null;
  /** null clears an existing date. YYYY-MM-DD format or null. */
  service_start_date?: string | null;
  /** null clears existing notes. */
  tenant_notes?: string | null;
}

/** 200 response from PATCH /api/v1/tenants/{id} — same core shape as TenantDetail. */
export interface UpdateTenantResponse {
  data: TenantDetail;
}

/**
 * Update mutable tenant metadata via PATCH /api/v1/tenants/{tenant_id}.
 * Requires Platform Admin role.
 */
export async function updateTenantMetadata(
  tenant_id: string,
  body: UpdateTenantRequest,
): Promise<UpdateTenantResponse> {
  const response = await api.patch<UpdateTenantResponse>(
    `/tenants/${tenant_id}`,
    body,
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Change Tenant Status (POST /status)
// ---------------------------------------------------------------------------

/**
 * Target status the tenant should transition to. TDD §3.6.
 * Transition rules are enforced server-side (§2.6 matrix).
 */
export interface ChangeTenantStatusRequest {
  target_status: TenantStatus;
  /** Required when target_status is 'suspended' or 'archived'. Must NOT be supplied for 'active'. */
  status_reason?: string;
}

/** 200 response from POST /api/v1/tenants/{id}/status. */
export interface ChangeTenantStatusResponse {
  data: {
    tenant_id: string;
    previous_status: TenantStatus;
    current_status: TenantStatus;
    /** null when transitioning to active (automatically cleared by server). */
    status_reason: string | null;
    updated_at: string;
    updated_by: string;
  };
}

/**
 * Trigger a tenant status transition via POST /api/v1/tenants/{tenant_id}/status.
 * Requires Platform Admin role.
 */
export async function changeTenantStatus(
  tenant_id: string,
  body: ChangeTenantStatusRequest,
): Promise<ChangeTenantStatusResponse> {
  const response = await api.post<ChangeTenantStatusResponse>(
    `/tenants/${tenant_id}/status`,
    body,
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Hard Delete Tenant
// ---------------------------------------------------------------------------

/**
 * Permanently delete a tenant and every dependent row via
 * DELETE /api/v1/tenants/{tenant_id}.  Restricted to Platform Admin.
 *
 * Backend returns 204 No Content on success.  This is irreversible — the
 * caller is responsible for confirming with the user before invoking.
 */
export async function deleteTenant(tenant_id: string): Promise<void> {
  await api.delete(`/tenants/${tenant_id}`);
}
