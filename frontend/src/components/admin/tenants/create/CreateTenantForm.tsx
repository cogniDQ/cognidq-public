/**
 * CreateTenantForm — full create-tenant form with:
 *   - Auto-slug generation from name (stops once user manually edits slug)
 *   - Blur-triggered client-side validation (TDD §5.4)
 *   - 201 success → navigate to detail page + success toast
 *   - 422 → banner + inline field errors from error.fields
 *   - 403 → banner error
 *   - 5xx → generic banner error
 */
import { useState, useCallback, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { isAxiosError } from 'axios';
import toast from 'react-hot-toast';
import { AlertCircle } from 'lucide-react';

import { createTenant, CreateTenantRequest, ApiErrorBody, TenantRegion, TenantPlan } from '../../../../services/tenant';
import { generateSlug } from '../../../../utils/slugify';
import {
  TenantFormValues,
  TenantFormErrors,
  validateTenantName,
  validateTenantSlug,
  validateRegion,
  validatePlan,
  validateInitialStatus,
  validateServiceStartDate,
  validateTenantNotes,
  validateAll,
  hasNoErrors,
} from '../../../../utils/tenantValidation';

import TenantNameField from './TenantNameField';
import TenantSlugField from './TenantSlugField';
import RegionSelect from './RegionSelect';
import PlanSelect from './PlanSelect';
import InitialStatusSelect from './InitialStatusSelect';
import ServiceStartDatePicker from './ServiceStartDatePicker';
import TenantNotesTextarea from './TenantNotesTextarea';
import FormActions from './FormActions';

// ---------------------------------------------------------------------------
// Initial values
// ---------------------------------------------------------------------------

const INITIAL_VALUES: TenantFormValues = {
  tenant_name: '',
  tenant_slug: '',
  region: '',
  plan: '',
  initial_status: 'draft',
  service_start_date: '',
  tenant_notes: '',
};

// ---------------------------------------------------------------------------
// Field-level re-validator (called on blur and after submit)
// ---------------------------------------------------------------------------

function validateField(
  field: keyof TenantFormValues,
  value: string,
): string | undefined {
  switch (field) {
    case 'tenant_name':      return validateTenantName(value);
    case 'tenant_slug':      return validateTenantSlug(value);
    case 'region':           return validateRegion(value);
    case 'plan':             return validatePlan(value);
    case 'initial_status':   return validateInitialStatus(value);
    case 'service_start_date': return validateServiceStartDate(value);
    case 'tenant_notes':     return validateTenantNotes(value);
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CreateTenantForm() {
  const navigate = useNavigate();

  const [values, setValues] = useState<TenantFormValues>(INITIAL_VALUES);
  const [errors, setErrors] = useState<TenantFormErrors>({});
  /** Tracks fields the user has left (blurred) at least once. */
  const [touched, setTouched] = useState<Partial<Record<keyof TenantFormValues, boolean>>>({});
  /** After first submit attempt, show all errors regardless of touched state. */
  const [hasSubmitted, setHasSubmitted] = useState(false);
  /** Once true, name changes no longer overwrite the slug field. */
  const [slugUserModified, setSlugUserModified] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [bannerError, setBannerError] = useState<string | null>(null);
  /** Field-level error messages returned by the server (422 error.fields). */
  const [fieldServerErrors, setFieldServerErrors] = useState<TenantFormErrors>({});

  // Derive the errors to display: client errors (for touched/submitted fields)
  // merged with any server-returned field errors (server errors take precedence).
  const displayErrors: TenantFormErrors = {};
  for (const key of Object.keys(INITIAL_VALUES) as (keyof TenantFormValues)[]) {
    // Show client error if field is touched or form has been submitted
    if (touched[key] || hasSubmitted) {
      displayErrors[key] = errors[key];
    }
    // Server-returned field error always overrides client error
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
        const next: TenantFormValues = { ...prev, tenant_name: value };
        if (!slugUserModified) {
          next.tenant_slug = generateSlug(value);
        }
        return next;
      });
      // Clear server errors for this field on change
      setFieldServerErrors((prev) => ({ ...prev, tenant_name: undefined }));
      if (touched.tenant_name || hasSubmitted) {
        setErrors((prev) => ({ ...prev, tenant_name: validateTenantName(value) }));
      }
    },
    [slugUserModified, touched.tenant_name, hasSubmitted],
  );

  const handleSlugChange = useCallback(
    (value: string) => {
      setSlugUserModified(true);
      setValues((prev) => ({ ...prev, tenant_slug: value }));
      setFieldServerErrors((prev) => ({ ...prev, tenant_slug: undefined }));
      if (touched.tenant_slug || hasSubmitted) {
        setErrors((prev) => ({ ...prev, tenant_slug: validateTenantSlug(value) }));
      }
    },
    [touched.tenant_slug, hasSubmitted],
  );

  const handleFieldChange = useCallback(
    (field: keyof TenantFormValues) => (value: string) => {
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
    (field: keyof TenantFormValues) => () => {
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

      // Run full client-side validation
      const allErrors = validateAll(values);
      setErrors(allErrors);

      if (!hasNoErrors(allErrors)) {
        // Focus first invalid field for accessibility
        const firstErrorField = (Object.keys(allErrors) as (keyof TenantFormErrors)[]).find(
          (k) => allErrors[k],
        );
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
        const body: CreateTenantRequest = {
          tenant_name: values.tenant_name.trim(),
          tenant_slug: values.tenant_slug.trim().toLowerCase(),
          region: values.region as TenantRegion,
          plan: values.plan as TenantPlan,
        };
        if (values.initial_status && values.initial_status !== 'draft') {
          body.initial_status = values.initial_status as 'draft' | 'active';
        }
        if (values.service_start_date) {
          body.service_start_date = values.service_start_date;
        }
        const trimmedNotes = values.tenant_notes.trim();
        if (trimmedNotes) {
          body.tenant_notes = trimmedNotes;
        }

        const response = await createTenant(body);

        toast.success('Tenant created successfully.');
        navigate(`/admin/tenants/${response.data.tenant_id}`);
      } catch (err) {
        if (isAxiosError(err)) {
          const status = err.response?.status;
          const data = err.response?.data as ApiErrorBody | undefined;

          if (status === 422) {
            const message =
              data?.error?.message ?? 'Validation failed. Please check the fields below.';
            setBannerError(message);

            const serverFieldErrors: TenantFormErrors = {};
            for (const fe of data?.error?.fields ?? []) {
              serverFieldErrors[fe.field as keyof TenantFormErrors] = fe.reason;
            }
            setFieldServerErrors(serverFieldErrors);
          } else if (status === 403) {
            setBannerError('You do not have permission to create tenants.');
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
    [values, navigate],
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="space-y-6"
      aria-label="Create tenant form"
      data-testid="create-tenant-form"
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

      {/* Field grid — 2 columns on md+ */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <div className="md:col-span-2">
          <TenantNameField
            value={values.tenant_name}
            onChange={handleNameChange}
            onBlur={handleBlur('tenant_name')}
            error={displayErrors.tenant_name}
          />
        </div>

        <div className="md:col-span-2">
          <TenantSlugField
            value={values.tenant_slug}
            onChange={handleSlugChange}
            onBlur={handleBlur('tenant_slug')}
            error={displayErrors.tenant_slug}
          />
        </div>

        <RegionSelect
          value={values.region}
          onChange={handleFieldChange('region')}
          onBlur={handleBlur('region')}
          error={displayErrors.region}
        />

        <PlanSelect
          value={values.plan}
          onChange={handleFieldChange('plan')}
          onBlur={handleBlur('plan')}
          error={displayErrors.plan}
        />

        <InitialStatusSelect
          value={values.initial_status}
          onChange={handleFieldChange('initial_status')}
          onBlur={handleBlur('initial_status')}
          error={displayErrors.initial_status}
        />

        <ServiceStartDatePicker
          value={values.service_start_date}
          onChange={handleFieldChange('service_start_date')}
          onBlur={handleBlur('service_start_date')}
          error={displayErrors.service_start_date}
        />

        <div className="md:col-span-2">
          <TenantNotesTextarea
            value={values.tenant_notes}
            onChange={handleFieldChange('tenant_notes')}
            onBlur={handleBlur('tenant_notes')}
            error={displayErrors.tenant_notes}
          />
        </div>
      </div>

      <FormActions isSubmitting={isSubmitting} />
    </form>
  );
}
