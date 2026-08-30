/**
 * KeyPairTable — Two-column mapping table (source ↔ target dropdowns, +Add/-Remove)
 * Minimum 1 row enforced.
 */
import { Plus, Trash2 } from 'lucide-react'

export interface KeyPair {
  source: string
  target: string
}

interface KeyPairTableProps {
  pairs: KeyPair[]
  onChange: (pairs: KeyPair[]) => void
  sourceColumns: string[]
  targetColumns: string[]
  sourceLabel?: string
  targetLabel?: string
  disabled?: boolean
}

export function KeyPairTable({
  pairs,
  onChange,
  sourceColumns,
  targetColumns,
  sourceLabel = 'Source Column',
  targetLabel = 'Target Column',
  disabled = false,
}: KeyPairTableProps) {
  const addRow = () => {
    onChange([...pairs, { source: '', target: '' }])
  }

  const removeRow = (index: number) => {
    if (pairs.length <= 1) return // minimum 1 row
    onChange(pairs.filter((_, i) => i !== index))
  }

  const updatePair = (index: number, field: 'source' | 'target', value: string) => {
    const next = pairs.map((p, i) => (i === index ? { ...p, [field]: value } : p))
    onChange(next)
  }

  return (
    <div className="space-y-2">
      {/* Header row */}
      <div className="grid grid-cols-[1fr_1fr_28px] gap-2 text-xs text-gray-500">
        <span>{sourceLabel}</span>
        <span>{targetLabel}</span>
        <span />
      </div>

      {/* Data rows */}
      {pairs.map((pair, idx) => (
        <div key={idx} className="grid grid-cols-[1fr_1fr_28px] gap-2 items-center">
          <select
            value={pair.source}
            onChange={e => updatePair(idx, 'source', e.target.value)}
            disabled={disabled}
            className="bg-dark-900 border border-dark-700 rounded px-2 py-1.5 text-sm text-gray-200 focus:border-primary-500 focus:outline-none disabled:opacity-50"
          >
            <option value="">—</option>
            {sourceColumns.map(col => (
              <option key={col} value={col}>{col}</option>
            ))}
          </select>

          <select
            value={pair.target}
            onChange={e => updatePair(idx, 'target', e.target.value)}
            disabled={disabled}
            className="bg-dark-900 border border-dark-700 rounded px-2 py-1.5 text-sm text-gray-200 focus:border-primary-500 focus:outline-none disabled:opacity-50"
          >
            <option value="">—</option>
            {targetColumns.map(col => (
              <option key={col} value={col}>{col}</option>
            ))}
          </select>

          <button
            type="button"
            onClick={() => removeRow(idx)}
            disabled={disabled || pairs.length <= 1}
            className="p-1 text-gray-500 hover:text-red-400 disabled:opacity-30 disabled:cursor-not-allowed"
            title="Remove row"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}

      {/* Add row */}
      <button
        type="button"
        onClick={addRow}
        disabled={disabled}
        className="flex items-center gap-1 text-xs text-primary-400 hover:text-primary-300 disabled:opacity-50"
      >
        <Plus className="w-3.5 h-3.5" />
        <span>Add mapping</span>
      </button>
    </div>
  )
}
