/**
 * CheckTypeSection — Dimension chip, subtype dropdown with descriptions,
 * and "Start from Template" button.
 * Always visible for all check types.
 */
import type { BaseCheckConfig, DimensionSchema, ValidationError } from '../../../schemas/dq-checks/types'

interface CheckTypeSectionProps {
  dimension: string
  schema: DimensionSchema | undefined
  config: BaseCheckConfig & Record<string, unknown>
  onChange: (key: string, value: unknown) => void
  errors: ValidationError[]
  onOpenTemplatePicker: () => void
  appliedTemplate: { id: string; name: string } | null
}

// Dimension display colors
const DIMENSION_COLORS: Record<string, string> = {
  completeness: 'bg-green-500/20 text-green-400 border-green-500/30',
  validity: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  uniqueness: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  conformity: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  consistency: 'bg-violet-500/20 text-violet-400 border-violet-500/30',
  timeliness: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  accuracy: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  reconciliation: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
}

export function CheckTypeSection({
  dimension,
  schema,
  config,
  onChange,
  errors,
  onOpenTemplatePicker,
  appliedTemplate,
}: CheckTypeSectionProps) {
  const subtypeError = errors.find(e => e.field === 'subtype')?.message
  const dimLabel = dimension.charAt(0).toUpperCase() + dimension.slice(1)
  const colorClass = DIMENSION_COLORS[dimension] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'

  return (
    <div className="space-y-3">
      <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Check Type</h4>

      {/* Dimension Chip (read-only) */}
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-1">Dimension</label>
        <span className={`inline-block px-3 py-1 rounded-full text-xs font-medium border ${colorClass}`}>
          {dimLabel}
        </span>
      </div>

      {/* Subtype Dropdown */}
      {schema && schema.subtypes.length > 0 ? (
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">
            Check Subtype <span className="text-red-400">*</span>
          </label>
          <select
            value={config.subtype || ''}
            onChange={(e) => onChange('subtype', e.target.value)}
            className={`w-full bg-dark-800 border rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none ${
              subtypeError ? 'border-red-500/50' : 'border-dark-700'
            }`}
          >
            <option value="">Select a check type...</option>
            {schema.subtypes.map(st => (
              <option key={st.subtype} value={st.subtype}>
                {st.label}
              </option>
            ))}
          </select>
          {/* Subtype description */}
          {config.subtype && (() => {
            const st = schema.subtypes.find(s => s.subtype === config.subtype)
            return st ? (
              <p className="text-xs text-gray-500 mt-1">{st.description}</p>
            ) : null
          })()}
          {subtypeError && (
            <p className="text-xs text-red-400 mt-1">{subtypeError}</p>
          )}
        </div>
      ) : (
        <div className="text-xs text-gray-500">
          No schema registered for {dimLabel}. Using basic configuration.
        </div>
      )}

      {/* Template Button */}
      <button
        type="button"
        onClick={onOpenTemplatePicker}
        className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-sm text-primary-400 hover:bg-dark-700 hover:border-primary-500/30 transition-colors flex items-center justify-center space-x-2"
      >
        <span>📋</span>
        <span>Start from Template</span>
      </button>

      {/* Applied template banner */}
      {appliedTemplate && (
        <div className="px-3 py-2 bg-primary-500/10 border border-primary-500/20 rounded-lg text-xs text-primary-300">
          Started from template: <span className="font-medium">{appliedTemplate.name}</span>. All fields are editable.
        </div>
      )}
    </div>
  )
}
