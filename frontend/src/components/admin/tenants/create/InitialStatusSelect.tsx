/**
 * InitialStatusSelect — controlled dropdown for the tenant's initial status.
 *
 * Per TDD §6.5 the only permitted initial statuses are `draft` and `active`.
 * `suspended` and `archived` are intentionally absent from the options list.
 */

const STATUS_OPTIONS = [
  { value: 'draft', label: 'Draft' },
  { value: 'active', label: 'Active' },
] as const;

interface InitialStatusSelectProps {
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  error?: string;
}

const ID = 'initial-status';

export default function InitialStatusSelect({
  value,
  onChange,
  onBlur,
  error,
}: InitialStatusSelectProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={ID} className="block text-sm font-medium text-gray-300">
        Initial Status
      </label>
      <select
        id={ID}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        className={`w-full rounded-lg bg-dark-800/60 border px-3 py-2.5 text-sm text-gray-100 outline-none transition-colors focus:ring-2 focus:ring-primary-500/50 ${
          error ? 'border-red-500/60' : 'border-dark-700/60 focus:border-primary-500/50'
        }`}
        aria-describedby={error ? `${ID}-error` : `${ID}-hint`}
        data-testid="field-initial-status"
      >
        {STATUS_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error ? (
        <p id={`${ID}-error`} className="text-xs text-red-400" role="alert">
          {error}
        </p>
      ) : (
        <p id={`${ID}-hint`} className="text-xs text-gray-500">
          Defaults to Draft. Select Active to make the tenant immediately operational.
        </p>
      )}
    </div>
  );
}
