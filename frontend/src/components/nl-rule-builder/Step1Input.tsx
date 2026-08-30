import { Loader2, Sparkles, ChevronDown, ChevronUp, AlertCircle } from 'lucide-react'
import type { NLRuleDraft, RecentParseEntry } from '@/types/nlRuleBuilder'
import RuleTextInput from './RuleTextInput'
import ContextPanel from './ContextPanel'
import ExampleSuggestions from './ExampleSuggestions'
import RecentParses from './RecentParses'
import { useState } from 'react'

interface Dataset {
  id: string
  name: string
  dataset_id?: string
  data_source_name?: string
}

interface SavedParseEntry {
  request_id: string
  rule_text: string
  rule_type: string
  confidence: number
  status: string
  validated: boolean
  created_at: string
}

interface Step1InputProps {
  draft: NLRuleDraft
  onDraftChange: (partial: Partial<NLRuleDraft>) => void
  onParse: () => void
  isParseLoading: boolean
  parseError: Error | null
  datasets: Dataset[]
  history: RecentParseEntry[]
  savedParses?: { items: SavedParseEntry[] } | undefined
}

export default function Step1Input({
  draft,
  onDraftChange,
  onParse,
  isParseLoading,
  parseError,
  datasets,
  history,
  savedParses,
}: Step1InputProps) {
  const [historyOpen, setHistoryOpen] = useState(false)

  // Spec §4.3 / §17 — dataset is mandatory before parsing.
  const hasDataset = Boolean((draft.dataset_id ?? '').trim().length > 0)
  const canParse = draft.rule_text.trim().length > 0 && hasDataset && !isParseLoading

  return (
    <div className="space-y-6">
      {/* Rule text */}
      <div className="card">
        <RuleTextInput
          value={draft.rule_text}
          onChange={(val) => onDraftChange({ rule_text: val })}
          maxLength={500}
        />
      </div>

      {/* Examples */}
      <ExampleSuggestions
        onSelect={(text) => onDraftChange({ rule_text: text })}
      />

      {/* Context */}
      <div className="card">
        <ContextPanel
          draft={draft}
          onChange={onDraftChange}
          datasets={datasets}
        />
      </div>

      {/* Parse error inline */}
      {parseError && (
        <div
          className="flex items-start gap-2 rounded-lg border border-red-800 bg-dark-800 px-4 py-3 text-sm text-red-400"
          role="alert"
          data-testid="parse-error-banner"
        >
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{parseError.message}</span>
        </div>
      )}

      {/* Dataset required notice */}
      {!hasDataset && draft.rule_text.trim().length > 0 && (
        <div
          className="flex items-start gap-2 rounded-lg border border-amber-800 bg-dark-800 px-4 py-3 text-sm text-amber-400"
          role="status"
          data-testid="dataset-required-banner"
        >
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>Please select a dataset before interpreting the rule.</span>
        </div>
      )}

      {/* Interpret Rule button */}
      <button
        onClick={onParse}
        disabled={!canParse}
        className="btn btn-primary w-full flex items-center justify-center gap-2"
        data-testid="interpret-btn"
      >
        {isParseLoading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Sparkles className="w-4 h-4" />
        )}
        <span>Interpret Rule</span>
      </button>

      {/* Recent parses (collapsible) */}
      {(history.length > 0 || (savedParses?.items?.length ?? 0) > 0) && (
        <div className="card">
          <button
            className="flex w-full items-center justify-between text-sm font-medium text-gray-300"
            onClick={() => setHistoryOpen((v) => !v)}
            aria-expanded={historyOpen}
          >
            <span>Recent Parses</span>
            {historyOpen ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>
          {historyOpen && (
            <div className="mt-3">
              <RecentParses
                entries={history}
                savedEntries={savedParses?.items}
                onRestore={(text) => onDraftChange({ rule_text: text })}
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
