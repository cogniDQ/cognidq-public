/**
 * RegionSelect — controlled dropdown for the tenant's deployment region.
 *
 * Includes RegionImmutabilityNotice as region cannot be changed after creation.
 */

export const REGION_OPTIONS = [
  { value: 'eu-west', label: 'EU West (Ireland)' },
  { value: 'eu-central', label: 'EU Central (Frankfurt)' },
  { value: 'us-east', label: 'US East (N. Virginia)' },
  { value: 'us-west', label: 'US West (Oregon)' },
] as const;

interface RegionSelectProps {
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  error?: string;
}

const ID = 'region';

export default function RegionSelect({
  value,
  onChange,
  onBlur,
  error,
}: RegionSelectProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={ID} className="block text-sm font-medium text-gray-300">
        Region <span className="text-red-400" aria-hidden="true">*</span>
      </label>
      <select
        id={ID}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        className={`w-full rounded-lg bg-dark-800/60 border px-3 py-2.5 text-sm text-gray-100 outline-none transition-colors focus:ring-2 focus:ring-primary-500/50 ${
          error ? 'border-red-500/60' : 'border-dark-700/60 focus:border-primary-500/50'
        }`}
        aria-required="true"
        aria-describedby={
          [error ? `${ID}-error` : '', `${ID}-notice`].filter(Boolean).join(' ') || undefined
        }
        data-testid="field-region"
      >
        <option value="">Select a region…</option>
        {REGION_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && (
        <p id={`${ID}-error`} className="text-xs text-red-400" role="alert" data-testid="error-region">
          {error}
        </p>
      )}
      {/* RegionImmutabilityNotice */}
      <p id={`${ID}-notice`} className="text-xs text-amber-500/80" data-testid="region-immutability-notice">
        <span className="font-medium">Cannot be changed after creation.</span> Select the region
        where this tenant's data will reside.
      </p>
    </div>
  );
}
