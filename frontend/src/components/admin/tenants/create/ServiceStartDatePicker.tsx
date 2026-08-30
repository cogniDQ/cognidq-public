/**
 * ServiceStartDatePicker — optional date input for the tenant's service start date.
 *
 * Past and future dates are both permitted (TDD §6.7).
 * Uses the native <input type="date"> which provides a YYYY-MM-DD value.
 */

interface ServiceStartDatePickerProps {
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  error?: string;
}

const ID = 'service-start-date';

export default function ServiceStartDatePicker({
  value,
  onChange,
  onBlur,
  error,
}: ServiceStartDatePickerProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={ID} className="block text-sm font-medium text-gray-300">
        Service Start Date{' '}
        <span className="text-gray-500 font-normal">(optional)</span>
      </label>
      <input
        id={ID}
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        className={`w-full rounded-lg bg-dark-800/60 border px-3 py-2.5 text-sm text-gray-100 outline-none transition-colors focus:ring-2 focus:ring-primary-500/50 ${
          error ? 'border-red-500/60' : 'border-dark-700/60 focus:border-primary-500/50'
        }`}
        aria-describedby={error ? `${ID}-error` : undefined}
        data-testid="field-service-start-date"
      />
      {error && (
        <p id={`${ID}-error`} className="text-xs text-red-400" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
