/**
 * SearchableSelect — Combobox with search for dropdowns with many options
 */
import { useState, useMemo, useRef, useEffect } from 'react'
import { Search, ChevronDown } from 'lucide-react'

export interface SelectOption {
  value: string
  label: string
  description?: string
}

interface SearchableSelectProps {
  options: SelectOption[]
  value: string
  onChange: (value: string) => void
  label?: string
  placeholder?: string
  disabled?: boolean
}

export function SearchableSelect({
  options,
  value,
  onChange,
  label,
  placeholder = 'Select…',
  disabled = false,
}: SearchableSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState('')
  const wrapperRef = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    if (!search.trim()) return options
    const q = search.toLowerCase()
    return options.filter(o =>
      o.label.toLowerCase().includes(q) ||
      o.value.toLowerCase().includes(q) ||
      (o.description && o.description.toLowerCase().includes(q))
    )
  }, [options, search])

  const selectedOption = options.find(o => o.value === value)

  // Close on outside click
  useEffect(() => {
    const handle = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setIsOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [])

  const handleSelect = (val: string) => {
    onChange(val)
    setIsOpen(false)
    setSearch('')
  }

  return (
    <div className="space-y-1 relative" ref={wrapperRef}>
      {label && (
        <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider">{label}</label>
      )}

      {/* Trigger */}
      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className="w-full bg-dark-900 border border-dark-700 rounded px-3 py-1.5 text-sm text-left flex items-center justify-between focus:border-primary-500 focus:outline-none disabled:opacity-50"
      >
        <span className={selectedOption ? 'text-gray-200' : 'text-gray-500'}>
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <ChevronDown className="w-4 h-4 text-gray-500 flex-shrink-0" />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-50 w-full bg-dark-800 border border-dark-700 rounded-lg shadow-xl mt-1">
          {/* Search input */}
          <div className="p-2 border-b border-dark-700">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search…"
                autoFocus
                className="w-full bg-dark-900 border border-dark-700 rounded pl-7 pr-2 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:border-primary-500 focus:outline-none"
              />
            </div>
          </div>

          {/* Options */}
          <div className="max-h-48 overflow-y-auto p-1">
            {filtered.length === 0 ? (
              <div className="text-xs text-gray-500 text-center py-3">No options found</div>
            ) : (
              filtered.map(opt => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => handleSelect(opt.value)}
                  className={`w-full text-left px-3 py-2 rounded text-sm hover:bg-dark-700 ${
                    opt.value === value ? 'bg-primary-500/10 text-primary-300' : 'text-gray-300'
                  }`}
                >
                  <div>{opt.label}</div>
                  {opt.description && (
                    <div className="text-xs text-gray-500">{opt.description}</div>
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
