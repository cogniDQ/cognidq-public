/**
 * API client for Tenant Provisioning endpoints.
 *
 * All calls go through the project-wide axios instance (`api`) which
 * automatically attaches the Bearer token from localStorage.
 */
import { api } from './api';
import type { TenantRegion, TenantPlan } from './tenant';

// ---------------------------------------------------------------------------
// Request types
// ---------------------------------------------------------------------------

export interface ProvisionTenantRequest {
  /** Tenant display name (1-100 chars) */
  tenant_name: string;
  /** Tenant URL slug (2-50 chars, lowercase alphanumeric + hyphens) */
  tenant_slug: string;
  /** Deployment region */
  region: TenantRegion;
  /** Subscription plan */
  plan: TenantPlan;
  /** Service start date (YYYY-MM-DD, optional) */
  service_start_date?: string;
  /** Internal notes (optional) */
  tenant_notes?: string;
  /** Admin user email address */
  admin_email: string;
  /** Admin user full name (optional) */
  admin_full_name?: string;
  /** Custom workspace name (defaults to "Default Workspace") */
  workspace_name?: string;
  /** Custom workspace slug (defaults to "default") */
  workspace_slug?: string;
}

// ---------------------------------------------------------------------------
// Response types
// ---------------------------------------------------------------------------

export interface ProvisionedTenant {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  status: string;
  region: TenantRegion;
  plan: TenantPlan;
  provisioning_status: string;
  created_at: string;
}

export interface ProvisionedWorkspace {
  workspace_id: string;
  workspace_name: string;
  workspace_slug: string;
}

export interface ProvisionedAdmin {
  user_id: string;
  email: string;
  full_name: string | null;
  status: string;
}

export interface ProvisioningInvitation {
  password_reset_token: string;
  activation_url: string;
  expires_in_hours: number;
}

export interface ProvisioningStep {
  step_name: string;
  step_order: number;
  status: string;
}

export interface ProvisionTenantResponseData {
  tenant: ProvisionedTenant;
  workspace: ProvisionedWorkspace;
  admin: ProvisionedAdmin;
  invitation: ProvisioningInvitation;
  provisioning_steps: ProvisioningStep[];
}

export interface ProvisionTenantResponse {
  data: ProvisionTenantResponseData;
}

// ---------------------------------------------------------------------------
// Provisioning Log types
// ---------------------------------------------------------------------------

export interface ProvisioningLogEntry {
  log_id: string;
  step_name: string;
  step_order: number;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  step_data: Record<string, unknown> | null;
}

export interface ProvisioningLogsResponse {
  data: ProvisioningLogEntry[];
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
// API methods
// ---------------------------------------------------------------------------

/**
 * Provision a new tenant with default workspace and admin account.
 * Requires Platform Admin role.
 */
export async function provisionTenant(
  body: ProvisionTenantRequest,
): Promise<ProvisionTenantResponse> {
  const response = await api.post<ProvisionTenantResponse>(
    '/tenants/provision',
    body,
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Provision existing tenant
// ---------------------------------------------------------------------------

export interface ProvisionExistingTenantRequest {
  /** Admin user email (required). */
  admin_email: string;
  /** Admin user full name (optional). */
  admin_full_name?: string;
  /** Custom workspace name (defaults from tenant name). */
  workspace_name?: string;
  /** Custom workspace slug (defaults from tenant slug). */
  workspace_slug?: string;
}

/**
 * Provision the default workspace + admin account against an existing
 * tenant. Requires Platform Admin role.
 */
export async function provisionExistingTenant(
  tenantId: string,
  body: ProvisionExistingTenantRequest,
): Promise<ProvisionTenantResponse> {
  const response = await api.post<ProvisionTenantResponse>(
    `/tenants/${tenantId}/provision`,
    body,
  );
  return response.data;
}

/**
 * Fetch provisioning step logs for a tenant.
 * Requires Platform Admin or Platform Viewer role.
 */
export async function getProvisioningLogs(
  tenant_id: string,
): Promise<ProvisioningLogsResponse> {
  const response = await api.get<ProvisioningLogsResponse>(
    `/tenants/${tenant_id}/provisioning-logs`,
  );
  return response.data;
}
