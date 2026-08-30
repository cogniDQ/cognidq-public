/**
 * NumberSlider — Number input synced with slider, min/max/step
 */

interface NumberSliderProps {
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  step?: number
  label?: string
  suffix?: string
  disabled?: boolean
}

export function NumberSlider({
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  label,
  suffix = '',
  disabled = false,
}: NumberSliderProps) {
  const handleNumber = (raw: string) => {
    const n = parseFloat(raw)
    if (!isNaN(n)) {
      onChange(Math.max(min, Math.min(max, n)))
    }
  }

  const handleSlider = (raw: string) => {
    onChange(parseFloat(raw))
  }

  return (
    <div className="space-y-1">
      {label && (
        <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider">{label}</label>
      )}

      <div className="flex items-center gap-3">
        <input
          type="range"
          value={value}
          onChange={e => handleSlider(e.target.value)}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          className="flex-1 h-1.5 rounded-lg appearance-none cursor-pointer bg-dark-700 accent-primary-500 disabled:opacity-50"
        />
        <div className="flex items-center gap-1">
          <input
            type="number"
            value={value}
            onChange={e => handleNumber(e.target.value)}
            min={min}
            max={max}
            step={step}
            disabled={disabled}
            className="w-16 bg-dark-900 border border-dark-700 rounded px-2 py-1 text-sm text-gray-200 text-right focus:border-primary-500 focus:outline-none disabled:opacity-50"
          />
          {suffix && <span className="text-xs text-gray-500">{suffix}</span>}
        </div>
      </div>
    </div>
  )
}
