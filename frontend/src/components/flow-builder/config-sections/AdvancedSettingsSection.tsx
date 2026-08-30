/**
 * AdvancedSettingsSection — Collapsible with badge showing configured field count
 * Contains filter expression and other "advanced" scoped fields from the schema.
 */
import { CollapsibleSection } from '../shared/CollapsibleSection'
import type { FieldMeta, ValidationError } from '../../../schemas/dq-checks/types'

interface AdvancedSettingsSectionProps {
  config: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
  errors: ValidationError[]
  advancedFields?: FieldMeta[]
}

export function AdvancedSettingsSection({
  config,
  onChange,
  errors,
  advancedFields = [],
}: AdvancedSettingsSectionProps) {
  // Count how many advanced items have non-default values
  const filterExpr = (config.filter_expression as string) || ''
  let configuredCount = filterExpr.trim() ? 1 : 0
  configuredCount += advancedFields.filter(f => {
    const val = config[f.key]
    return val !== undefined && val !== null && val !== '' && val !== f.defaultValue
  }).length

  const filterError = errors.find(e => e.field === 'filter_expression')

  return (
    <CollapsibleSection
      title="Advanced Settings"
      badge={configuredCount > 0 ? configuredCount : undefined}
      defaultOpen={false}
    >
      <div className="space-y-3">
        {/* Filter expression — always present */}
        <div className="space-y-1">
          <label className="block text-xs text-gray-400">Row Filter Expression</label>
          <input
            type="text"
            value={filterExpr}
            onChange={e => onChange('filter_expression', e.target.value)}
            placeholder="e.g. status = 'active'"
            className="w-full bg-dark-900 border border-dark-700 rounded px-3 py-1.5 text-sm text-gray-200 font-mono placeholder-gray-600 focus:border-primary-500 focus:outline-none"
          />
          <p className="text-xs text-gray-600">Optional SQL-like expression to filter rows before checking</p>
          {filterError && <p className="text-xs text-red-400">{filterError.message}</p>}
        </div>

        {/* Subtype-specific advanced fields */}
        {advancedFields.map(field => {
          if (field.visibleWhen && !field.visibleWhen(config)) return null
          const fieldError = errors.find(e => e.field === field.key)

          return (
            <div key={field.key} className="space-y-1">
              <label className="block text-xs text-gray-400">{field.label}</label>
              <input
                type="text"
                value={String(config[field.key] ?? '')}
                onChange={e => onChange(field.key, e.target.value)}
                placeholder={field.placeholder || ''}
                className="w-full bg-dark-900 border border-dark-700 rounded px-3 py-1.5 text-sm text-gray-200 placeholder-gray-600 focus:border-primary-500 focus:outline-none"
              />
              {field.helpText && <p className="text-xs text-gray-600">{field.helpText}</p>}
              {fieldError && <p className="text-xs text-red-400">{fieldError.message}</p>}
            </div>
          )
        })}
      </div>
    </CollapsibleSection>
  )
}
