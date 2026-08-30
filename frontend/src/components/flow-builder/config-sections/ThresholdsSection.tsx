/**
 * ThresholdsSection — Pass threshold (number+slider), warning threshold (toggle),
 * and null handling dropdown.
 * Always visible for all check types.
 */
import type { BaseCheckConfig, NullHandling, ValidationError } from '../../../schemas/dq-checks/types'
import { NULL_HANDLING_OPTIONS } from '../../../schemas/dq-checks/types'

interface ThresholdsSectionProps {
  config: BaseCheckConfig & Record<string, unknown>
  onChange: (key: string, value: unknown) => void
  errors: ValidationError[]
}

export function ThresholdsSection({ config, onChange, errors }: ThresholdsSectionProps) {
  const passError = errors.find(e => e.field === 'threshold_pass')?.message
  const warnError = errors.find(e => e.field === 'threshold_warn')?.message
  const hasWarnThreshold = config.threshold_warn !== null && config.threshold_warn !== undefined

  return (
    <div className="space-y-3">
      <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Thresholds</h4>

      {/* Pass Threshold */}
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-1">
          Pass Threshold (%)
        </label>
        <div className="flex items-center space-x-3">
          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={config.threshold_pass}
            onChange={(e) => onChange('threshold_pass', parseInt(e.target.value))}
            className="flex-1 h-2 bg-dark-700 rounded-lg appearance-none cursor-pointer accent-primary-500"
          />
          <input
            type="number"
            min={0}
            max={100}
            value={config.threshold_pass}
            onChange={(e) => {
              const val = parseInt(e.target.value)
              if (!isNaN(val)) onChange('threshold_pass', Math.min(100, Math.max(0, val)))
            }}
            className={`w-16 bg-dark-800 border rounded-lg px-2 py-1 text-sm text-gray-200 text-center focus:border-primary-500 outline-none ${
              passError ? 'border-red-500/50' : 'border-dark-700'
            }`}
          />
          <span className="text-sm text-gray-400">%</span>
        </div>
        {config.threshold_pass === 100 && (
          <p className="text-xs text-yellow-400/70 mt-1">
            100% threshold means any single violation fails the check
          </p>
        )}
        {passError && <p className="text-xs text-red-400 mt-1">{passError}</p>}
      </div>

      {/* Warning Threshold Toggle */}
      <div>
        <label className="flex items-center space-x-2 cursor-pointer">
          <input
            type="checkbox"
            checked={hasWarnThreshold}
            onChange={(e) => {
              if (e.target.checked) {
                onChange('threshold_warn', Math.max(0, config.threshold_pass - 5))
              } else {
                onChange('threshold_warn', null)
              }
            }}
            className="rounded bg-dark-800 border-dark-600 text-primary-500 focus:ring-primary-500 focus:ring-offset-0"
          />
          <span className="text-sm text-gray-300">Add warning threshold</span>
        </label>
      </div>

      {hasWarnThreshold && (
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">
            Warning Threshold (%)
          </label>
          <div className="flex items-center space-x-3">
            <input
              type="range"
              min={0}
              max={config.threshold_pass}
              step={1}
              value={config.threshold_warn ?? 0}
              onChange={(e) => onChange('threshold_warn', parseInt(e.target.value))}
              className="flex-1 h-2 bg-dark-700 rounded-lg appearance-none cursor-pointer accent-orange-500"
            />
            <input
              type="number"
              min={0}
              max={config.threshold_pass}
              value={config.threshold_warn ?? 0}
              onChange={(e) => {
                const val = parseInt(e.target.value)
                if (!isNaN(val)) onChange('threshold_warn', Math.min(config.threshold_pass, Math.max(0, val)))
              }}
              className={`w-16 bg-dark-800 border rounded-lg px-2 py-1 text-sm text-gray-200 text-center focus:border-primary-500 outline-none ${
                warnError ? 'border-red-500/50' : 'border-dark-700'
              }`}
            />
            <span className="text-sm text-gray-400">%</span>
          </div>
          {warnError && <p className="text-xs text-red-400 mt-1">{warnError}</p>}
        </div>
      )}

      {/* Null Handling */}
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-1">
          Null Handling
        </label>
        <select
          value={config.null_handling}
          onChange={(e) => onChange('null_handling', e.target.value as NullHandling)}
          className="w-full bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
        >
          {NULL_HANDLING_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        {/* Show description of selected option */}
        {(() => {
          const selected = NULL_HANDLING_OPTIONS.find(o => o.value === config.null_handling)
          return selected ? (
            <p className="text-xs text-gray-500 mt-1">{selected.description}</p>
          ) : null
        })()}
      </div>
    </div>
  )
}
