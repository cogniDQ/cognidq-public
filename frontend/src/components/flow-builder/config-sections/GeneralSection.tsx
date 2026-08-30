/**
 * GeneralSection — Rule name, severity, and description fields.
 * Always visible for all check types.
 */
import type { BaseCheckConfig, Severity, ValidationError } from '../../../schemas/dq-checks/types'
import { SEVERITY_OPTIONS } from '../../../schemas/dq-checks/types'

interface GeneralSectionProps {
  config: BaseCheckConfig & Record<string, unknown>
  onChange: (key: string, value: unknown) => void
  errors: ValidationError[]
  collapsed?: boolean
}

export function GeneralSection({ config, onChange, errors }: GeneralSectionProps) {
  const getError = (field: string) => errors.find(e => e.field === field)?.message

  return (
    <div className="space-y-3">
      <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">General</h4>

      {/* Rule Name */}
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-1">
          Rule Name
        </label>
        <input
          type="text"
          value={config.ruleName || ''}
          onChange={(e) => onChange('ruleName', e.target.value)}
          placeholder="Auto-generated if empty"
          className="w-full bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
        />
      </div>

      {/* Severity */}
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-1">
          Severity
        </label>
        <select
          value={config.severity}
          onChange={(e) => onChange('severity', e.target.value as Severity)}
          className="w-full bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
        >
          {SEVERITY_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      {/* Description */}
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-1">
          Description
          <span className="text-gray-500 font-normal ml-1">(optional)</span>
        </label>
        <textarea
          value={config.description || ''}
          onChange={(e) => onChange('description', e.target.value)}
          placeholder="Describe what this check verifies"
          rows={2}
          className="w-full bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none resize-none"
        />
        {getError('description') && (
          <p className="text-xs text-red-400 mt-1">{getError('description')}</p>
        )}
      </div>
    </div>
  )
}
