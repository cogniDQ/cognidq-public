/**
 * TenantNotesTextarea — optional notes field with live character counter.
 *
 * Max 5000 characters (TDD §6.8). Counter updates on every keypress so the
 * user can see how close they are to the limit.
 */

const MAX_LENGTH = 5000;

interface TenantNotesTextareaProps {
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  error?: string;
}

const ID = 'tenant-notes';

export default function TenantNotesTextarea({
  value,
  onChange,
  onBlur,
  error,
}: TenantNotesTextareaProps) {
  const remaining = MAX_LENGTH - value.length;
  const nearLimit = remaining <= 200;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <label htmlFor={ID} className="block text-sm font-medium text-gray-300">
          Notes <span className="text-gray-500 font-normal">(optional)</span>
        </label>
        <span
          className={`text-xs tabular-nums ${nearLimit ? 'text-amber-400' : 'text-gray-500'}`}
          aria-live="polite"
          aria-label={`${value.length} of ${MAX_LENGTH} characters used`}
          data-testid="notes-char-count"
        >
          {value.length} / {MAX_LENGTH}
        </span>
      </div>
      <textarea
        id={ID}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        rows={4}
        className={`w-full rounded-lg bg-dark-800/60 border px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 outline-none transition-colors resize-y focus:ring-2 focus:ring-primary-500/50 ${
          error ? 'border-red-500/60' : 'border-dark-700/60 focus:border-primary-500/50'
        }`}
        placeholder="Internal notes about this tenant…"
        aria-describedby={error ? `${ID}-error` : undefined}
        data-testid="field-tenant-notes"
      />
      {error && (
        <p id={`${ID}-error`} className="text-xs text-red-400" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
