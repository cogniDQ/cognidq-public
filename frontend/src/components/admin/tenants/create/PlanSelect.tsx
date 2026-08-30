/**
 * PlanSelect — controlled dropdown for the tenant's billing plan.
 */

export const PLAN_OPTIONS = [
  { value: 'starter', label: 'Starter' },
  { value: 'growth', label: 'Growth' },
  { value: 'enterprise', label: 'Enterprise' },
] as const;

interface PlanSelectProps {
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  error?: string;
}

const ID = 'plan';

export default function PlanSelect({
  value,
  onChange,
  onBlur,
  error,
}: PlanSelectProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={ID} className="block text-sm font-medium text-gray-300">
        Plan <span className="text-red-400" aria-hidden="true">*</span>
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
        aria-describedby={error ? `${ID}-error` : undefined}
        data-testid="field-plan"
      >
        <option value="">Select a plan…</option>
        {PLAN_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && (
        <p id={`${ID}-error`} className="text-xs text-red-400" role="alert" data-testid="error-plan">
          {error}
        </p>
      )}
    </div>
  );
}
