/**
 * Client-side validators for F001 tenant form fields.
 *
 * Rules mirror TDD §6.1–§6.8 exactly so the UI catches the same violations
 * the server would catch, preventing unnecessary round-trips.
 *
 * Each function returns undefined when the value is valid, or a human-
 * readable error string when it is not.
 */

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Control characters U+0000–U+001F and U+007F */
// eslint-disable-next-line no-control-regex -- intentional control-char rejection for input sanitization
const CONTROL_CHARS = /[\x00-\x1F\x7F]/;

/** Characters forbidden in tenant_name per TDD §6.1 */
const FORBIDDEN_NAME_CHARS = /[<>&"'`]/;

// ---------------------------------------------------------------------------
// Per-field validators
// ---------------------------------------------------------------------------

export function validateTenantName(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) return 'This field is required.';
  if (trimmed.length < 2) return 'Minimum 2 characters.';
  if (trimmed.length > 150) return 'Maximum 150 characters.';
  if (FORBIDDEN_NAME_CHARS.test(trimmed) || CONTROL_CHARS.test(trimmed)) {
    return 'Name contains invalid characters (< > & " \' ` or control characters are not allowed).';
  }
  return undefined;
}

export function validateTenantSlug(value: string): string | undefined {
  const normalized = value.trim().toLowerCase();
  if (!normalized) return 'This field is required.';
  if (normalized.length < 3) return 'Minimum 3 characters.';
  if (normalized.length > 80) return 'Maximum 80 characters.';
  if (!/^[a-z0-9-]+$/.test(normalized)) {
    return 'Only lowercase letters, digits, and hyphens are allowed.';
  }
  if (normalized.startsWith('-')) return 'Must not start with a hyphen.';
  if (normalized.endsWith('-')) return 'Must not end with a hyphen.';
  if (normalized.includes('--')) return 'Must not contain consecutive hyphens.';
  return undefined;
}

export function validateRegion(value: string): string | undefined {
  if (!value.trim()) return 'This field is required.';
  const valid = ['eu-west', 'eu-central', 'us-east', 'us-west'] as const;
  if (!(valid as readonly string[]).includes(value.trim().toLowerCase())) {
    return 'Invalid region.';
  }
  return undefined;
}

export function validatePlan(value: string): string | undefined {
  if (!value.trim()) return 'This field is required.';
  const valid = ['starter', 'growth', 'enterprise'] as const;
  if (!(valid as readonly string[]).includes(value.trim().toLowerCase())) {
    return 'Invalid plan.';
  }
  return undefined;
}

/** initial_status is optional (defaults to 'draft'). */
export function validateInitialStatus(value: string): string | undefined {
  if (!value) return undefined;
  if (!['draft', 'active'].includes(value)) return 'Invalid status value.';
  return undefined;
}

/** service_start_date is optional; if supplied must be a valid YYYY-MM-DD. */
export function validateServiceStartDate(value: string): string | undefined {
  if (!value) return undefined;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return 'Date must be in YYYY-MM-DD format.';
  }
  const d = new Date(value);
  if (isNaN(d.getTime())) return 'Invalid date.';
  return undefined;
}

/** tenant_notes is optional; if supplied max 5000 chars, no control chars. */
export function validateTenantNotes(value: string): string | undefined {
  if (!value) return undefined;
  if (value.length > 5000) return 'Maximum 5000 characters.';
  if (CONTROL_CHARS.test(value)) {
    return 'Notes contain invalid characters (control characters are not allowed).';
  }
  return undefined;
}

// ---------------------------------------------------------------------------
// Full-form validation
// ---------------------------------------------------------------------------

export interface TenantFormValues {
  tenant_name: string;
  tenant_slug: string;
  region: string;
  plan: string;
  initial_status: string;
  service_start_date: string;
  tenant_notes: string;
}

export type TenantFormErrors = Partial<Record<keyof TenantFormValues, string>>;

export function validateAll(values: TenantFormValues): TenantFormErrors {
  return {
    tenant_name: validateTenantName(values.tenant_name),
    tenant_slug: validateTenantSlug(values.tenant_slug),
    region: validateRegion(values.region),
    plan: validatePlan(values.plan),
    initial_status: validateInitialStatus(values.initial_status),
    service_start_date: validateServiceStartDate(values.service_start_date),
    tenant_notes: validateTenantNotes(values.tenant_notes),
  };
}

/** Returns true when there are no validation errors in the errors object. */
export function hasNoErrors(errors: TenantFormErrors): boolean {
  return Object.values(errors).every((v) => v === undefined);
}

// ---------------------------------------------------------------------------
// Status-reason validator (used on Edit form and StatusChangeModal)
// ---------------------------------------------------------------------------

/**
 * Validates `status_reason` per TDD §6.6.
 *
 * @param value   The raw input string.
 * @param required  True when the target/current status is `suspended` or `archived`.
 */
export function validateStatusReason(
  value: string,
  required: boolean,
): string | undefined {
  const trimmed = value.trim();
  if (required && !trimmed) return 'A reason is required for suspended or archived tenants.';
  if (!trimmed) return undefined; // optional and empty → valid
  if (trimmed.length < 10) return 'Minimum 10 characters.';
  if (trimmed.length > 500) return 'Maximum 500 characters.';
  if (CONTROL_CHARS.test(trimmed)) {
    return 'Reason contains invalid characters (control characters are not allowed).';
  }
  return undefined;
}
