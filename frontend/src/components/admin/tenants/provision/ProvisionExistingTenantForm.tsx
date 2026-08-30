/**
 * ProvisionExistingTenantForm — provision the default workspace and admin
 * account against an already-created tenant.
 *
 * Tenant identity (name/slug/region/plan) is read-only and pulled from the
 * existing tenant record. The form only collects:
 *   • admin email + full name (required / optional)
 *   • workspace name + slug (optional — defaults from tenant name/slug)
 *
 * On success, displays the invitation activation link with a copy button.
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
  ChevronLeft,
  Building2,
  UserPlus,
  LayoutDashboard,
} from 'lucide-react';

import {
  provisionExistingTenant,
  ProvisionExistingTenantRequest,
  ProvisionTenantResponseData,
  ProvisioningStep,
  ApiErrorBody,
} from '../../../../services/provisioning';
import type { TenantDetailRecord } from '../../../../services/tenant';
import {
  validateAdminEmail,
  validateAdminFullName,
  validateWorkspaceName,
  validateWorkspaceSlug,
} from '../../../../utils/provisioningValidation';

interface FormValues {
  admin_email: string;
  admin_full_name: string;
  workspace_name: string;
  workspace_slug: string;
}

type FormErrors = Partial<Record<keyof FormValues, string>>;

const INITIAL: FormValues = {
  admin_email: '',
  admin_full_name: '',
  workspace_name: '',
  workspace_slug: '',
};

interface Props {
  tenant: TenantDetailRecord;
}

export default function ProvisionExistingTenantForm({ tenant }: Props) {
  const [values, setValues] = useState<FormValues>(INITIAL);
  const [errors, setErrors] = useState<FormErrors>({});
  const [touched, setTouched] = useState<Partial<Record<keyof FormValues, boolean>>>({});
  const [hasSubmitted, setHasSubmitted] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [fieldServerErrors, setFieldServerErrors] = useState<FormErrors>({});

  const [result, setResult] = useState<ProvisionTenantResponseData | null>(null);
  const [copied, setCopied] = useState(false);

  const validateField = (field: keyof FormValues, value: string): string | undefined => {
    switch (field) {
      case 'admin_email':     return validateAdminEmail(value);
      case 'admin_full_name': return validateAdminFullName(value);
      case 'workspace_name':  return validateWorkspaceName(value);
      case 'workspace_slug':  return validateWorkspaceSlug(value);
    }
  };

  const handleChange = (field: keyof FormValues) => (value: string) => {
    setValues((prev) => ({ ...prev, [field]: value }));
    setFieldServerErrors((prev) => ({ ...prev, [field]: undefined }));
    if (touched[field] || hasSubmitted) {
      setErrors((prev) => ({ ...prev, [field]: validateField(field, value) }));
    }
  };

  const handleBlur = (field: keyof FormValues) => () => {
    setTouched((prev) => ({ ...prev, [field]: true }));
    setErrors((prev) => ({ ...prev, [field]: validateField(field, values[field]) }));
  };

  const displayErrors: FormErrors = {};
  for (const k of Object.keys(INITIAL) as (keyof FormValues)[]) {
    if (touched[k] || hasSubmitted) displayErrors[k] = errors[k];
    if (fieldServerErrors[k]) displayErrors[k] = fieldServerErrors[k];
  }

  const validateAll = (): FormErrors => ({
    admin_email:     validateAdminEmail(values.admin_email),
    admin_full_name: validateAdminFullName(values.admin_full_name),
    workspace_name:  validateWorkspaceName(values.workspace_name),
    workspace_slug:  validateWorkspaceSlug(values.workspace_slug),
  });

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setHasSubmitted(true);
      setBannerError(null);
      setFieldServerErrors({});

      const all = validateAll();
      setErrors(all);
      if (Object.values(all).some(Boolean)) return;

      setIsSubmitting(true);
      try {
        const body: ProvisionExistingTenantRequest = {
          admin_email: values.admin_email.trim().toLowerCase(),
        };
        const fn = values.admin_full_name.trim();
        if (fn) body.admin_full_name = fn;
        const wn = values.workspace_name.trim();
        if (wn) body.workspace_name = wn;
        const ws = values.workspace_slug.trim().toLowerCase();
        if (ws) body.workspace_slug = ws;

        const response = await provisionExistingTenant(tenant.tenant_id, body);
        setResult(response.data);
        toast.success('Tenant provisioned successfully!');
      } catch (err) {
        if (isAxiosError(err)) {
          const status = err.response?.status;
          const data = err.response?.data as ApiErrorBody | undefined;
          if (status === 422) {
            setBannerError(data?.error?.message ?? 'Validation failed. Check the fields below.');
            const serverFields: FormErrors = {};
            for (const fe of data?.error?.fields ?? []) {
              serverFields[fe.field as keyof FormErrors] = fe.reason;
            }
            setFieldServerErrors(serverFields);
          } else if (status === 409) {
            setBannerError(data?.error?.message ?? 'This tenant has already been provisioned.');
          } else if (status === 403) {
            setBannerError('You do not have permission to provision tenants.');
          } else if (status === 404) {
            setBannerError('Tenant not found.');
          } else {
            setBannerError(data?.error?.message || 'An unexpected error occurred. Please try again.');
          }
        } else {
          setBannerError('An unexpected error occurred. Please try again.');
        }
      } finally {
        setIsSubmitting(false);
      }
    },
    [values, tenant.tenant_id],
  );

  const handleCopyInvitation = useCallback(() => {
    if (!result) return;
    const url = `${window.location.origin}${result.invitation.activation_url}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      toast.success('Invitation link copied to clipboard');
      setTimeout(() => setCopied(false), 3000);
    });
  }, [result]);

  const inputCls = (field: keyof FormValues) =>
    `w-full rounded-lg bg-dark-800/60 border px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 outline-none transition-colors focus:ring-2 focus:ring-primary-500/50 ${
      displayErrors[field] ? 'border-red-500/60' : 'border-dark-700/60 focus:border-primary-500/50'
    }`;

  // ─── Already provisioned shortcut ─────────────────────────────────
  const alreadyProvisioned = false; // backend gates this; banner will surface 409.

  // ─── Result panel ─────────────────────────────────────────────────
  if (result) {
    const activationUrl = `${window.location.origin}${result.invitation.activation_url}`;
    return (
      <div className="space-y-6" data-testid="provision-result">
        <div className="flex items-center gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4">
          <CheckCircle2 className="w-6 h-6 text-emerald-400 shrink-0" aria-hidden="true" />
          <div>
            <p className="text-sm font-semibold text-emerald-300">Provisioning complete</p>
            <p className="text-sm text-emerald-400/80 mt-0.5">
              Default workspace and admin account were created for <span className="font-medium">{result.tenant.tenant_name}</span>.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="rounded-xl border border-dark-700/60 bg-dark-900/40 p-4">
            <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-gray-500">
              <Building2 className="w-3.5 h-3.5" aria-hidden="true" /> Tenant
            </div>
            <p className="mt-2 text-sm text-white font-medium">{result.tenant.tenant_name}</p>
            <p className="text-xs text-gray-500 font-mono mt-0.5">{result.tenant.tenant_slug}</p>
          </div>
          <div className="rounded-xl border border-dark-700/60 bg-dark-900/40 p-4">
            <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-gray-500">
              <LayoutDashboard className="w-3.5 h-3.5" aria-hidden="true" /> Workspace
            </div>
            <p className="mt-2 text-sm text-white font-medium">{result.workspace.workspace_name}</p>
            <p className="text-xs text-gray-500 font-mono mt-0.5">{result.workspace.workspace_slug}</p>
          </div>
          <div className="rounded-xl border border-dark-700/60 bg-dark-900/40 p-4">
            <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-gray-500">
              <UserPlus className="w-3.5 h-3.5" aria-hidden="true" /> Admin
            </div>
            <p className="mt-2 text-sm text-white font-medium">{result.admin.email}</p>
            <p className="text-xs text-gray-500 mt-0.5">Status: {result.admin.status}</p>
          </div>
        </div>

        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
          <p className="text-xs uppercase tracking-wide text-amber-300/80 mb-2">
            Invitation link (shown only once)
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 truncate rounded-md bg-dark-900/60 border border-dark-700/60 px-3 py-2 text-xs text-gray-300 font-mono">
              {activationUrl}
            </code>
            <button
              type="button"
              onClick={handleCopyInvitation}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md bg-amber-500/10 border border-amber-500/30 text-amber-300 hover:bg-amber-500/20 text-xs font-medium transition-colors"
              data-testid="btn-copy-invitation"
            >
              <Copy className="w-3.5 h-3.5" aria-hidden="true" />
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <p className="mt-2 text-xs text-amber-400/70">
            Expires in {result.invitation.expires_in_hours} hours. Share with the admin so they can set their password.
          </p>
        </div>

        <div className="rounded-xl border border-dark-700/60 bg-dark-900/40 p-4">
          <p className="text-xs uppercase tracking-wide text-gray-500 mb-3">Provisioning steps</p>
          <ul className="space-y-1.5 text-sm">
            {result.provisioning_steps.map((s: ProvisioningStep) => (
              <li key={s.step_order} className="flex items-center gap-2">
                <span
                  className={`inline-block w-1.5 h-1.5 rounded-full ${
                    s.status === 'success' ? 'bg-emerald-400' :
                    s.status === 'skipped' ? 'bg-gray-500' : 'bg-red-400'
                  }`}
                  aria-hidden="true"
                />
                <span className="text-gray-300">{s.step_name}</span>
                <span className="text-xs text-gray-500">— {s.status}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="flex items-center gap-3">
          <Link
            to={`/admin/tenants/${tenant.tenant_id}`}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium transition-colors"
          >
            Back to tenant
          </Link>
          <Link
            to="/admin/tenants"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-dark-600 text-gray-300 hover:text-white text-sm font-medium transition-colors"
          >
            All tenants
          </Link>
        </div>
      </div>
    );
  }

  // ─── Form view ────────────────────────────────────────────────────
  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-6" data-testid="provision-existing-form">
      {/* Read-only tenant summary */}
      <div className="rounded-xl border border-dark-700/60 bg-dark-900/40 p-4 flex items-center gap-4">
        <div className="rounded-lg bg-primary-500/10 p-2.5">
          <Building2 className="w-5 h-5 text-primary-400" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium text-white truncate">{tenant.tenant_name}</p>
          <p className="text-xs text-gray-500 font-mono mt-0.5 truncate">
            {tenant.tenant_slug} • {tenant.region} • {tenant.plan}
          </p>
        </div>
      </div>

      {bannerError && (
        <div role="alert" className="flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/10 p-3">
          <AlertCircle className="w-5 h-5 text-red-400 mt-0.5 shrink-0" aria-hidden="true" />
          <p className="text-sm text-red-300">{bannerError}</p>
        </div>
      )}

      {/* Admin account */}
      <fieldset className="space-y-4">
        <legend className="text-sm font-semibold text-gray-200 mb-1">Admin account</legend>

        <div>
          <label htmlFor="admin-email" className="block text-xs uppercase tracking-wide text-gray-400 mb-1.5">
            Email <span className="text-red-400">*</span>
          </label>
          <input
            id="admin-email"
            type="email"
            value={values.admin_email}
            onChange={(e) => handleChange('admin_email')(e.target.value)}
            onBlur={handleBlur('admin_email')}
            className={inputCls('admin_email')}
            placeholder="admin@company.com"
            disabled={isSubmitting || alreadyProvisioned}
            data-testid="input-admin-email"
          />
          {displayErrors.admin_email && (
            <p className="mt-1 text-xs text-red-400">{displayErrors.admin_email}</p>
          )}
        </div>

        <div>
          <label htmlFor="admin-full-name" className="block text-xs uppercase tracking-wide text-gray-400 mb-1.5">
            Full name
          </label>
          <input
            id="admin-full-name"
            type="text"
            value={values.admin_full_name}
            onChange={(e) => handleChange('admin_full_name')(e.target.value)}
            onBlur={handleBlur('admin_full_name')}
            className={inputCls('admin_full_name')}
            placeholder="Jane Doe"
            disabled={isSubmitting || alreadyProvisioned}
            data-testid="input-admin-full-name"
          />
          {displayErrors.admin_full_name && (
            <p className="mt-1 text-xs text-red-400">{displayErrors.admin_full_name}</p>
          )}
        </div>
      </fieldset>

      {/* Workspace */}
      <fieldset className="space-y-4">
        <legend className="text-sm font-semibold text-gray-200 mb-1">Default workspace</legend>
        <p className="text-xs text-gray-500 -mt-2">
          Leave blank to default from the tenant name and slug.
        </p>

        <div>
          <label htmlFor="workspace-name" className="block text-xs uppercase tracking-wide text-gray-400 mb-1.5">
            Workspace name
          </label>
          <input
            id="workspace-name"
            type="text"
            value={values.workspace_name}
            onChange={(e) => handleChange('workspace_name')(e.target.value)}
            onBlur={handleBlur('workspace_name')}
            className={inputCls('workspace_name')}
            placeholder={`${tenant.tenant_name} Workspace`}
            disabled={isSubmitting || alreadyProvisioned}
            data-testid="input-workspace-name"
          />
          {displayErrors.workspace_name && (
            <p className="mt-1 text-xs text-red-400">{displayErrors.workspace_name}</p>
          )}
        </div>

        <div>
          <label htmlFor="workspace-slug" className="block text-xs uppercase tracking-wide text-gray-400 mb-1.5">
            Workspace slug
          </label>
          <input
            id="workspace-slug"
            type="text"
            value={values.workspace_slug}
            onChange={(e) => handleChange('workspace_slug')(e.target.value)}
            onBlur={handleBlur('workspace_slug')}
            className={inputCls('workspace_slug')}
            placeholder={tenant.tenant_slug}
            disabled={isSubmitting || alreadyProvisioned}
            data-testid="input-workspace-slug"
          />
          {displayErrors.workspace_slug && (
            <p className="mt-1 text-xs text-red-400">{displayErrors.workspace_slug}</p>
          )}
        </div>
      </fieldset>

      <div className="flex items-center gap-3 pt-2">
        <button
          type="submit"
          disabled={isSubmitting || alreadyProvisioned}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary-600 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
          data-testid="btn-submit-provision"
        >
          {isSubmitting ? (
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
          ) : (
            <Rocket className="w-4 h-4" aria-hidden="true" />
          )}
          {isSubmitting ? 'Provisioning…' : 'Provision Tenant'}
        </button>
        <Link
          to={`/admin/tenants/${tenant.tenant_id}`}
          className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <ChevronLeft className="w-4 h-4" aria-hidden="true" />
          Cancel
        </Link>
      </div>
    </form>
  );
}
