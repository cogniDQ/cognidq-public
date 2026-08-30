import { useState } from 'react'
import { AlertCircle, CheckCircle2, Loader2, AlertTriangle, Workflow, HelpCircle, Send } from 'lucide-react'
import type { ParseRuleResponse, ClarifyingQuestion } from '@/types/nlRuleBuilder'
import ConfidenceBadge from './ConfidenceBadge'

interface ParseResultPanelProps {
  result: ParseRuleResponse | null
  isPending: boolean
  error: Error | null
  onValidate?: (validated: boolean, adjustments?: Record<string, unknown>) => void
  onCreateFlow?: () => void
  isCreatingFlow?: boolean
  isValidated?: boolean
  onClarify?: (answers: Record<string, string>) => void
  isClarifying?: boolean
  /** Opens the full parse result modal */
  onOpenModal?: () => void
}

export default function ParseResultPanel({ result, isPending, error, onValidate: _onValidate, onCreateFlow, isCreatingFlow, isValidated, onClarify, isClarifying, onOpenModal }: ParseResultPanelProps) {
  if (isPending) {
    return (
      <div className="card flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
        <span className="ml-3 text-gray-500">Interpreting your rule...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card border-red-800 bg-red-900/20">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-500 mt-0.5 shrink-0" />
          <div>
            <h3 className="text-sm font-semibold text-red-400">Parse Error</h3>
            <p className="text-sm text-red-400 mt-1">{error.message}</p>
          </div>
        </div>
      </div>
    )
  }

  if (!result) {
    return (
      <div className="card text-center py-12 text-gray-400">
        <p className="text-sm">Enter a business rule and click "Interpret Rule" to see the result.</p>
      </div>
    )
  }

  if ((result.status !== 'parsed' && result.status !== 'needs_clarification') || !result.parsed_rule) {
    return (
      <div className="card border-yellow-800 bg-yellow-900/20">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-yellow-500 mt-0.5 shrink-0" />
          <div>
            <h3 className="text-sm font-semibold text-yellow-400">
              {result.status === 'cannot_interpret' ? 'Could Not Interpret' : 'Parse Error'}
            </h3>
            {result.reason && <p className="text-sm text-yellow-300 mt-1">{result.reason}</p>}
            {result.suggestions.length > 0 && (
              <ul className="mt-2 space-y-1">
                {result.suggestions.map((s, idx) => (
                  <li key={idx} className="text-xs text-yellow-300">• {s}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    )
  }

  const sir = result.parsed_rule
  const warnings = sir.parse_warnings || []

  // needs_clarification: show inline Q&A only
  if (result.status === 'needs_clarification') {
    return (
      <div className="space-y-4">
        {(result.clarifying_questions?.length ?? 0) > 0 && onClarify ? (
          <ClarifyingQuestionsPanel
            questions={result.clarifying_questions!}
            context={result.clarification_context ?? null}
            onSubmit={onClarify}
            isSubmitting={!!isClarifying}
          />
        ) : (
          <div className="card border-blue-800 bg-blue-900/20">
            <div className="flex items-start gap-3">
              <HelpCircle className="w-5 h-5 text-blue-500 mt-0.5 shrink-0" />
              <div>
                <h3 className="text-sm font-semibold text-blue-400">Clarification Needed</h3>
                {result.reason && <p className="text-sm text-blue-300 mt-1">{result.reason}</p>}
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  // parsed: compact summary — full detail is in the modal
  return (
    <div className="card space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <CheckCircle2 className="w-5 h-5 text-green-500" />
        <h3 className="font-semibold text-gray-100">Rule Parsed</h3>
        <ConfidenceBadge confidence={sir.confidence} />
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="bg-dark-800/50 rounded-lg px-3 py-2 border border-dark-700">
          <p className="text-xs text-gray-400 font-medium uppercase mb-0.5">Rule Type</p>
          <span className="px-2 py-0.5 bg-primary-900/30 text-primary-400 rounded text-xs font-semibold">
            {sir.rule_type.replace(/_/g, ' ')}
          </span>
        </div>
        <div className="bg-dark-800/50 rounded-lg px-3 py-2 border border-dark-700">
          <p className="text-xs text-gray-400 font-medium uppercase mb-0.5">Datasets</p>
          <p className="text-gray-200 font-medium">
            {(result.detected_datasets?.length ?? 0) === 0
              ? <span className="text-gray-400">—</span>
              : `${result.detected_datasets!.length} matched`}
          </p>
        </div>
        <div className="bg-dark-800/50 rounded-lg px-3 py-2 border border-dark-700">
          <p className="text-xs text-gray-400 font-medium uppercase mb-0.5">Columns</p>
          <p className="text-gray-200 font-medium">
            {(result.detected_columns?.length ?? 0) === 0
              ? <span className="text-gray-400">—</span>
              : `${result.detected_columns!.length} detected`}
          </p>
        </div>
        <div className="bg-dark-800/50 rounded-lg px-3 py-2 border border-dark-700">
          <p className="text-xs text-gray-400 font-medium uppercase mb-0.5">Checks</p>
          <p className="text-gray-200 font-medium">
            {(result.check_configs?.length ?? 0) === 0
              ? <span className="text-gray-400">—</span>
              : `${result.check_configs!.length} configured`}
          </p>
        </div>
      </div>

      {/* Warnings pill */}
      {warnings.length > 0 && (
        <div className="flex items-center gap-2 px-3 py-2 bg-yellow-900/20 border border-yellow-800 rounded-lg text-xs text-yellow-400">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          {warnings.length} parser warning{warnings.length !== 1 ? 's' : ''} — see details
        </div>
      )}

      {/* Open modal button */}
      {onOpenModal && (
        <button
          onClick={onOpenModal}
          className="btn btn-primary w-full flex items-center justify-center gap-2"
        >
          <CheckCircle2 className="w-4 h-4" />
          Review &amp; Configure →
        </button>
      )}

      {/* Transform to DQ Flow — only after proposal submitted */}
      {isValidated && onCreateFlow && (
        <button
          onClick={onCreateFlow}
          disabled={isCreatingFlow}
          className="btn w-full flex items-center justify-center gap-2 text-sm bg-emerald-600 hover:bg-emerald-700 text-white"
        >
          {isCreatingFlow ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Workflow className="w-4 h-4" />
          )}
          <span>{isCreatingFlow ? 'Creating Flow…' : 'Transform to DQ Flow'}</span>
        </button>
      )}
    </div>
  )
}

function ClarifyingQuestionsPanel({
  questions,
  context,
  onSubmit,
  isSubmitting,
}: {
  questions: ClarifyingQuestion[]
  context: string | null
  onSubmit: (answers: Record<string, string>) => void
  isSubmitting: boolean
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({})

  const allRequiredAnswered = questions
    .filter(q => q.required)
    .every(q => answers[q.field]?.trim())

  const handleSubmit = () => {
    if (allRequiredAnswered) {
      onSubmit(answers)
    }
  }

  const isRetry = !!context

  return (
    <div className={`card space-y-4 ${isRetry ? 'border-amber-700 bg-amber-900/20' : 'border-blue-800 bg-blue-900/20'}`}>
      {/* Retry context — shows what the parser tried */}
      {isRetry && (
        <div className="flex items-start gap-2 bg-amber-900/30 rounded-lg p-3 border border-amber-700">
          <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-amber-300">Your previous answers didn't fully resolve</p>
            <p className="text-xs text-amber-400 mt-1">{context}</p>
          </div>
        </div>
      )}

      <div className="flex items-start gap-2">
        <HelpCircle className={`w-5 h-5 mt-0.5 shrink-0 ${isRetry ? 'text-amber-400' : 'text-blue-400'}`} />
        <div>
          <h3 className={`text-sm font-semibold ${isRetry ? 'text-amber-300' : 'text-blue-300'}`}>
            {isRetry ? 'Follow-up Questions' : 'Clarification Needed'}
          </h3>
          <p className={`text-xs mt-1 ${isRetry ? 'text-amber-400' : 'text-blue-400'}`}>
            {isRetry
              ? 'Please review the updated questions below and try again.'
              : 'Please answer the following questions so the parser can accurately interpret your rule.'
            }
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {questions.map((q, idx) => {
          // E1 — typed clarifying questions: derive answer_type for each q.
          const answerType =
            q.answer_type ?? (q.options && q.options.length > 0 ? 'single_select' : 'free_text')
          const value = answers[q.field] ?? ''
          const selectedMulti = value.split(',').map((s) => s.trim()).filter(Boolean)
          return (
          <div key={idx} className="bg-dark-800 rounded-lg p-3 border border-dark-700 space-y-2">
            <label className="text-sm font-medium text-gray-200 flex items-center gap-1">
              {q.question}
              {q.required && <span className="text-red-500 text-xs">*</span>}
              <span className="ml-2 inline-block px-1.5 py-0.5 text-[10px] uppercase tracking-wide rounded border border-dark-600 text-gray-400">
                {answerType.replace('_', ' ')}
              </span>
            </label>
            {q.rationale && (
              <p className="text-[11px] text-gray-400">{q.rationale}</p>
            )}

            {answerType === 'single_select' && q.options.length > 0 && (
              <div className="space-y-1">
                {q.options.map((opt) => (
                  <label
                    key={opt}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded cursor-pointer text-sm transition-colors ${
                      answers[q.field] === opt
                        ? 'bg-primary-900/30 text-primary-400 border border-primary-700'
                        : 'bg-dark-700 text-gray-300 border border-dark-600 hover:bg-dark-600'
                    }`}
                  >
                    <input
                      type="radio"
                      name={`clarify-${q.field}`}
                      value={opt}
                      checked={answers[q.field] === opt}
                      onChange={() => setAnswers(prev => ({ ...prev, [q.field]: opt }))}
                      className="sr-only"
                    />
                    {opt}
                  </label>
                ))}
                <input
                  type="text"
                  placeholder="Or type a custom answer..."
                  value={q.options.includes(answers[q.field] ?? '') ? '' : (answers[q.field] ?? '')}
                  onChange={(e) => setAnswers(prev => ({ ...prev, [q.field]: e.target.value }))}
                  className="w-full mt-1 text-sm border border-dark-600 rounded px-2 py-1 bg-dark-800 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-primary-400"
                />
              </div>
            )}

            {answerType === 'multi_select' && (
              <div className="space-y-1">
                {(q.options ?? []).map((opt) => {
                  const checked = selectedMulti.includes(opt)
                  return (
                    <label
                      key={opt}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded cursor-pointer text-sm transition-colors ${
                        checked
                          ? 'bg-primary-900/30 text-primary-400 border border-primary-700'
                          : 'bg-dark-700 text-gray-300 border border-dark-600 hover:bg-dark-600'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          const next = checked
                            ? selectedMulti.filter((x) => x !== opt)
                            : [...selectedMulti, opt]
                          setAnswers(prev => ({ ...prev, [q.field]: next.join(', ') }))
                        }}
                        className="accent-primary-500"
                      />
                      {opt}
                    </label>
                  )
                })}
              </div>
            )}

            {answerType === 'numeric' && (
              <input
                type="number"
                step="any"
                min={q.min_value ?? undefined}
                max={q.max_value ?? undefined}
                placeholder={
                  q.min_value != null || q.max_value != null
                    ? `Number${q.min_value != null ? ` ≥ ${q.min_value}` : ''}${q.max_value != null ? ` ≤ ${q.max_value}` : ''}`
                    : 'Numeric answer'
                }
                value={answers[q.field] ?? ''}
                onChange={(e) => setAnswers(prev => ({ ...prev, [q.field]: e.target.value }))}
                className="w-full text-sm border border-dark-600 rounded px-2 py-1 bg-dark-800 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-primary-400"
              />
            )}

            {answerType === 'free_text' && (
              <input
                type="text"
                placeholder="Type your answer..."
                value={answers[q.field] ?? ''}
                onChange={(e) => setAnswers(prev => ({ ...prev, [q.field]: e.target.value }))}
                className="w-full text-sm border border-dark-600 rounded px-2 py-1 bg-dark-800 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-primary-400"
              />
            )}
          </div>
          )
        })}
      </div>

      <button
        onClick={handleSubmit}
        disabled={!allRequiredAnswered || isSubmitting}
        className="btn btn-primary w-full flex items-center justify-center gap-2 text-sm"
      >
        {isSubmitting ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Send className="w-4 h-4" />
        )}
        <span>{isSubmitting ? 'Re-parsing...' : 'Submit Answers & Re-parse'}</span>
      </button>
    </div>
  )
}
