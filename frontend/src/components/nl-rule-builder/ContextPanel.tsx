import type { NLRuleDraft } from '@/types/nlRuleBuilder'

interface Dataset {
  id: string
  name: string
  dataset_id?: string
  data_source_name?: string
}

interface ContextPanelProps {
  draft: NLRuleDraft
  onChange: (partial: Partial<NLRuleDraft>) => void
  datasets: Dataset[]
}

export default function ContextPanel({ draft, onChange, datasets }: ContextPanelProps) {
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-gray-100">Context (optional)</h3>

      {/* Dataset selector */}
      <div>
        <label htmlFor="dataset-select" className="block text-xs font-medium text-gray-400 mb-1">
          Dataset
        </label>
        <select
          id="dataset-select"
          data-testid="nl-dataset-select"
          value={draft.dataset_id}
          onChange={(e) => onChange({ dataset_id: e.target.value })}
          className="input text-sm w-full"
        >
          <option value="">— Select dataset —</option>
          {datasets.map((ds) => (
            <option key={ds.id || ds.dataset_id} value={ds.id || ds.dataset_id}>
              {ds.data_source_name ? `${ds.data_source_name}.${ds.name}` : ds.name}
            </option>
          ))}
        </select>
      </div>

      {/* Domain */}
      <div>
        <label htmlFor="domain-input" className="block text-xs font-medium text-gray-400 mb-1">
          Business Domain
        </label>
        <input
          id="domain-input"
          type="text"
          value={draft.domain}
          onChange={(e) => onChange({ domain: e.target.value })}
          className="input text-sm w-full"
          placeholder="e.g., Finance, HR, Supply Chain"
        />
      </div>

      {/* Use column context toggle */}
      <div className="flex items-center gap-2">
        <input
          id="use-context"
          type="checkbox"
          checked={draft.use_context}
          onChange={(e) => onChange({ use_context: e.target.checked })}
          className="h-4 w-4 rounded border-dark-600 text-primary-600 focus:ring-primary-500"
        />
        <label htmlFor="use-context" className="text-xs text-gray-400">
          Use column context from selected dataset
        </label>
      </div>

      {/* Severity */}
      <div>
        <label htmlFor="severity-select" className="block text-xs font-medium text-gray-400 mb-1">
          Severity
        </label>
        <select
          id="severity-select"
          value={draft.severity}
          onChange={(e) => onChange({ severity: e.target.value as NLRuleDraft['severity'] })}
          className="input text-sm w-full"
        >
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
          <option value="info">Info</option>
        </select>
      </div>

      {/* Tags */}
      <div>
        <label htmlFor="tags-input" className="block text-xs font-medium text-gray-400 mb-1">
          Tags
        </label>
        <TagInput
          tags={draft.tags}
          onChange={(tags) => onChange({ tags })}
          maxTags={10}
          maxLength={50}
        />
      </div>
    </div>
  )
}

// Inline minimal tag input (avoids import dependency on flow-builder shared)
interface TagInputProps {
  tags: string[]
  onChange: (tags: string[]) => void
  maxTags: number
  maxLength: number
}

function TagInput({ tags, onChange, maxTags, maxLength }: TagInputProps) {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      const input = e.currentTarget
      const value = input.value.trim()
      if (value && tags.length < maxTags && value.length <= maxLength && !tags.includes(value)) {
        onChange([...tags, value])
        input.value = ''
      }
    }
  }

  const removeTag = (index: number) => {
    onChange(tags.filter((_, i) => i !== index))
  }

  return (
    <div>
      <div className="flex flex-wrap gap-1 mb-2">
        {tags.map((tag, idx) => (
          <span
            key={idx}
            className="inline-flex items-center gap-1 px-2 py-0.5 bg-primary-50 text-primary-700 text-xs rounded-full"
          >
            {tag}
            <button
              onClick={() => removeTag(idx)}
              className="text-primary-400 hover:text-primary-700"
              aria-label={`Remove tag ${tag}`}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      {tags.length < maxTags && (
        <input
          id="tags-input"
          type="text"
          onKeyDown={handleKeyDown}
          className="input text-sm w-full"
          placeholder="Type and press Enter to add a tag"
          maxLength={maxLength}
        />
      )}
      <p className="text-xs text-gray-400 mt-1">{tags.length}/{maxTags} tags</p>
    </div>
  )
}
