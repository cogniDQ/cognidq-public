/**
 * Client-side validation for the Create Workspace form (F002 P10).
 *
 * Rules mirror the backend TDD §5.3:
 * - workspace_name: required, 2–150 code points after trim
 * - workspace_slug: required, 3–80 chars, [a-z0-9-] only, no leading/trailing/
 *   consecutive hyphens
 * - description: optional, max 500 code points
 * - default_timezone: optional; if provided must be non-empty string
 *
 * Note: IANA canonical validation is server-side only; client validates
 * that the field is non-empty when filled.
 */

export interface WorkspaceFormValues {
  workspace_name: string;
  workspace_slug: string;
  description: string;
  default_timezone: string;
}

export type WorkspaceFormErrors = Partial<Record<keyof WorkspaceFormValues, string>>;

// ---------------------------------------------------------------------------
// Individual field validators
// ---------------------------------------------------------------------------

export function validateWorkspaceName(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) return 'Workspace name is required.';
  if ([...trimmed].length < 2) return 'Workspace name must be at least 2 characters.';
  if ([...trimmed].length > 150) return 'Workspace name must be 150 characters or fewer.';
  return undefined;
}

/** Slug character regex: only lowercase letters, digits, hyphens */
const SLUG_CHAR_RE = /^[a-z0-9-]+$/;

export function validateWorkspaceSlug(value: string): string | undefined {
  if (!value) return 'Workspace slug is required.';
  if (value.length < 3) return 'Slug must be at least 3 characters.';
  if (value.length > 80) return 'Slug must be 80 characters or fewer.';
  if (!SLUG_CHAR_RE.test(value)) return 'Slug may only contain lowercase letters, digits, and hyphens.';
  if (value.startsWith('-') || value.endsWith('-'))
    return 'Slug must not start or end with a hyphen.';
  if (/--/.test(value)) return 'Slug must not contain consecutive hyphens.';
  return undefined;
}

export function validateDescription(value: string): string | undefined {
  if ([...value].length > 500) return 'Description must be 500 characters or fewer.';
  return undefined;
}

export function validateDefaultTimezone(value: string): string | undefined {
  // Client-side: just ensure it is non-empty if the user has set it.
  // The backend performs full IANA canonical validation.
  if (value && value.trim() === '') return 'Timezone cannot be blank.';
  return undefined;
}

// ---------------------------------------------------------------------------
// Full-form validator — accumulates all errors in one pass
// ---------------------------------------------------------------------------

export function validateAll(values: WorkspaceFormValues): WorkspaceFormErrors {
  return {
    workspace_name: validateWorkspaceName(values.workspace_name),
    workspace_slug: validateWorkspaceSlug(values.workspace_slug),
    description: validateDescription(values.description),
    default_timezone: validateDefaultTimezone(values.default_timezone),
  };
}

export function hasNoErrors(errors: WorkspaceFormErrors): boolean {
  return Object.values(errors).every((v) => !v);
}

// ---------------------------------------------------------------------------
// Per-keystroke slug inline warnings (not form-submit errors)
// ---------------------------------------------------------------------------

/** Invalid char detector: warns if slug contains characters outside [a-z0-9-]. */
export function detectSlugInvalidChars(value: string): boolean {
  return value.length > 0 && !SLUG_CHAR_RE.test(value);
}
