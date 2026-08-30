/**
 * EditWorkspaceForm — inline edit form for workspace metadata (F002 P11).
 *
 * Displayed inline on the detail page for workspace_administrator actors.
 *
 * Read-only fields (never sent to the API):
 *   workspace_id, workspace_slug, tenant_id
 *
 * Editable fields:
 *   workspace_name, description, default_timezone
 *
 * Behaviour:
 *   - Pre-fills with current workspace values on mount.
 *   - Submit calls PATCH /workspaces/{id}; only sends changed fields.
 *   - 200 success: success toast + onSuccess() callback (triggers refetch).
 *   - 403: permission-denied banner.
 *   - 409 conflict: stale-data banner; user must refresh.
 *   - 422 field errors: adjacent to each field.
 *   - 422 entity-level: form-level banner.
 *   - Submit disabled while in-flight (no duplicate submissions).
 */
import { useState, useCallback, FormEvent } from 'react';
import { isAxiosError } from 'axios';
import toast from 'react-hot-toast';
import { AlertCircle } from 'lucide-react';

import {
  updateWorkspace,
  UpdateWorkspaceRequest,
  ApiErrorBody,
  WorkspaceDetailWithCounts,
} from '../../../services/workspace';
import {
  WorkspaceFormErrors,
  validateWorkspaceName,
  validateDescription,
  validateDefaultTimezone,
} from '../../../utils/workspaceValidation';

// Common IANA timezone options (mirrored from CreateWorkspaceForm)
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
// Shared class strings
// ---------------------------------------------------------------------------

const inputCls =
  'w-full rounded-lg border border-dark-700 bg-dark-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500';
const inputErrorCls =
  'w-full rounded-lg border border-red-500/50 bg-dark-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-red-500/50 focus:border-red-500';
const readonlyCls =
  'w-full rounded-lg border border-dark-700/50 bg-dark-800/40 px-3 py-2 text-sm text-gray-400 font-mono cursor-not-allowed select-all break-all';
const labelCls = 'block text-sm font-medium text-gray-300 mb-1';

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface EditWorkspaceFormProps {
  workspace: WorkspaceDetailWithCounts;
  /** Called after a successful PATCH — parent should refetch workspace data. */
  onSuccess: () => void;
}

export default function EditWorkspaceForm({ workspace, onSuccess }: EditWorkspaceFormProps) {
  const [name, setName] = useState(workspace.workspace_name);
  const [description, setDescription] = useState(workspace.description ?? '');
  const [timezone, setTimezone] = useState(workspace.default_timezone);

  const [errors, setErrors] = useState<WorkspaceFormErrors>({});
  const [touched, setTouched] = useState<Partial<Record<string, boolean>>>({});
  const [hasSubmitted, setHasSubmitted] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [fieldServerErrors, setFieldServerErrors] = useState<WorkspaceFormErrors>({});

  // Merge client validation + server errors (server takes precedence after submit)
  const displayErrors: WorkspaceFormErrors = {};
  const editableFields = ['workspace_name', 'description', 'default_timezone'] as const;
  for (const key of editableFields) {
    if (touched[key] || hasSubmitted) displayErrors[key] = errors[key];
    if (fieldServerErrors[key]) displayErrors[key] = fieldServerErrors[key];
  }

  // ---------------------------------------------------------------------------
  // Blur handlers
  // ---------------------------------------------------------------------------

  const handleBlur = (field: string, value: string) => {
    setTouched((p) => ({ ...p, [field]: true }));
    if (field === 'workspace_name')
      setErrors((p) => ({ ...p, workspace_name: validateWorkspaceName(value) }));
    if (field === 'description')
      setErrors((p) => ({ ...p, description: validateDescription(value) }));
    if (field === 'default_timezone')
      setErrors((p) => ({ ...p, default_timezone: validateDefaultTimezone(value) }));
  };

  // ---------------------------------------------------------------------------
  // Submit handler
  // ---------------------------------------------------------------------------

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setHasSubmitted(true);
      setBannerError(null);
      setFieldServerErrors({});

      const nameErr = validateWorkspaceName(name);
      const descErr = validateDescription(description);
      const tzErr = validateDefaultTimezone(timezone);
      setErrors({ workspace_name: nameErr, description: descErr, default_timezone: tzErr });
      if (nameErr || descErr || tzErr) return;

      // Build diff — only send changed fields
      const body: UpdateWorkspaceRequest = {};
      if (name !== workspace.workspace_name) body.workspace_name = name;
      if (description !== (workspace.description ?? '')) {
        body.description = description || null;
      }
      if (timezone !== workspace.default_timezone) body.default_timezone = timezone;

      // No-op: nothing changed
      if (!Object.keys(body).length) {
        toast.success('No changes to save.');
        return;
      }

      setIsSubmitting(true);
      try {
        await updateWorkspace(workspace.workspace_id, body);
        toast.success('Workspace updated successfully.');
        onSuccess();
      } catch (err) {
        if (isAxiosError(err)) {
          const status = err.response?.status;
          const errBody = err.response?.data as ApiErrorBody | undefined;
          if (status === 403) {
            setBannerError('You do not have permission to edit this workspace.');
          } else if (status === 409) {
            setBannerError(
              'This workspace was modified by someone else. Please refresh and try again.',
            );
          } else if (status === 422 && errBody?.error?.fields?.length) {
            const map: WorkspaceFormErrors = {};
            for (const f of errBody.error.fields) {
              if (f.field === 'workspace_name') map.workspace_name = f.reason;
              else if (f.field === 'description') map.description = f.reason;
              else if (f.field === 'default_timezone') map.default_timezone = f.reason;
            }
            setFieldServerErrors(map);
          } else if (status === 422 && errBody?.error) {
            setBannerError(errBody.error.message || 'Validation failed.');
          } else {
            setBannerError('An unexpected error occurred. Please try again.');
          }
        } else {
          setBannerError('Network error. Please check your connection and try again.');
        }
      } finally {
        setIsSubmitting(false);
      }
    },
    [name, description, timezone, workspace, onSuccess],
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div
      className="rounded-2xl border border-dark-800/60 bg-dark-900/60 p-6 backdrop-blur-sm"
      data-testid="edit-workspace-form"
    >
      <h3 className="text-base font-semibold text-white mb-4">Edit Workspace</h3>

      {bannerError && (
        <div
          role="alert"
          className="mb-4 flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400 text-sm"
          data-testid="edit-workspace-banner-error"
        >
          <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />
          <span>{bannerError}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate>
        {/* ── Read-only identity fields ──────────────────────────────────── */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 mb-5">
          <div>
            <span className={labelCls}>Workspace ID</span>
            <div className={readonlyCls} data-testid="edit-workspace-id-readonly">
              {workspace.workspace_id}
            </div>
          </div>
          <div>
            <span className={labelCls}>Slug</span>
            <div className={readonlyCls} data-testid="edit-workspace-slug-readonly">
              {workspace.workspace_slug}
            </div>
          </div>
          <div>
            <span className={labelCls}>Tenant ID</span>
            <div className={readonlyCls} data-testid="edit-workspace-tenant-id-readonly">
              {workspace.tenant_id}
            </div>
          </div>
        </div>

        {/* ── Editable fields ───────────────────────────────────────────── */}
        <div className="space-y-4">
          {/* Workspace Name */}
          <div>
            <label htmlFor="edit-ws-name" className={labelCls}>
              Workspace Name <span className="text-red-400">*</span>
            </label>
            <input
              id="edit-ws-name"
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setFieldServerErrors((p) => ({ ...p, workspace_name: undefined }));
                if (touched.workspace_name || hasSubmitted) {
                  setErrors((p) => ({
                    ...p,
                    workspace_name: validateWorkspaceName(e.target.value),
                  }));
                }
              }}
              onBlur={() => handleBlur('workspace_name', name)}
              className={displayErrors.workspace_name ? inputErrorCls : inputCls}
              data-testid="edit-workspace-name-input"
              aria-describedby={displayErrors.workspace_name ? 'edit-ws-name-err' : undefined}
            />
            {displayErrors.workspace_name && (
              <p
                id="edit-ws-name-err"
                role="alert"
                className="mt-1 text-xs text-red-400"
                data-testid="edit-workspace-name-error"
              >
                {displayErrors.workspace_name}
              </p>
            )}
          </div>

          {/* Description */}
          <div>
            <label htmlFor="edit-ws-desc" className={labelCls}>
              Description
            </label>
            <textarea
              id="edit-ws-desc"
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
                setFieldServerErrors((p) => ({ ...p, description: undefined }));
                if (touched.description || hasSubmitted) {
                  setErrors((p) => ({
                    ...p,
                    description: validateDescription(e.target.value),
                  }));
                }
              }}
              onBlur={() => handleBlur('description', description)}
              rows={3}
              className={displayErrors.description ? inputErrorCls : inputCls}
              data-testid="edit-workspace-description-input"
            />
            {displayErrors.description && (
              <p role="alert" className="mt-1 text-xs text-red-400">
                {displayErrors.description}
              </p>
            )}
          </div>

          {/* Default Timezone */}
          <div>
            <label htmlFor="edit-ws-tz" className={labelCls}>
              Default Timezone
            </label>
            <select
              id="edit-ws-tz"
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              className={inputCls}
              data-testid="edit-workspace-timezone-select"
            >
              {TIMEZONE_OPTIONS.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>

          {/* Submit */}
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              data-testid="edit-workspace-submit-btn"
            >
              {isSubmitting ? 'Saving…' : 'Save Changes'}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
