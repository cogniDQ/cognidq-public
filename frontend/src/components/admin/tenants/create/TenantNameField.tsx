/**
 * TenantNameField — controlled text input for the tenant display name.
 *
 * Validation fires on blur and errors are shown when `error` prop is set.
 * All form state is managed by the parent (CreateTenantForm).
 */

interface TenantNameFieldProps {
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  error?: string;
}

const ID = 'tenant-name';

export default function TenantNameField({
  value,
  onChange,
  onBlur,
  error,
}: TenantNameFieldProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={ID} className="block text-sm font-medium text-gray-300">
        Tenant Name <span className="text-red-400" aria-hidden="true">*</span>
      </label>
      <input
        id={ID}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        maxLength={155} /* slightly above 150 to allow server-side to catch exact edge cases */
        className={`w-full rounded-lg bg-dark-800/60 border px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 outline-none transition-colors focus:ring-2 focus:ring-primary-500/50 ${
          error ? 'border-red-500/60' : 'border-dark-700/60 focus:border-primary-500/50'
        }`}
        placeholder="e.g. Acme Corporation"
        aria-required="true"
        aria-describedby={error ? `${ID}-error` : undefined}
        data-testid="field-tenant-name"
      />
      {error && (
        <p id={`${ID}-error`} className="text-xs text-red-400" role="alert" data-testid="error-tenant-name">
          {error}
        </p>
      )}
    </div>
  );
}
