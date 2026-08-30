/**
 * ProvisionTenantForm — Full-page form for provisioning a new tenant.
 *
 * Three sections:
 *   1. Tenant Details (name, slug, region, plan, dates, notes)
 *   2. Admin Account (email, full name)
 *   3. Default Workspace (optional name and slug)
 *
 * On success, shows a result panel with all created resources and the
 * invitation link for the admin user.
 */
import { useState, useCallback, FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { isAxiosError } from 'axios';
import toast from 'react-hot-toast';
import {
  AlertCircle,
  CheckCircle2,
  Copy,
  Loader2,
  Rocket,
  Building2,
  UserPlus,
  LayoutDashboard,
  ChevronLeft,
} from 'lucide-react';

import {
  provisionTenant,
  ProvisionTenantRequest,
  ProvisionTenantResponseData,
  ProvisioningStep,
  ApiErrorBody,
} from '../../../../services/provisioning';
import type { TenantRegion, TenantPlan } from '../../../../services/tenant';
import { generateSlug } from '../../../../utils/slugify';
import {
  ProvisionFormValues,
  ProvisionFormErrors,
  validateProvisionAll,
  hasNoProvisionErrors,
  validateTenantName,
  validateTenantSlug,
  validateRegion,
  validatePlan,
  validateServiceStartDate,
  validateTenantNotes,
  validateAdminEmail,
  validateAdminFullName,
  validateWorkspaceName,
  validateWorkspaceSlug,
} from '../../../../utils/provisioningValidation';
import { REGION_OPTIONS } from '../create/RegionSelect';

// ---------------------------------------------------------------------------
// Plan options (mirrors PlanSelect.tsx)
// ---------------------------------------------------------------------------

const PLAN_OPTIONS = [
  { value: 'starter', label: 'Starter' },
  { value: 'growth', label: 'Growth' },
  { value: 'enterprise', label: 'Enterprise' },
] as const;

// ---------------------------------------------------------------------------
// Field validator lookup
// ---------------------------------------------------------------------------

function validateField(
  field: keyof ProvisionFormValues,
  value: string,
): string | undefined {
  switch (field) {
    case 'tenant_name':       return validateTenantName(value);
    case 'tenant_slug':       return validateTenantSlug(value);
    case 'region':            return validateRegion(value);
    case 'plan':              return validatePlan(value);
    case 'service_start_date': return validateServiceStartDate(value);
    case 'tenant_notes':      return validateTenantNotes(value);
    case 'admin_email':       return validateAdminEmail(value);
    case 'admin_full_name':   return validateAdminFullName(value);
    case 'workspace_name':    return validateWorkspaceName(value);
    case 'workspace_slug':    return validateWorkspaceSlug(value);
  }
}

// ---------------------------------------------------------------------------
// Initial form values
// ---------------------------------------------------------------------------

const INITIAL_VALUES: ProvisionFormValues = {
  tenant_name: '',
  tenant_slug: '',
  region: '',
  plan: '',
  service_start_date: '',
  tenant_notes: '',
  admin_email: '',
  admin_full_name: '',
  workspace_name: '',
  workspace_slug: '',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ProvisionTenantForm() {
  const [values, setValues] = useState<ProvisionFormValues>(INITIAL_VALUES);
  const [errors, setErrors] = useState<ProvisionFormErrors>({});
  const [touched, setTouched] = useState<Partial<Record<keyof ProvisionFormValues, boolean>>>({});
  const [hasSubmitted, setHasSubmitted] = useState(false);
  const [slugUserModified, setSlugUserModified] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [fieldServerErrors, setFieldServerErrors] = useState<ProvisionFormErrors>({});

  // Success state
  const [result, setResult] = useState<ProvisionTenantResponseData | null>(null);
  const [copied, setCopied] = useState(false);

  // Derive display errors
  const displayErrors: ProvisionFormErrors = {};
  for (const key of Object.keys(INITIAL_VALUES) as (keyof ProvisionFormValues)[]) {
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
      setValues((prev: ProvisionFormValues) => {
        const next = { ...prev, tenant_name: value };
        if (!slugUserModified) {
          next.tenant_slug = generateSlug(value);
        }
        return next;
      });
      setFieldServerErrors((prev: ProvisionFormErrors) => ({ ...prev, tenant_name: undefined }));
      if (touched.tenant_name || hasSubmitted) {
        setErrors((prev: ProvisionFormErrors) => ({ ...prev, tenant_name: validateTenantName(value) }));
      }
    },
    [slugUserModified, touched.tenant_name, hasSubmitted],
  );

  const handleSlugChange = useCallback(
    (value: string) => {
      setSlugUserModified(true);
      setValues((prev: ProvisionFormValues) => ({ ...prev, tenant_slug: value }));
      setFieldServerErrors((prev: ProvisionFormErrors) => ({ ...prev, tenant_slug: undefined }));
      if (touched.tenant_slug || hasSubmitted) {
        setErrors((prev: ProvisionFormErrors) => ({ ...prev, tenant_slug: validateTenantSlug(value) }));
      }
    },
    [touched.tenant_slug, hasSubmitted],
  );

  const handleFieldChange = useCallback(
    (field: keyof ProvisionFormValues) => (value: string) => {
      setValues((prev: ProvisionFormValues) => ({ ...prev, [field]: value }));
      setFieldServerErrors((prev: ProvisionFormErrors) => ({ ...prev, [field]: undefined }));
      if (touched[field] || hasSubmitted) {
        setErrors((prev: ProvisionFormErrors) => ({ ...prev, [field]: validateField(field, value) }));
      }
    },
    [touched, hasSubmitted],
  );

  const handleBlur = useCallback(
    (field: keyof ProvisionFormValues) => () => {
      setTouched((prev) => ({ ...prev, [field]: true }));
      setErrors((prev: ProvisionFormErrors) => ({ ...prev, [field]: validateField(field, values[field]) }));
    },
    [values],
  );

  // ---------------------------------------------------------------------------
  // Submit
  // ---------------------------------------------------------------------------

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setHasSubmitted(true);
      setBannerError(null);
      setFieldServerErrors({});

      const allErrors = validateProvisionAll(values);
      setErrors(allErrors);

      if (!hasNoProvisionErrors(allErrors)) {
        const firstErrorField = (
          Object.keys(allErrors) as (keyof ProvisionFormErrors)[]
        ).find((k) => allErrors[k]);
        if (firstErrorField) {
          const el = document.getElementById(
            String(firstErrorField).replace(/_/g, '-'),
          ) as HTMLElement | null;
          el?.focus();
        }
        return;
      }

      setIsSubmitting(true);
      try {
        const body: ProvisionTenantRequest = {
          tenant_name: values.tenant_name.trim(),
          tenant_slug: values.tenant_slug.trim().toLowerCase(),
          region: values.region as TenantRegion,
          plan: values.plan as TenantPlan,
          admin_email: values.admin_email.trim().toLowerCase(),
        };

        if (values.service_start_date) {
          body.service_start_date = values.service_start_date;
        }
        const trimmedNotes = values.tenant_notes.trim();
        if (trimmedNotes) body.tenant_notes = trimmedNotes;

        const trimmedName = values.admin_full_name.trim();
        if (trimmedName) body.admin_full_name = trimmedName;

        const wsName = values.workspace_name.trim();
        if (wsName) body.workspace_name = wsName;

        const wsSlug = values.workspace_slug.trim().toLowerCase();
        if (wsSlug) body.workspace_slug = wsSlug;

        const response = await provisionTenant(body);

        setResult(response.data);
        toast.success('Tenant provisioned successfully!');
      } catch (err) {
        if (isAxiosError(err)) {
          const status = err.response?.status;
          const data = err.response?.data as ApiErrorBody | undefined;

          if (status === 422) {
            const message =
              data?.error?.message ?? 'Validation failed. Please check the fields below.';
            setBannerError(message);

            const serverFieldErrors: ProvisionFormErrors = {};
            for (const fe of data?.error?.fields ?? []) {
              serverFieldErrors[fe.field as keyof ProvisionFormErrors] = fe.reason;
            }
            setFieldServerErrors(serverFieldErrors);
          } else if (status === 403) {
            setBannerError('You do not have permission to provision tenants.');
          } else {
            setBannerError(
              data?.error?.message || 'An unexpected error occurred. Please try again.',
            );
          }
        } else {
          setBannerError('An unexpected error occurred. Please try again.');
        }
      } finally {
        setIsSubmitting(false);
      }
    },
    [values],
  );

  // ---------------------------------------------------------------------------
  // Copy invitation link
  // ---------------------------------------------------------------------------

  const handleCopyInvitation = useCallback(() => {
    if (!result) return;
    const url = `${window.location.origin}${result.invitation.activation_url}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      toast.success('Invitation link copied to clipboard');
      setTimeout(() => setCopied(false), 3000);
    });
  }, [result]);

  // ---------------------------------------------------------------------------
  // Shared input className helper
  // ---------------------------------------------------------------------------

  const inputCls = (field: keyof ProvisionFormValues) =>
    `w-full rounded-lg bg-dark-800/60 border px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 outline-none transition-colors focus:ring-2 focus:ring-primary-500/50 ${
      displayErrors[field]
        ? 'border-red-500/60'
        : 'border-dark-700/60 focus:border-primary-500/50'
    }`;

  const selectCls = inputCls;

  // ---------------------------------------------------------------------------
  // Success view
  // ---------------------------------------------------------------------------

  if (result) {
    return (
      <div data-testid="provision-success" className="space-y-6">
        {/* Success header */}
        <div className="flex items-center gap-3 rounded-xl border border-green-500/30 bg-green-500/10 px-5 py-4">
          <CheckCircle2 className="w-6 h-6 text-green-400 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-green-300">Tenant provisioned successfully</p>
            <p className="text-xs text-green-400/80 mt-0.5">
              All resources have been created and the admin invitation is ready.
            </p>
          </div>
        </div>

        {/* Tenant info */}
        <div className="rounded-2xl border border-dark-700/60 bg-dark-800/60 divide-y divide-dark-700/60">
          <div className="px-6 py-4">
            <div className="flex items-center gap-2 mb-3">
              <Building2 className="w-4 h-4 text-primary-400" />
              <h3 className="text-sm font-semibold text-gray-200">Tenant</h3>
            </div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <dt className="text-gray-500">Name</dt>
              <dd className="text-gray-200">{result.tenant.tenant_name}</dd>
              <dt className="text-gray-500">Slug</dt>
              <dd className="text-gray-200 font-mono">{result.tenant.tenant_slug}</dd>
              <dt className="text-gray-500">Region</dt>
              <dd className="text-gray-200">{result.tenant.region}</dd>
              <dt className="text-gray-500">Plan</dt>
              <dd className="text-gray-200 capitalize">{result.tenant.plan}</dd>
              <dt className="text-gray-500">Status</dt>
              <dd className="text-gray-200 capitalize">{result.tenant.status}</dd>
            </dl>
          </div>

          {/* Workspace info */}
          <div className="px-6 py-4">
            <div className="flex items-center gap-2 mb-3">
              <LayoutDashboard className="w-4 h-4 text-blue-400" />
              <h3 className="text-sm font-semibold text-gray-200">Default Workspace</h3>
            </div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <dt className="text-gray-500">Name</dt>
              <dd className="text-gray-200">{result.workspace.workspace_name}</dd>
              <dt className="text-gray-500">Slug</dt>
              <dd className="text-gray-200 font-mono">{result.workspace.workspace_slug}</dd>
            </dl>
          </div>

          {/* Admin info */}
          <div className="px-6 py-4">
            <div className="flex items-center gap-2 mb-3">
              <UserPlus className="w-4 h-4 text-purple-400" />
              <h3 className="text-sm font-semibold text-gray-200">Admin Account</h3>
            </div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <dt className="text-gray-500">Email</dt>
              <dd className="text-gray-200">{result.admin.email}</dd>
              {result.admin.full_name && (
                <>
                  <dt className="text-gray-500">Name</dt>
                  <dd className="text-gray-200">{result.admin.full_name}</dd>
                </>
              )}
              <dt className="text-gray-500">Status</dt>
              <dd className="text-amber-400 capitalize">{result.admin.status}</dd>
            </dl>
          </div>

          {/* Invitation */}
          <div className="px-6 py-4">
            <div className="flex items-center gap-2 mb-3">
              <Rocket className="w-4 h-4 text-amber-400" />
              <h3 className="text-sm font-semibold text-gray-200">Invitation</h3>
            </div>
            <p className="text-xs text-gray-400 mb-3">
              Share this single-use link with the tenant admin. It expires in{' '}
              <strong className="text-gray-300">{result.invitation.expires_in_hours} hours</strong>.
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 px-3 py-2 text-xs bg-dark-900 rounded-lg border border-dark-700/60 text-amber-300 truncate">
                {window.location.origin}{result.invitation.activation_url}
              </code>
              <button
                onClick={handleCopyInvitation}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border border-dark-600 text-gray-300 hover:text-white hover:bg-dark-700/60 transition-colors"
                data-testid="btn-copy-invitation"
              >
                <Copy className="w-3.5 h-3.5" />
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>

          {/* Provisioning steps */}
          <div className="px-6 py-4">
            <h3 className="text-sm font-semibold text-gray-200 mb-3">Provisioning Steps</h3>
            <div className="space-y-1">
              {result.provisioning_steps.map((step: ProvisioningStep) => (
                <div
                  key={step.step_order}
                  className="flex items-center gap-2 text-xs"
                >
                  <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />
                  <span className="text-gray-400">{step.step_name.replace(/_/g, ' ')}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between">
          <Link
            to="/admin/tenants"
            className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
            All Tenants
          </Link>
          <Link
            to={`/admin/tenants/${result.tenant.tenant_id}`}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-primary-600 hover:bg-primary-500 text-white transition-colors"
          >
            View Tenant Details
          </Link>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Form view
  // ---------------------------------------------------------------------------

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="space-y-8"
      aria-label="Provision tenant form"
      data-testid="provision-tenant-form"
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

      {/* ── Section 1: Tenant Details ──────────────────────────────────── */}
      <fieldset className="space-y-5">
        <legend className="flex items-center gap-2 text-base font-semibold text-white mb-1">
          <Building2 className="w-4 h-4 text-primary-400" />
          Tenant Details
        </legend>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Tenant Name */}
          <div className="md:col-span-2 space-y-1.5">
            <label htmlFor="tenant-name" className="block text-sm font-medium text-gray-300">
              Tenant Name <span className="text-red-400">*</span>
            </label>
            <input
              id="tenant-name"
              type="text"
              value={values.tenant_name}
              onChange={(e) => handleNameChange(e.target.value)}
              onBlur={handleBlur('tenant_name')}
              maxLength={155}
              className={inputCls('tenant_name')}
              placeholder="e.g. Acme Corporation"
              aria-required="true"
              data-testid="field-tenant-name"
            />
            {displayErrors.tenant_name && (
              <p className="text-xs text-red-400" role="alert">{displayErrors.tenant_name}</p>
            )}
          </div>

          {/* Tenant Slug */}
          <div className="md:col-span-2 space-y-1.5">
            <label htmlFor="tenant-slug" className="block text-sm font-medium text-gray-300">
              Tenant Slug <span className="text-red-400">*</span>
            </label>
            <input
              id="tenant-slug"
              type="text"
              value={values.tenant_slug}
              onChange={(e) => handleSlugChange(e.target.value)}
              onBlur={handleBlur('tenant_slug')}
              maxLength={85}
              className={inputCls('tenant_slug')}
              placeholder="e.g. acme-corp"
              aria-required="true"
              data-testid="field-tenant-slug"
            />
            {displayErrors.tenant_slug && (
              <p className="text-xs text-red-400" role="alert">{displayErrors.tenant_slug}</p>
            )}
          </div>

          {/* Region */}
          <div className="space-y-1.5">
            <label htmlFor="region" className="block text-sm font-medium text-gray-300">
              Region <span className="text-red-400">*</span>
            </label>
            <select
              id="region"
              value={values.region}
              onChange={(e) => handleFieldChange('region')(e.target.value)}
              onBlur={handleBlur('region')}
              className={selectCls('region')}
              aria-required="true"
              data-testid="field-region"
            >
              <option value="">Select a region…</option>
              {REGION_OPTIONS.map((opt: { readonly value: string; readonly label: string }) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            {displayErrors.region && (
              <p className="text-xs text-red-400" role="alert">{displayErrors.region}</p>
            )}
          </div>

          {/* Plan */}
          <div className="space-y-1.5">
            <label htmlFor="plan" className="block text-sm font-medium text-gray-300">
              Plan <span className="text-red-400">*</span>
            </label>
            <select
              id="plan"
              value={values.plan}
              onChange={(e) => handleFieldChange('plan')(e.target.value)}
              onBlur={handleBlur('plan')}
              className={selectCls('plan')}
              aria-required="true"
              data-testid="field-plan"
            >
              <option value="">Select a plan…</option>
              {PLAN_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            {displayErrors.plan && (
              <p className="text-xs text-red-400" role="alert">{displayErrors.plan}</p>
            )}
          </div>

          {/* Service Start Date */}
          <div className="space-y-1.5">
            <label htmlFor="service-start-date" className="block text-sm font-medium text-gray-300">
              Service Start Date
            </label>
            <input
              id="service-start-date"
              type="date"
              value={values.service_start_date}
              onChange={(e) => handleFieldChange('service_start_date')(e.target.value)}
              onBlur={handleBlur('service_start_date')}
              className={inputCls('service_start_date')}
              data-testid="field-service-start-date"
            />
            {displayErrors.service_start_date && (
              <p className="text-xs text-red-400" role="alert">{displayErrors.service_start_date}</p>
            )}
          </div>

          {/* Notes */}
          <div className="md:col-span-2 space-y-1.5">
            <label htmlFor="tenant-notes" className="block text-sm font-medium text-gray-300">
              Notes
            </label>
            <textarea
              id="tenant-notes"
              value={values.tenant_notes}
              onChange={(e) => handleFieldChange('tenant_notes')(e.target.value)}
              onBlur={handleBlur('tenant_notes')}
              maxLength={5100}
              rows={3}
              className={inputCls('tenant_notes')}
              placeholder="Internal notes (optional)"
              data-testid="field-tenant-notes"
            />
            {displayErrors.tenant_notes && (
              <p className="text-xs text-red-400" role="alert">{displayErrors.tenant_notes}</p>
            )}
          </div>
        </div>
      </fieldset>

      {/* ── Section 2: Admin Account ──────────────────────────────────── */}
      <fieldset className="space-y-5">
        <legend className="flex items-center gap-2 text-base font-semibold text-white mb-1">
          <UserPlus className="w-4 h-4 text-purple-400" />
          Client Admin Account
        </legend>
        <p className="text-xs text-gray-500 -mt-3">
          The admin will receive an invitation link to set their password and activate their account.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Email */}
          <div className="space-y-1.5">
            <label htmlFor="admin-email" className="block text-sm font-medium text-gray-300">
              Email Address <span className="text-red-400">*</span>
            </label>
            <input
              id="admin-email"
              type="email"
              value={values.admin_email}
              onChange={(e) => handleFieldChange('admin_email')(e.target.value)}
              onBlur={handleBlur('admin_email')}
              maxLength={260}
              className={inputCls('admin_email')}
              placeholder="admin@client.com"
              aria-required="true"
              data-testid="field-admin-email"
            />
            {displayErrors.admin_email && (
              <p className="text-xs text-red-400" role="alert">{displayErrors.admin_email}</p>
            )}
          </div>

          {/* Full Name */}
          <div className="space-y-1.5">
            <label htmlFor="admin-full-name" className="block text-sm font-medium text-gray-300">
              Full Name
            </label>
            <input
              id="admin-full-name"
              type="text"
              value={values.admin_full_name}
              onChange={(e) => handleFieldChange('admin_full_name')(e.target.value)}
              onBlur={handleBlur('admin_full_name')}
              maxLength={260}
              className={inputCls('admin_full_name')}
              placeholder="John Doe (optional)"
              data-testid="field-admin-full-name"
            />
            {displayErrors.admin_full_name && (
              <p className="text-xs text-red-400" role="alert">{displayErrors.admin_full_name}</p>
            )}
          </div>
        </div>
      </fieldset>

      {/* ── Section 3: Default Workspace ──────────────────────────────── */}
      <fieldset className="space-y-5">
        <legend className="flex items-center gap-2 text-base font-semibold text-white mb-1">
          <LayoutDashboard className="w-4 h-4 text-blue-400" />
          Default Workspace
        </legend>
        <p className="text-xs text-gray-500 -mt-3">
          A default workspace is automatically created. Customise it below or leave blank for defaults.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Workspace Name */}
          <div className="space-y-1.5">
            <label htmlFor="workspace-name" className="block text-sm font-medium text-gray-300">
              Workspace Name
            </label>
            <input
              id="workspace-name"
              type="text"
              value={values.workspace_name}
              onChange={(e) => handleFieldChange('workspace_name')(e.target.value)}
              onBlur={handleBlur('workspace_name')}
              maxLength={105}
              className={inputCls('workspace_name')}
              placeholder="Default Workspace"
              data-testid="field-workspace-name"
            />
            {displayErrors.workspace_name && (
              <p className="text-xs text-red-400" role="alert">{displayErrors.workspace_name}</p>
            )}
          </div>

          {/* Workspace Slug */}
          <div className="space-y-1.5">
            <label htmlFor="workspace-slug" className="block text-sm font-medium text-gray-300">
              Workspace Slug
            </label>
            <input
              id="workspace-slug"
              type="text"
              value={values.workspace_slug}
              onChange={(e) => handleFieldChange('workspace_slug')(e.target.value)}
              onBlur={handleBlur('workspace_slug')}
              maxLength={55}
              className={inputCls('workspace_slug')}
              placeholder="default"
              data-testid="field-workspace-slug"
            />
            {displayErrors.workspace_slug && (
              <p className="text-xs text-red-400" role="alert">{displayErrors.workspace_slug}</p>
            )}
          </div>
        </div>
      </fieldset>

      {/* ── Actions ───────────────────────────────────────────────────── */}
      <div className="flex items-center justify-end gap-3 pt-2">
        <Link
          to="/admin/tenants"
          className="px-4 py-2 text-sm font-medium text-gray-400 hover:text-white rounded-lg border border-dark-700/60 bg-dark-800/40 hover:bg-dark-700/60 transition-colors"
          data-testid="btn-cancel"
        >
          Cancel
        </Link>
        <button
          type="submit"
          disabled={isSubmitting}
          className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-lg bg-primary-600 hover:bg-primary-500 text-white disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
          data-testid="btn-provision"
        >
          {isSubmitting ? (
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
          ) : (
            <Rocket className="w-4 h-4" aria-hidden="true" />
          )}
          {isSubmitting ? 'Provisioning…' : 'Provision Tenant'}
        </button>
      </div>
    </form>
  );
}
