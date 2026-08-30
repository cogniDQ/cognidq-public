/**
 * TemplatePicker — Overlay panel for selecting a pre-built check template.
 * 
 * Filters templates by the current dimension and provides search.
 * On apply, the parent receives the template config to fill the form.
 */
import { useState, useMemo } from 'react'
import { ArrowLeft, Search } from 'lucide-react'

export interface Template {
  id: string
  dimension: string
  name: string
  description: string
  presetConfig: Record<string, unknown>
}

interface TemplatePickerProps {
  dimension: string
  templates: Template[]
  loading?: boolean
  onApply: (template: Template) => void
  onBack: () => void
}

export function TemplatePicker({
  dimension,
  templates,
  loading = false,
  onApply,
  onBack,
}: TemplatePickerProps) {
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    const dimTemplates = templates.filter(t => t.dimension === dimension)
    if (!search.trim()) return dimTemplates
    const q = search.toLowerCase()
    return dimTemplates.filter(
      t =>
        t.name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q)
    )
  }, [templates, dimension, search])

  const dimLabel = dimension.charAt(0).toUpperCase() + dimension.slice(1)

  return (
    <div className="absolute inset-0 bg-dark-800 z-10 flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-dark-700 flex-shrink-0">
        <button
          onClick={onBack}
          className="p-1.5 hover:bg-dark-700 rounded-lg transition-colors"
        >
          <ArrowLeft className="w-4 h-4 text-gray-400" />
        </button>
        <div>
          <h3 className="text-sm font-semibold text-white">Choose a Template</h3>
          <p className="text-xs text-gray-400">{dimLabel} templates</p>
        </div>
      </div>

      {/* Search */}
      <div className="px-4 py-3 border-b border-dark-700 flex-shrink-0">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search templates…"
            className="w-full bg-dark-900 border border-dark-700 rounded-lg pl-9 pr-3 py-2 text-sm text-gray-200 focus:border-primary-500 focus:outline-none placeholder-gray-500"
          />
        </div>
      </div>

      {/* Template list */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {loading && (
          <div className="text-center py-8 text-xs text-gray-500">Loading templates…</div>
        )}
        {!loading && filtered.length === 0 && (
          <div className="text-center py-8 text-xs text-gray-500">
            {search ? 'No templates match your search.' : `No templates available for ${dimLabel}.`}
          </div>
        )}
        {filtered.map(t => (
          <div
            key={t.id}
            className="p-3 bg-dark-900 border border-dark-700 rounded-lg hover:border-primary-500/30 transition-colors"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <h4 className="text-sm font-medium text-gray-200 truncate">{t.name}</h4>
                <p className="text-xs text-gray-500 mt-1 line-clamp-2">{t.description}</p>
              </div>
              <button
                onClick={() => onApply(t)}
                className="flex-shrink-0 px-3 py-1.5 bg-primary-600 hover:bg-primary-500 text-white text-xs rounded-lg transition-colors"
              >
                Apply
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
