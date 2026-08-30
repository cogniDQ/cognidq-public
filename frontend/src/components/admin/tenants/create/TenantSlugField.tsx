/**
 * TenantSlugField — controlled text input for the tenant URL slug.
 *
 * Auto-populated from the name field while the user has not manually edited
 * it. Once the user types here, auto-generation stops permanently (the parent
 * tracks `slugUserModified`).
 *
 * Includes SlugImmutabilityNotice explaining that the slug cannot be changed
 * after the tenant is created.
 */

interface TenantSlugFieldProps {
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  error?: string;
}

const ID = 'tenant-slug';

export default function TenantSlugField({
  value,
  onChange,
  onBlur,
  error,
}: TenantSlugFieldProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={ID} className="block text-sm font-medium text-gray-300">
        Slug <span className="text-red-400" aria-hidden="true">*</span>
      </label>
      <input
        id={ID}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        maxLength={85}
        className={`w-full rounded-lg bg-dark-800/60 border px-3 py-2.5 text-sm text-gray-100 font-mono placeholder-gray-600 outline-none transition-colors focus:ring-2 focus:ring-primary-500/50 ${
          error ? 'border-red-500/60' : 'border-dark-700/60 focus:border-primary-500/50'
        }`}
        placeholder="e.g. acme-corp"
        aria-required="true"
        aria-describedby={
          [error ? `${ID}-error` : '', `${ID}-notice`].filter(Boolean).join(' ') || undefined
        }
        data-testid="field-tenant-slug"
      />
      {error && (
        <p id={`${ID}-error`} className="text-xs text-red-400" role="alert" data-testid="error-tenant-slug">
          {error}
        </p>
      )}
      {/* SlugImmutabilityNotice */}
      <p id={`${ID}-notice`} className="text-xs text-amber-500/80" data-testid="slug-immutability-notice">
        <span className="font-medium">Cannot be changed after creation.</span> Choose carefully — the
        slug forms part of the tenant's URL and API identifier.
      </p>
    </div>
  );
}
