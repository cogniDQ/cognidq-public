/**
 * StatusReasonField — textarea for the status_reason field on the Edit Tenant form.
 *
 * Used when the tenant is currently suspended or archived; the existing reason
 * is pre-populated and may be updated, but may not be cleared while the tenant
 * remains in those statuses (TDD §6.6 PATCH guard).
 *
 * Character counter: visible at all times; warns near 500-char limit.
 */

const MIN_LENGTH = 10;
const MAX_LENGTH = 500;

interface StatusReasonFieldProps {
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  error?: string;
  /** Whether the field is required (tenant is currently suspended or archived). */
  required: boolean;
}

const ID = 'status-reason';

export default function StatusReasonField({
  value,
  onChange,
  onBlur,
  error,
  required,
}: StatusReasonFieldProps) {
  const remaining = MAX_LENGTH - value.length;
  const nearLimit = remaining <= 50;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <label htmlFor={ID} className="block text-sm font-medium text-gray-300">
          Status Reason{' '}
          {required ? (
            <span className="text-red-400" aria-hidden="true">*</span>
          ) : (
            <span className="text-gray-500 font-normal">(optional)</span>
          )}
        </label>
        <span
          className={`text-xs tabular-nums ${nearLimit ? 'text-amber-400' : 'text-gray-500'}`}
          aria-live="polite"
          aria-label={`${value.length} of ${MAX_LENGTH} characters used`}
          data-testid="status-reason-char-count"
        >
          {value.length} / {MAX_LENGTH}
        </span>
      </div>
      <textarea
        id={ID}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        rows={3}
        minLength={MIN_LENGTH}
        maxLength={MAX_LENGTH + 10} /* allow typing slightly over to see live counter */
        className={`w-full rounded-lg bg-dark-800/60 border px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 outline-none transition-colors resize-y focus:ring-2 focus:ring-primary-500/50 ${
          error ? 'border-red-500/60' : 'border-dark-700/60 focus:border-primary-500/60'
        }`}
        placeholder="Describe the reason for this status (min 10 characters)…"
        aria-required={required}
        aria-describedby={error ? `${ID}-error` : `${ID}-hint`}
        data-testid="field-status-reason"
      />
      {error ? (
        <p id={`${ID}-error`} className="text-xs text-red-400" role="alert" data-testid="error-status-reason">
          {error}
        </p>
      ) : (
        <p id={`${ID}-hint`} className="text-xs text-gray-600">
          {required
            ? 'Required while this tenant is suspended or archived. Minimum 10 characters.'
            : 'Optional. Minimum 10 characters if provided.'}
        </p>
      )}
    </div>
  );
}
