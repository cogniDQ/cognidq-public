/**
 * CreateWorkspaceForm — full form for creating a workspace (F002 P10).
 *
 * Behaviour:
 *   - Slug auto-populates from workspace_name (lowercase, spaces→hyphens,
 *     strip invalid chars, collapse hyphens).
 *   - Once user manually edits slug field, auto-population stops permanently.
 *   - EC-6: if workspace_name produces only invalid chars (e.g. "!!!"),
 *     slug is left empty and an inline error is shown before submission.
 *   - Slug immutability notice is always visible.
 *   - Submit disabled while request is in-flight (no duplicate submissions).
 *   - 201 success: navigate to /workspaces, show success toast.
 *   - 401: interceptor redirects to login.
 *   - 403: permission-denied banner.
 *   - 422 field errors: displayed adjacent to fields.
 *   - 422 entity-level errors: form-level banner.
 *   - 500 / network: generic retry banner.
 */
import { useState, useCallback, FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { isAxiosError } from 'axios';
import toast from 'react-hot-toast';
import { AlertCircle } from 'lucide-react';

import {
  createWorkspace,
  ApiErrorBody,
} from '../../../services/workspace';
import { generateSlug } from '../../../utils/slugify';
import { getActorRole, getTenantId } from '../../../utils/jwt';
import {
  WorkspaceFormValues,
  WorkspaceFormErrors,
  validateWorkspaceName,
  validateWorkspaceSlug,
  validateDescription,
  validateDefaultTimezone,
  validateAll,
  hasNoErrors,
} from '../../../utils/workspaceValidation';
import SlugInputField from '../SlugInputField';

// ---------------------------------------------------------------------------
// Common IANA timezones for the default_timezone select
// ---------------------------------------------------------------------------
const TIMEZONE_OPTIONS = [
  'UTC',
  'Africa/Cairo',
  'Africa/Johannesburg',
  'Africa/Lagos',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/New_York',
  'America/Sao_Paulo',
  'Asia/Colombo',
  'Asia/Dubai',
  'Asia/Ho_Chi_Minh',
  'Asia/Hong_Kong',
  'Asia/Jakarta',
  'Asia/Karachi',
  'Asia/Kolkata',
  'Asia/Manila',
  'Asia/Riyadh',
  'Asia/Seoul',
  'Asia/Shanghai',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Melbourne',
  'Australia/Sydney',
  'Europe/Amsterdam',
  'Europe/Berlin',
  'Europe/Istanbul',
  'Europe/London',
  'Europe/Madrid',
  'Europe/Moscow',
  'Europe/Paris',
  'Europe/Warsaw',
  'Pacific/Auckland',
];

// ---------------------------------------------------------------------------
// Initial values
// ---------------------------------------------------------------------------

const INITIAL_VALUES: WorkspaceFormValues = {
  workspace_name: '',
  workspace_slug: '',
  description: '',
  default_timezone: 'UTC',
};

// ---------------------------------------------------------------------------
// Single-field re-validator (called on blur and after submit attempt)
// ---------------------------------------------------------------------------

function validateField(
  field: keyof WorkspaceFormValues,
  value: string,
): string | undefined {
  switch (field) {
    case 'workspace_name':  return validateWorkspaceName(value);
    case 'workspace_slug':  return validateWorkspaceSlug(value);
    case 'description':     return validateDescription(value);
    case 'default_timezone': return validateDefaultTimezone(value);
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CreateWorkspaceForm() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Resolve target tenant: URL ?tenant_id=... overrides the JWT claim. The
  // backend accepts an explicit tenant_id only for platform_admin callers; it
  // is harmless for other roles because they always have a tenant_id in JWT.
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const actorRole = getActorRole(token);
  const jwtTenantId = getTenantId(token);
  const queryTenantId = searchParams.get('tenant_id');
  const targetTenantId = queryTenantId || jwtTenantId;
  const needsTenantSelection = actorRole === 'platform_admin' && !targetTenantId;

  const [values, setValues] = useState<WorkspaceFormValues>(INITIAL_VALUES);
  const [errors, setErrors] = useState<WorkspaceFormErrors>({});
  const [touched, setTouched] = useState<
    Partial<Record<keyof WorkspaceFormValues, boolean>>
  >({});
  const [hasSubmitted, setHasSubmitted] = useState(false);
  const [slugUserModified, setSlugUserModified] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [fieldServerErrors, setFieldServerErrors] = useState<WorkspaceFormErrors>({});

  // Derived display errors: client errors (for touched/submitted fields)
  // merged with server-returned field errors (server takes precedence).
  const displayErrors: WorkspaceFormErrors = {};
  for (const key of Object.keys(INITIAL_VALUES) as (keyof WorkspaceFormValues)[]) {
    if (touched[key] || hasSubmitted) {
      displayErrors[key] = errors[key];
    }
    if (fieldServerErrors[key]) {
      displayErrors[key] = fieldServerErrors[key];
    }
  }

  // ---------------------------------------------------------------------------
  // Change handlers
  // ---------------------------------------------------------------------------

  const handleNameChange = useCallback(
    (value: string) => {
      setValues((prev) => {
        const next: WorkspaceFormValues = { ...prev, workspace_name: value };
        if (!slugUserModified) {
          next.workspace_slug = generateSlug(value);
        }
        return next;
      });
      setFieldServerErrors((prev) => ({ ...prev, workspace_name: undefined }));
      if (touched.workspace_name || hasSubmitted) {
        setErrors((prev) => ({ ...prev, workspace_name: validateWorkspaceName(value) }));
      }
    },
    [slugUserModified, touched.workspace_name, hasSubmitted],
  );

  const handleSlugChange = useCallback(
    (value: string) => {
      setSlugUserModified(true);
      setValues((prev) => ({ ...prev, workspace_slug: value }));
      setFieldServerErrors((prev) => ({ ...prev, workspace_slug: undefined }));
      if (touched.workspace_slug || hasSubmitted) {
        setErrors((prev) => ({ ...prev, workspace_slug: validateWorkspaceSlug(value) }));
      }
    },
    [touched.workspace_slug, hasSubmitted],
  );

  const handleFieldChange = useCallback(
    (field: keyof WorkspaceFormValues) => (value: string) => {
      setValues((prev) => ({ ...prev, [field]: value }));
      setFieldServerErrors((prev) => ({ ...prev, [field]: undefined }));
      if (touched[field] || hasSubmitted) {
        setErrors((prev) => ({ ...prev, [field]: validateField(field, value) }));
      }
    },
    [touched, hasSubmitted],
  );

  // ---------------------------------------------------------------------------
  // Blur handlers — run validation and mark field as touched
  // ---------------------------------------------------------------------------

  const handleBlur = useCallback(
    (field: keyof WorkspaceFormValues) => () => {
      setTouched((prev) => ({ ...prev, [field]: true }));
      setErrors((prev) => ({ ...prev, [field]: validateField(field, values[field]) }));
    },
    [values],
  );

  // ---------------------------------------------------------------------------
  // Submit handler
  // ---------------------------------------------------------------------------

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setHasSubmitted(true);
      setBannerError(null);
      setFieldServerErrors({});

      const allErrors = validateAll(values);
      setErrors(allErrors);

      if (!hasNoErrors(allErrors)) {
        const firstErrorField = (
          Object.keys(allErrors) as (keyof WorkspaceFormErrors)[]
        ).find((k) => allErrors[k]);
        if (firstErrorField) {
          const el = document.getElementById(
            firstErrorField.replace(/_/g, '-'),
          ) as HTMLElement | null;
          el?.focus();
        }
        return;
      }

      setIsSubmitting(true);
      try {
        const body: Parameters<typeof createWorkspace>[0] = {
          workspace_name: values.workspace_name.trim(),
          workspace_slug: values.workspace_slug.trim().toLowerCase(),
          description: values.description.trim() || undefined,
          default_timezone: values.default_timezone || 'UTC',
        };
        // Platform admins must supply tenant_id explicitly because their JWT
        // has no tenant claim. Tenant admins / members rely on the JWT claim.
        if (queryTenantId) {
          body.tenant_id = queryTenantId;
        }

        await createWorkspace(body);

        toast.success('Workspace created successfully.');
        navigate('/workspaces');
      } catch (err) {
        if (isAxiosError(err)) {
          const status = err.response?.status;
          const data = err.response?.data as ApiErrorBody | undefined;

          if (status === 422) {
            const msg =
              data?.error?.message ?? 'Validation failed. Please check the fields below.';
            // If there are field-specific errors, show banner too
            setBannerError(msg);

            const serverFieldErrors: WorkspaceFormErrors = {};
            for (const fe of data?.error?.fields ?? []) {
              serverFieldErrors[fe.field as keyof WorkspaceFormErrors] = fe.reason;
            }
            // If all errors are field-level, the banner is redundant — but
            // entity-level errors (no fields array) are shown only as banner.
            if ((data?.error?.fields ?? []).length > 0) {
              setBannerError(null);
            }
            setFieldServerErrors(serverFieldErrors);
          } else if (status === 403) {
            setBannerError(
              'You do not have permission to create workspaces.',
            );
          } else {
            setBannerError('An unexpected error occurred. Please try again.');
          }
        } else {
          setBannerError('An unexpected error occurred. Please try again.');
        }
      } finally {
        setIsSubmitting(false);
      }
    },
    [values, navigate, queryTenantId],
  );

  // Platform admin without a tenant context cannot create a workspace.
  if (needsTenantSelection) {
    return (
      <div
        role="alert"
        className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-amber-300"
        data-testid="missing-tenant-banner"
      >
        <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" aria-hidden="true" />
        <div className="text-sm space-y-1">
          <p>Pick a target tenant first.</p>
          <p className="text-amber-200/80">
            Open a tenant from the{' '}
            <a href="/admin/tenants" className="underline hover:text-amber-100">Tenants</a>{' '}
            page and use its &ldquo;Create Workspace&rdquo; action.
          </p>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="space-y-6"
      aria-label="Create workspace form"
      data-testid="create-workspace-form"
    >
      {/* Global error banner */}
      {bannerError && (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400"
          data-testid="form-banner-error"
        >
          <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" aria-hidden="true" />
          <span className="text-sm">{bannerError}</span>
        </div>
      )}

      {/* Workspace Name */}
      <div className="space-y-1.5">
        <label
          htmlFor="workspace-name"
          className="block text-sm font-medium text-gray-300"
        >
          Workspace Name <span className="text-red-400" aria-hidden="true">*</span>
        </label>
        <input
          id="workspace-name"
          type="text"
          value={values.workspace_name}
          onChange={(e) => handleNameChange(e.target.value)}
          onBlur={handleBlur('workspace_name')}
          maxLength={155}
          className={`w-full rounded-lg bg-dark-800/60 border px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 outline-none transition-colors focus:ring-2 focus:ring-primary-500/50 ${
            displayErrors.workspace_name
              ? 'border-red-500/60'
              : 'border-dark-700/60 focus:border-primary-500/50'
          }`}
          placeholder="e.g. Analytics Team"
          aria-required="true"
          aria-describedby={
            displayErrors.workspace_name ? 'workspace-name-error' : undefined
          }
          data-testid="field-workspace-name"
        />
        {displayErrors.workspace_name && (
          <p
            id="workspace-name-error"
            className="text-xs text-red-400"
            role="alert"
            data-testid="error-workspace-name"
          >
            {displayErrors.workspace_name}
          </p>
        )}
      </div>

      {/* Slug */}
      <SlugInputField
        value={values.workspace_slug}
        onChange={handleSlugChange}
        onBlur={handleBlur('workspace_slug')}
        error={displayErrors.workspace_slug}
        isAutoPopulated={!slugUserModified}
      />

      {/* Description */}
      <div className="space-y-1.5">
        <label
          htmlFor="workspace-description"
          className="block text-sm font-medium text-gray-300"
        >
          Description{' '}
          <span className="text-gray-500 font-normal text-xs">(optional)</span>
        </label>
        <textarea
          id="workspace-description"
          value={values.description}
          onChange={(e) => handleFieldChange('description')(e.target.value)}
          onBlur={handleBlur('description')}
          rows={3}
          maxLength={510}
          className={`w-full rounded-lg bg-dark-800/60 border px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 outline-none transition-colors focus:ring-2 focus:ring-primary-500/50 resize-none ${
            displayErrors.description
              ? 'border-red-500/60'
              : 'border-dark-700/60 focus:border-primary-500/50'
          }`}
          placeholder="Optional description of this workspace's purpose."
          aria-describedby={
            displayErrors.description ? 'workspace-description-error' : undefined
          }
          data-testid="field-workspace-description"
        />
        {displayErrors.description && (
          <p
            id="workspace-description-error"
            className="text-xs text-red-400"
            role="alert"
            data-testid="error-workspace-description"
          >
            {displayErrors.description}
          </p>
        )}
      </div>

      {/* Default Timezone */}
      <div className="space-y-1.5">
        <label
          htmlFor="workspace-default-timezone"
          className="block text-sm font-medium text-gray-300"
        >
          Default Timezone
        </label>
        <select
          id="workspace-default-timezone"
          value={values.default_timezone}
          onChange={(e) => handleFieldChange('default_timezone')(e.target.value)}
          onBlur={handleBlur('default_timezone')}
          className={`w-full rounded-lg bg-dark-800/60 border px-3 py-2.5 text-sm text-gray-100 outline-none transition-colors focus:ring-2 focus:ring-primary-500/50 ${
            displayErrors.default_timezone
              ? 'border-red-500/60'
              : 'border-dark-700/60 focus:border-primary-500/50'
          }`}
          aria-describedby={
            displayErrors.default_timezone
              ? 'workspace-default-timezone-error'
              : undefined
          }
          data-testid="field-workspace-timezone"
        >
          {TIMEZONE_OPTIONS.map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </select>
        {displayErrors.default_timezone && (
          <p
            id="workspace-default-timezone-error"
            className="text-xs text-red-400"
            role="alert"
            data-testid="error-workspace-timezone"
          >
            {displayErrors.default_timezone}
          </p>
        )}
      </div>

      {/* Form actions */}
      <div className="flex items-center justify-end gap-3 pt-2">
        <button
          type="button"
          onClick={() => navigate('/workspaces')}
          className="px-4 py-2.5 rounded-lg text-sm font-medium text-gray-300 hover:text-white bg-dark-800/60 border border-dark-700/60 hover:border-dark-600 transition-colors"
          disabled={isSubmitting}
          data-testid="btn-cancel"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={isSubmitting}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary-600 hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
          aria-busy={isSubmitting}
          data-testid="btn-save"
        >
          {isSubmitting ? (
            <>
              <span
                className="w-4 h-4 rounded-full border-2 border-white/40 border-t-white animate-spin"
                aria-hidden="true"
              />
              Creating…
            </>
          ) : (
            'Create Workspace'
          )}
        </button>
      </div>
    </form>
  );
}
