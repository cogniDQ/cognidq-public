/**
 * BusinessLogicSection — Dynamic field rendering from schema FieldMeta
 *
 * Renders subtype-specific fields using the appropriate shared components
 * based on each field's inputType. Only appears when the subtype has fields.
 */
import type { FieldMeta, ValidationError } from '../../../schemas/dq-checks/types'
import { TagInput } from '../shared/TagInput'
import { ExpressionEditor } from '../shared/ExpressionEditor'
import { NumberSlider } from '../shared/NumberSlider'
import { ColumnPicker } from '../shared/ColumnPicker'
import { DurationInput } from '../shared/DurationInput'

interface BusinessLogicSectionProps {
  fields: FieldMeta[]
  config: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
  errors: ValidationError[]
  availableColumns: string[]
}

export function BusinessLogicSection({
  fields,
  config,
  onChange,
  errors,
  availableColumns,
}: BusinessLogicSectionProps) {
  // Only show fields that belong to businessLogic section
  const businessFields = fields.filter(f => f.section === 'businessLogic')
  if (businessFields.length === 0) return null

  // Filter visible fields
  const visibleFields = businessFields.filter(f => {
    if (!f.visibleWhen) return true
    return f.visibleWhen(config)
  })

  if (visibleFields.length === 0) return null

  return (
    <div className="space-y-3">
      <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Configuration</h4>

      {visibleFields.map(field => (
        <FieldRenderer
          key={field.key}
          field={field}
          value={config[field.key]}
          onChange={(val) => onChange(field.key, val)}
          onConfigChange={onChange}
          error={errors.find(e => e.field === field.key)}
          availableColumns={availableColumns}
          config={config}
        />
      ))}
    </div>
  )
}

// ─── Field Renderer ───────────────────────────────────────────────

interface FieldRendererProps {
  field: FieldMeta
  value: unknown
  onChange: (value: unknown) => void
  onConfigChange: (key: string, value: unknown) => void
  error?: ValidationError
  availableColumns: string[]
  config: Record<string, unknown>
}

function FieldRenderer({ field, value, onChange, onConfigChange, error, availableColumns, config }: FieldRendererProps) {
  const errorMsg = error?.message

  switch (field.inputType) {
    case 'text':
      return (
        <div className="space-y-1">
          <label className="block text-xs text-gray-400">{field.label}</label>
          <input
            type="text"
            value={(value as string) ?? ''}
            onChange={e => onChange(e.target.value)}
            placeholder={field.placeholder || ''}
            className="w-full bg-dark-900 border border-dark-700 rounded px-3 py-1.5 text-sm text-gray-200 placeholder-gray-600 focus:border-primary-500 focus:outline-none"
          />
          {field.helpText && <p className="text-xs text-gray-600">{field.helpText}</p>}
          {errorMsg && <p className="text-xs text-red-400">{errorMsg}</p>}
        </div>
      )

    case 'number':
      return (
        <div className="space-y-1">
          <label className="block text-xs text-gray-400">{field.label}</label>
          <input
            type="number"
            value={value === null || value === undefined ? '' : String(value)}
            onChange={e => {
              const raw = e.target.value
              if (raw === '') { onChange(null); return }
              const n = parseFloat(raw)
              if (!isNaN(n)) onChange(n)
            }}
            min={field.min}
            max={field.max}
            placeholder={field.placeholder || ''}
            className="w-full bg-dark-900 border border-dark-700 rounded px-3 py-1.5 text-sm text-gray-200 placeholder-gray-600 focus:border-primary-500 focus:outline-none"
          />
          {field.helpText && <p className="text-xs text-gray-600">{field.helpText}</p>}
          {errorMsg && <p className="text-xs text-red-400">{errorMsg}</p>}
        </div>
      )

    case 'number-slider':
      return (
        <div className="space-y-1">
          <NumberSlider
            value={(value as number) ?? field.defaultValue as number ?? 0}
            onChange={onChange as (v: number) => void}
            label={field.label}
            min={field.min ?? 0}
            max={field.max ?? 100}
            step={field.max === 1 ? 0.01 : 1}
          />
          {field.helpText && <p className="text-xs text-gray-600">{field.helpText}</p>}
          {errorMsg && <p className="text-xs text-red-400">{errorMsg}</p>}
        </div>
      )

    case 'dropdown':
      return (
        <div className="space-y-1">
          <label className="block text-xs text-gray-400">{field.label}</label>
          <select
            value={(value as string) ?? ''}
            onChange={e => onChange(e.target.value)}
            className="w-full bg-dark-900 border border-dark-700 rounded px-3 py-1.5 text-sm text-gray-200 focus:border-primary-500 focus:outline-none"
          >
            {field.options?.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          {field.helpText && <p className="text-xs text-gray-600">{field.helpText}</p>}
          {errorMsg && <p className="text-xs text-red-400">{errorMsg}</p>}
        </div>
      )

    case 'toggle':
      return (
        <div className="space-y-1">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={!!value}
              onChange={e => onChange(e.target.checked)}
              className="rounded bg-dark-800 border-dark-600 text-primary-500 focus:ring-primary-500 focus:ring-offset-0"
            />
            <span className="text-sm text-gray-300">{field.label}</span>
          </label>
          {field.helpText && <p className="text-xs text-gray-600 ml-6">{field.helpText}</p>}
          {errorMsg && <p className="text-xs text-red-400">{errorMsg}</p>}
        </div>
      )

    case 'radio':
      return (
        <div className="space-y-1">
          <label className="block text-xs text-gray-400">{field.label}</label>
          <div className="space-y-1">
            {field.options?.map(opt => (
              <label key={opt.value} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name={field.key}
                  value={opt.value}
                  checked={value === opt.value}
                  onChange={() => onChange(opt.value)}
                  className="text-primary-500 focus:ring-primary-500 focus:ring-offset-0 bg-dark-800 border-dark-600"
                />
                <span className="text-sm text-gray-300">{opt.label}</span>
              </label>
            ))}
          </div>
          {field.helpText && <p className="text-xs text-gray-600">{field.helpText}</p>}
          {errorMsg && <p className="text-xs text-red-400">{errorMsg}</p>}
        </div>
      )

    case 'tag-input':
      return (
        <div>
          <TagInput
            tags={(value as string[]) ?? []}
            onChange={onChange as (v: string[]) => void}
            label={field.label}
            placeholder={field.placeholder}
          />
          {errorMsg && <p className="text-xs text-red-400">{errorMsg}</p>}
        </div>
      )

    case 'expression':
      return (
        <div>
          <ExpressionEditor
            value={(value as string) ?? ''}
            onChange={onChange as (v: string) => void}
            label={field.label}
            placeholder={field.placeholder}
            syntaxHint={field.helpText}
          />
          {errorMsg && <p className="text-xs text-red-400">{errorMsg}</p>}
        </div>
      )

    case 'column-picker': {
      // Single column selection rendered as dropdown for scalar fields
      const isSingleColumn = typeof field.defaultValue === 'string'
      if (isSingleColumn) {
        return (
          <div className="space-y-1">
            <label className="block text-xs text-gray-400">{field.label}</label>
            <select
              value={(value as string) ?? ''}
              onChange={e => onChange(e.target.value)}
              className="w-full bg-dark-900 border border-dark-700 rounded px-3 py-1.5 text-sm text-gray-200 focus:border-primary-500 focus:outline-none"
            >
              <option value="">Select column…</option>
              {availableColumns.map(col => (
                <option key={col} value={col}>{col}</option>
              ))}
            </select>
            {field.helpText && <p className="text-xs text-gray-600">{field.helpText}</p>}
            {errorMsg && <p className="text-xs text-red-400">{errorMsg}</p>}
          </div>
        )
      }
      // Multi-column for array defaults
      return (
        <div>
          <ColumnPicker
            columns={availableColumns}
            selected={(value as string[]) ?? []}
            onChange={onChange as (v: string[]) => void}
            label={field.label}
          />
          {errorMsg && <p className="text-xs text-red-400">{errorMsg}</p>}
        </div>
      )
    }

    case 'time':
      return (
        <div className="space-y-1">
          <label className="block text-xs text-gray-400">{field.label}</label>
          <input
            type="time"
            value={(value as string) ?? ''}
            onChange={e => onChange(e.target.value)}
            className="bg-dark-900 border border-dark-700 rounded px-3 py-1.5 text-sm text-gray-200 focus:border-primary-500 focus:outline-none"
          />
          {field.helpText && <p className="text-xs text-gray-600">{field.helpText}</p>}
          {errorMsg && <p className="text-xs text-red-400">{errorMsg}</p>}
        </div>
      )

    case 'duration': {
      // The companion unit field is the same key with '_value' replaced by '_unit'
      const unitKey = field.key.replace('_value', '_unit')
      const currentUnit = (config[unitKey] as string) || 'hours'
      return (
        <div>
          <DurationInput
            value={(value as number) ?? 1}
            unit={currentUnit as 'minutes' | 'hours' | 'days' | 'weeks'}
            onValueChange={onChange as (v: number) => void}
            onUnitChange={(u) => onConfigChange(unitKey, u)}
            label={field.label}
          />
          {field.helpText && <p className="text-xs text-gray-600">{field.helpText}</p>}
          {errorMsg && <p className="text-xs text-red-400">{errorMsg}</p>}
        </div>
      )
    }

    default:
      return (
        <div className="space-y-1">
          <label className="block text-xs text-gray-400">{field.label}</label>
          <input
            type="text"
            value={String(value ?? '')}
            onChange={e => onChange(e.target.value)}
            className="w-full bg-dark-900 border border-dark-700 rounded px-3 py-1.5 text-sm text-gray-200 focus:border-primary-500 focus:outline-none"
          />
        </div>
      )
  }
}
