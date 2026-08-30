/**
 * ColumnPicker — Multi-select column picker with search, Select All, Clear, chips
 */
import { useState, useMemo } from 'react'
import { X, Search } from 'lucide-react'

interface ColumnPickerProps {
  columns: string[]
  selected: string[]
  onChange: (selected: string[]) => void
  label?: string
  placeholder?: string
  maxHeight?: string
  disabled?: boolean
}

export function ColumnPicker({
  columns,
  selected,
  onChange,
  label = 'Columns',
  placeholder = 'Search columns…',
  maxHeight = 'max-h-48',
  disabled = false,
}: ColumnPickerProps) {
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    if (!search.trim()) return columns
    const q = search.toLowerCase()
    return columns.filter(c => c.toLowerCase().includes(q))
  }, [columns, search])

  const toggle = (col: string) => {
    if (disabled) return
    onChange(
      selected.includes(col)
        ? selected.filter(c => c !== col)
        : [...selected, col]
    )
  }

  const selectAll = () => {
    if (disabled) return
    const merged = new Set([...selected, ...filtered])
    onChange(Array.from(merged))
  }

  const clear = () => {
    if (disabled) return
    onChange([])
  }

  const removeChip = (col: string) => {
    if (disabled) return
    onChange(selected.filter(c => c !== col))
  }

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">{label}</span>
        <span className="text-xs text-gray-500">
          {selected.length} of {columns.length} selected
        </span>
      </div>

      {/* Selected chips */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {selected.map(col => (
            <span
              key={col}
              className="inline-flex items-center gap-1 px-2 py-0.5 bg-primary-500/20 text-primary-300 text-xs rounded-full"
            >
              {col}
              {!disabled && (
                <button type="button" onClick={() => removeChip(col)} className="hover:text-white">
                  <X className="w-3 h-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}

      {/* Search + actions */}
      <div className="flex items-center gap-2">
        <div className="flex-1 relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={placeholder}
            disabled={disabled}
            className="w-full bg-dark-900 border border-dark-700 rounded pl-7 pr-2 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:border-primary-500 focus:outline-none"
          />
        </div>
        <button type="button" onClick={selectAll} disabled={disabled} className="text-xs text-primary-400 hover:text-primary-300 whitespace-nowrap disabled:opacity-50">
          Select All
        </button>
        <span className="text-xs text-gray-600">|</span>
        <button type="button" onClick={clear} disabled={disabled} className="text-xs text-gray-400 hover:text-gray-300 whitespace-nowrap disabled:opacity-50">
          Clear
        </button>
      </div>

      {/* Column list */}
      <div className={`${maxHeight} overflow-y-auto bg-dark-900/50 border border-dark-700 rounded-lg p-1.5 space-y-0.5`}>
        {filtered.length === 0 ? (
          <div className="text-xs text-gray-500 text-center py-3">
            {columns.length === 0 ? 'No columns available' : 'No matches'}
          </div>
        ) : (
          filtered.map((col, idx) => {
            const isSelected = selected.includes(col)
            return (
              <label
                key={`${col}-${idx}`}
                className={`flex items-center gap-2 cursor-pointer px-2 py-1.5 rounded hover:bg-dark-800/50 ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => toggle(col)}
                  disabled={disabled}
                  className="rounded bg-dark-800 border-dark-600 text-primary-500 focus:ring-primary-500 focus:ring-offset-0"
                />
                <span className={`text-sm truncate ${isSelected ? 'text-white' : 'text-gray-400'}`}>
                  {col}
                </span>
              </label>
            )
          })
        )}
      </div>
    </div>
  )
}
