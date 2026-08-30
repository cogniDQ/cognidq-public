/**
 * EditTenantForm — the main form component for editing mutable tenant fields.
 *
 * Behaviour (TDD §5.4, Packet 13):
 * - Pre-populated from `initialData` (the currently saved tenant record).
 * - Validation fires on field blur; server errors shown after submit.
 * - Change-set detection: only fields whose value differs from `initialData`
 *   are included in the PATCH request body (AC-13.2).
 * - On 200: navigate to detail, invalidate cache, show success toast.
 * - On 409: conflict banner, stay on page, changes intact (AC-13.3).
 * - On 422 `archived_tenant`: banner then navigate back to detail.
 * - On other 422: banner + inline field errors.
 *
 * Read-only fields (AC-13.1): tenant_id, tenant_slug, region
 * Editable fields: tenant_name, plan, status_reason, service_start_date, tenant_notes
 */
import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import toast from 'react-hot-toast';
import { AlertCircle } from 'lucide-react';

import {
  TenantDetailRecord,
  UpdateTenantRequest,
  updateTenantMetadata,
} from '../../../../services/tenant';

import {
  validateTenantName,
  validatePlan,
  validateStatusReason,
  validateServiceStartDate,
  validateTenantNotes,
} from '../../../../utils/tenantValidation';

import TenantNameField from '../create/TenantNameField';
import PlanSelect from '../create/PlanSelect';
import ServiceStartDatePicker from '../create/ServiceStartDatePicker';
import TenantNotesTextarea from '../create/TenantNotesTextarea';
import TenantSlugReadOnly from './TenantSlugReadOnly';
import RegionReadOnly from './RegionReadOnly';
import TenantIdReadOnly from './TenantIdReadOnly';
import StatusReasonField from './StatusReasonField';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface EditFormValues {
  tenant_name: string;
  plan: string;
  status_reason: string;
  service_start_date: string;
  tenant_notes: string;
}

interface EditFormErrors {
  tenant_name?: string;
  plan?: string;
  status_reason?: string;
  service_start_date?: string;
  tenant_notes?: string;
}

interface Props {
  initialData: TenantDetailRecord;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** True when the current status means status_reason is required. */
function isReasonRequired(status: string): boolean {
  return status === 'suspended' || status === 'archived';
}

/** Convert `null` from API to empty string for controlled inputs. */
function nullToEmpty(v: string | null | undefined): string {
  return v ?? '';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function EditTenantForm({ initialData }: Props) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const reasonRequired = isReasonRequired(initialData.status);

  // Snapshot of server values — used for change-set detection
  const initial: EditFormValues = {
    tenant_name: initialData.tenant_name,
    plan: initialData.plan,
    status_reason: nullToEmpty(initialData.status_reason),
    service_start_date: nullToEmpty(initialData.service_start_date),
    tenant_notes: nullToEmpty(initialData.tenant_notes),
  };

  const [values, setValues] = useState<EditFormValues>(initial);
  const [errors, setErrors] = useState<EditFormErrors>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // ── Field update helpers ─────────────────────────────────────────────────

  const setField = useCallback(
    <K extends keyof EditFormValues>(key: K, value: EditFormValues[K]) => {
      setValues((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  // ── Blur validators ──────────────────────────────────────────────────────

  const blurField = useCallback(
    (key: keyof EditFormErrors, errorMsg: string | undefined) => {
      setErrors((prev) => ({ ...prev, [key]: errorMsg }));
    },
    [],
  );

  // ── Change-set detection ─────────────────────────────────────────────────

  function buildChangeset(): UpdateTenantRequest | null {
    const patch: UpdateTenantRequest = {};

    if (values.tenant_name.trim() !== initial.tenant_name.trim()) {
      patch.tenant_name = values.tenant_name.trim();
    }

    if (values.plan !== initial.plan) {
      patch.plan = values.plan as UpdateTenantRequest['plan'];
    }

    // status_reason: treat empty string as null (clear intent)
    const newReason = values.status_reason.trim() || null;
    const oldReason = initial.status_reason.trim() || null;
    if (newReason !== oldReason) {
      patch.status_reason = newReason;
    }

    // service_start_date: treat empty string as null (clear intent)
    const newDate = values.service_start_date || null;
    const oldDate = initial.service_start_date || null;
    if (newDate !== oldDate) {
      patch.service_start_date = newDate;
    }

    // tenant_notes: treat empty string as null (clear intent)
    const newNotes = values.tenant_notes.trim() || null;
    const oldNotes = initial.tenant_notes.trim() || null;
    if (newNotes !== oldNotes) {
      patch.tenant_notes = newNotes;
    }

    return Object.keys(patch).length > 0 ? patch : null;
  }

  // ── Submit ───────────────────────────────────────────────────────────────

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBanner(null);

    // Client-side full validation before submit
    const newErrors: EditFormErrors = {
      tenant_name: validateTenantName(values.tenant_name),
      plan: validatePlan(values.plan),
      status_reason: validateStatusReason(values.status_reason, reasonRequired),
      service_start_date: validateServiceStartDate(values.service_start_date),
      tenant_notes: validateTenantNotes(values.tenant_notes),
    };

    const hasErrors = Object.values(newErrors).some((e) => e !== undefined);
    if (hasErrors) {
      setErrors(newErrors);
      return;
    }

    const patch = buildChangeset();
    if (!patch) {
      setBanner('No changes detected. Update at least one field before saving.');
      return;
    }

    setIsSaving(true);
    try {
      await updateTenantMetadata(initialData.tenant_id, patch);
      queryClient.invalidateQueries({ queryKey: ['tenant', initialData.tenant_id] });
      toast.success('Tenant updated successfully.');
      navigate(`/admin/tenants/${initialData.tenant_id}`);
    } catch (err) {
      if (isAxiosError(err)) {
        const status = err.response?.status;
        const body = err.response?.data as {
          error?: { code?: string; message?: string; fields?: { field: string; reason: string }[] };
        } | undefined;
        const code = body?.error?.code ?? '';
        const message = body?.error?.message ?? 'An unexpected error occurred.';

        if (status === 409) {
          // AC-13.3: stay on page, changes intact
          setBanner(
            'A conflict occurred — another update may have been made. Please review your changes and try again.',
          );
        } else if (status === 422 && code === 'archived_tenant') {
          setBanner('This tenant has been archived and can no longer be edited.');
          setTimeout(() => navigate(`/admin/tenants/${initialData.tenant_id}`), 1500);
        } else if (status === 422) {
          // Map server field errors back to our inline error state
          const serverErrors: EditFormErrors = {};
          for (const fe of body?.error?.fields ?? []) {
            if (fe.field in newErrors) {
              (serverErrors as Record<string, string>)[fe.field] = fe.reason;
            }
          }
          if (Object.keys(serverErrors).length > 0) {
            setErrors((prev) => ({ ...prev, ...serverErrors }));
          }
          setBanner(message);
        } else {
          setBanner(message);
        }
      } else {
        setBanner('An unexpected error occurred. Please try again.');
      }
    } finally {
      setIsSaving(false);
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <form onSubmit={handleSubmit} noValidate data-testid="edit-tenant-form">
      {/* Error / info banner */}
      {banner && (
        <div
          className="mb-5 rounded-xl border border-red-500/30 bg-red-500/10 p-4 flex gap-3"
          role="alert"
          data-testid="edit-form-banner"
        >
          <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
          <p className="text-sm text-red-300">{banner}</p>
        </div>
      )}

      <div className="space-y-5">
        {/* Read-only fields (AC-13.1) */}
        <TenantIdReadOnly value={initialData.tenant_id} />
        <TenantSlugReadOnly value={initialData.tenant_slug} />
        <RegionReadOnly value={initialData.region} />

        {/* Editable fields */}
        <TenantNameField
          value={values.tenant_name}
          onChange={(v) => setField('tenant_name', v)}
          onBlur={() => blurField('tenant_name', validateTenantName(values.tenant_name))}
          error={errors.tenant_name}
        />

        <PlanSelect
          value={values.plan}
          onChange={(v) => setField('plan', v)}
          onBlur={() => blurField('plan', validatePlan(values.plan))}
          error={errors.plan}
        />

        <StatusReasonField
          value={values.status_reason}
          onChange={(v) => setField('status_reason', v)}
          onBlur={() =>
            blurField('status_reason', validateStatusReason(values.status_reason, reasonRequired))
          }
          error={errors.status_reason}
          required={reasonRequired}
        />

        <ServiceStartDatePicker
          value={values.service_start_date}
          onChange={(v) => setField('service_start_date', v)}
          onBlur={() =>
            blurField('service_start_date', validateServiceStartDate(values.service_start_date))
          }
          error={errors.service_start_date}
        />

        <TenantNotesTextarea
          value={values.tenant_notes}
          onChange={(v) => setField('tenant_notes', v)}
          onBlur={() => blurField('tenant_notes', validateTenantNotes(values.tenant_notes))}
          error={errors.tenant_notes}
        />
      </div>

      {/* Form actions */}
      <div className="flex items-center justify-end gap-3 mt-8 pt-5 border-t border-dark-700/60">
        <button
          type="button"
          onClick={() => navigate(`/admin/tenants/${initialData.tenant_id}`)}
          className="px-4 py-2 rounded-lg text-sm font-medium text-gray-300 bg-dark-700/60 border border-dark-600/60 hover:bg-dark-600/60 hover:text-white transition-colors"
          data-testid="btn-cancel-edit"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={isSaving}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          data-testid="btn-save-edit"
        >
          {isSaving ? 'Saving…' : 'Save Changes'}
        </button>
      </div>
    </form>
  );
}
