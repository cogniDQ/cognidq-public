/**
 * TargetScopeSection — Column picker integration section
 * Uses the shared ColumnPicker component with proper label for the subtype.
 */
import { ColumnPicker } from '../shared/ColumnPicker'
import type { ValidationError } from '../../../schemas/dq-checks/types'

interface TargetScopeSectionProps {
  config: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
  availableColumns: string[]
  errors: ValidationError[]
  hasSource: boolean
  columnLabel?: string
}

export function TargetScopeSection({
  config,
  onChange,
  availableColumns,
  errors,
  hasSource,
  columnLabel = 'Target Columns',
}: TargetScopeSectionProps) {
  const selectedColumns = (config.columns as string[]) || []
  const columnError = errors.find(e => e.field === 'columns')

  return (
    <div className="space-y-3">
      <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Target Scope</h4>

      {hasSource && availableColumns.length > 0 ? (
        <ColumnPicker
          columns={availableColumns}
          selected={selectedColumns}
          onChange={(cols) => onChange('columns', cols)}
          label={columnLabel}
        />
      ) : hasSource ? (
        <div className="text-xs text-gray-500">
          Connected source has no column metadata.
        </div>
      ) : (
        <div className="text-xs text-gray-500">
          Connect a data source to see available columns.
        </div>
      )}

      {columnError && (
        <p className="text-xs text-red-400">{columnError.message}</p>
      )}
    </div>
  )
}
