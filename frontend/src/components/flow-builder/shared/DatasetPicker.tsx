/**
 * DatasetPicker — Dropdown from /datasets API list with search filter
 * 
 * Renders a searchable dropdown of datasets. Accepts a pre-fetched list
 * rather than fetching internally (the parent or hook provides the list).
 */
import { useState, useMemo } from 'react'
import { Search, Loader2 } from 'lucide-react'

export interface DatasetOption {
  id: string
  name: string
  description?: string
}

interface DatasetPickerProps {
  datasets: DatasetOption[]
  selected: string | null
  onChange: (datasetId: string | null) => void
  label?: string
  placeholder?: string
  loading?: boolean
  disabled?: boolean
}

export function DatasetPicker({
  datasets,
  selected,
  onChange,
  label = 'Reference Dataset',
  placeholder = 'Select a dataset…',
  loading = false,
  disabled = false,
}: DatasetPickerProps) {
  const [search, setSearch] = useState('')
  const [isOpen, setIsOpen] = useState(false)

  const filtered = useMemo(() => {
    if (!search.trim()) return datasets
    const q = search.toLowerCase()
    return datasets.filter(d =>
      d.name.toLowerCase().includes(q) ||
      (d.description && d.description.toLowerCase().includes(q))
    )
  }, [datasets, search])

  const selectedDataset = datasets.find(d => d.id === selected)

  const handleSelect = (id: string) => {
    onChange(id)
    setIsOpen(false)
    setSearch('')
  }

  const handleClear = () => {
    onChange(null)
  }

  return (
    <div className="space-y-1 relative">
      {label && (
        <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider">{label}</label>
      )}

      {/* Selected display / trigger */}
      <div className="relative">
        <button
          type="button"
          onClick={() => !disabled && setIsOpen(!isOpen)}
          disabled={disabled || loading}
          className="w-full bg-dark-900 border border-dark-700 rounded px-3 py-1.5 text-sm text-left flex items-center justify-between focus:border-primary-500 focus:outline-none disabled:opacity-50"
        >
          {loading ? (
            <span className="flex items-center gap-2 text-gray-500">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…
            </span>
          ) : selectedDataset ? (
            <span className="text-gray-200 truncate">{selectedDataset.name}</span>
          ) : (
            <span className="text-gray-500">{placeholder}</span>
          )}
          <svg className="w-4 h-4 text-gray-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {selected && !disabled && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-8 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
          >
            ×
          </button>
        )}
      </div>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-50 w-full bg-dark-800 border border-dark-700 rounded-lg shadow-xl mt-1">
          {/* Search */}
          <div className="p-2 border-b border-dark-700">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search datasets…"
                autoFocus
                className="w-full bg-dark-900 border border-dark-700 rounded pl-7 pr-2 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:border-primary-500 focus:outline-none"
              />
            </div>
          </div>

          {/* List */}
          <div className="max-h-48 overflow-y-auto p-1">
            {filtered.length === 0 ? (
              <div className="text-xs text-gray-500 text-center py-3">No datasets found</div>
            ) : (
              filtered.map(d => (
                <button
                  key={d.id}
                  type="button"
                  onClick={() => handleSelect(d.id)}
                  className={`w-full text-left px-3 py-2 rounded text-sm hover:bg-dark-700 ${
                    d.id === selected ? 'bg-primary-500/10 text-primary-300' : 'text-gray-300'
                  }`}
                >
                  <div className="truncate">{d.name}</div>
                  {d.description && (
                    <div className="text-xs text-gray-500 truncate">{d.description}</div>
                  )}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
