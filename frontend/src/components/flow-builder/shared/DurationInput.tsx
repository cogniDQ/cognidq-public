/**
 * DurationInput — Number + unit dropdown with human-readable preview
 */

type DurationUnit = 'minutes' | 'hours' | 'days' | 'weeks'

interface DurationInputProps {
  value: number
  unit: DurationUnit
  onValueChange: (value: number) => void
  onUnitChange: (unit: DurationUnit) => void
  label?: string
  min?: number
  max?: number
  disabled?: boolean
}

const UNIT_OPTIONS: { value: DurationUnit; label: string }[] = [
  { value: 'minutes', label: 'Minutes' },
  { value: 'hours', label: 'Hours' },
  { value: 'days', label: 'Days' },
  { value: 'weeks', label: 'Weeks' },
]

function formatPreview(value: number, unit: DurationUnit): string {
  if (value <= 0) return ''

  // Convert to a single canonical representation
  const totalMinutes =
    unit === 'minutes' ? value :
    unit === 'hours' ? value * 60 :
    unit === 'days' ? value * 1440 :
    value * 10080

  if (totalMinutes >= 10080 && totalMinutes % 10080 === 0) {
    const w = totalMinutes / 10080
    return `= ${w} week${w !== 1 ? 's' : ''}`
  }
  if (totalMinutes >= 1440 && totalMinutes % 1440 === 0) {
    const d = totalMinutes / 1440
    return `= ${d} day${d !== 1 ? 's' : ''}`
  }
  if (totalMinutes >= 60 && totalMinutes % 60 === 0) {
    const h = totalMinutes / 60
    return `= ${h} hour${h !== 1 ? 's' : ''}`
  }
  return `= ${totalMinutes} minute${totalMinutes !== 1 ? 's' : ''}`
}

export function DurationInput({
  value,
  unit,
  onValueChange,
  onUnitChange,
  label,
  min = 1,
  max = 9999,
  disabled = false,
}: DurationInputProps) {
  const preview = formatPreview(value, unit)

  return (
    <div className="space-y-1">
      {label && (
        <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider">{label}</label>
      )}

      <div className="flex items-center gap-2">
        <input
          type="number"
          value={value}
          onChange={e => {
            const n = parseInt(e.target.value, 10)
            if (!isNaN(n)) onValueChange(Math.max(min, Math.min(max, n)))
          }}
          min={min}
          max={max}
          disabled={disabled}
          className="w-20 bg-dark-900 border border-dark-700 rounded px-2 py-1.5 text-sm text-gray-200 focus:border-primary-500 focus:outline-none disabled:opacity-50"
        />
        <select
          value={unit}
          onChange={e => onUnitChange(e.target.value as DurationUnit)}
          disabled={disabled}
          className="bg-dark-900 border border-dark-700 rounded px-2 py-1.5 text-sm text-gray-200 focus:border-primary-500 focus:outline-none disabled:opacity-50"
        >
          {UNIT_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>

        {preview && (
          <span className="text-xs text-gray-500">{preview}</span>
        )}
      </div>
    </div>
  )
}
