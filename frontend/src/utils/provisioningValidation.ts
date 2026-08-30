/**
 * Client-side validators for Provisioning form fields.
 *
 * Reuses existing tenant validators where applicable and adds
 * provisioning-specific validators (admin email, workspace fields).
 */

import {
  validateTenantName,
  validateTenantSlug,
  validateRegion,
  validatePlan,
  validateServiceStartDate,
  validateTenantNotes,
} from './tenantValidation';

// ---------------------------------------------------------------------------
// Per-field validators
// ---------------------------------------------------------------------------

const EMAIL_RE = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;

export function validateAdminEmail(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) return 'This field is required.';
  if (trimmed.length > 255) return 'Maximum 255 characters.';
  if (!EMAIL_RE.test(trimmed)) return 'Enter a valid email address.';
  return undefined;
}

export function validateAdminFullName(value: string): string | undefined {
  if (!value.trim()) return undefined; // optional
  if (value.trim().length > 255) return 'Maximum 255 characters.';
  return undefined;
}

export function validateWorkspaceName(value: string): string | undefined {
  if (!value.trim()) return undefined; // optional — will default to "Default Workspace"
  if (value.trim().length > 100) return 'Maximum 100 characters.';
  return undefined;
}

const WORKSPACE_SLUG_RE = /^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$/;

export function validateWorkspaceSlug(value: string): string | undefined {
  if (!value.trim()) return undefined; // optional — will default to "default"
  const slug = value.trim().toLowerCase();
  if (slug.length > 50) return 'Maximum 50 characters.';
  if (!WORKSPACE_SLUG_RE.test(slug)) {
    return 'Only lowercase letters, digits, and hyphens are allowed.';
  }
  return undefined;
}

// ---------------------------------------------------------------------------
// Full-form types and validators
// ---------------------------------------------------------------------------

export interface ProvisionFormValues {
  tenant_name: string;
  tenant_slug: string;
  region: string;
  plan: string;
  service_start_date: string;
  tenant_notes: string;
  admin_email: string;
  admin_full_name: string;
  workspace_name: string;
  workspace_slug: string;
}

export type ProvisionFormErrors = Partial<Record<keyof ProvisionFormValues, string>>;

export function validateProvisionAll(values: ProvisionFormValues): ProvisionFormErrors {
  return {
    tenant_name: validateTenantName(values.tenant_name),
    tenant_slug: validateTenantSlug(values.tenant_slug),
    region: validateRegion(values.region),
    plan: validatePlan(values.plan),
    service_start_date: validateServiceStartDate(values.service_start_date),
    tenant_notes: validateTenantNotes(values.tenant_notes),
    admin_email: validateAdminEmail(values.admin_email),
    admin_full_name: validateAdminFullName(values.admin_full_name),
    workspace_name: validateWorkspaceName(values.workspace_name),
    workspace_slug: validateWorkspaceSlug(values.workspace_slug),
  };
}

export function hasNoProvisionErrors(errors: ProvisionFormErrors): boolean {
  return Object.values(errors).every((v) => v === undefined);
}

// Re-export base validators for individual field use
export {
  validateTenantName,
  validateTenantSlug,
  validateRegion,
  validatePlan,
  validateServiceStartDate,
  validateTenantNotes,
};
