import { useMemo, useState } from 'react'
import { MessageCircle, Loader2, HelpCircle } from 'lucide-react'
import type { ClarifyingQuestion, ClarifyingAnswerType } from '@/types/nlRuleBuilder'

interface ClarificationPanelProps {
  questions: ClarifyingQuestion[]
  context?: string | null
  onSubmit: (answers: Record<string, string>) => void
  isSubmitting: boolean
}

/**
 * E1 — typed clarifying questions.
 *
 * answer_type drives the input control:
 *  - single_select  → chip group, single value
 *  - multi_select   → chip group, comma-joined values
 *  - free_text      → text input
 *  - numeric        → number input (honours min_value / max_value)
 *
 * For backwards compatibility, when answer_type is missing we infer:
 *  options.length > 0 → single_select, else free_text.
 */

function inferAnswerType(q: ClarifyingQuestion): ClarifyingAnswerType {
  if (q.answer_type) return q.answer_type
  if (q.options && q.options.length > 0) return 'single_select'
  return 'free_text'
}

function isAnswered(q: ClarifyingQuestion, value: string): boolean {
  const trimmed = (value ?? '').trim()
  if (trimmed.length === 0) return false
  if (inferAnswerType(q) === 'numeric') {
    const n = Number(trimmed)
    if (Number.isNaN(n)) return false
    if (q.min_value != null && n < q.min_value) return false
    if (q.max_value != null && n > q.max_value) return false
  }
  return true
}

export default function ClarificationPanel({
  questions,
  context,
  onSubmit,
  isSubmitting,
}: ClarificationPanelProps) {
  const [answers, setAnswers] = useState<Record<string, string>>(() =>
    Object.fromEntries(questions.map((q) => [q.field, '']))
  )

  const canSubmit = useMemo(
    () => questions.filter((q) => q.required).every((q) => isAnswered(q, answers[q.field] ?? '')),
    [questions, answers],
  )

  // F2 — partial accept: count how many questions have valid answers, regardless of required
  const answeredCount = useMemo(
    () => questions.filter((q) => isAnswered(q, answers[q.field] ?? '')).length,
    [questions, answers],
  )
  const canSubmitPartial = answeredCount > 0 && answeredCount < questions.length

  function setAnswer(field: string, value: string) {
    setAnswers((prev) => ({ ...prev, [field]: value }))
  }

  function toggleMulti(field: string, opt: string) {
    setAnswers((prev) => {
      const current = (prev[field] ?? '').split(',').map((s) => s.trim()).filter(Boolean)
      const next = current.includes(opt)
        ? current.filter((x) => x !== opt)
        : [...current, opt]
      return { ...prev, [field]: next.join(', ') }
    })
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (canSubmit && !isSubmitting) {
      onSubmit(answers)
    }
  }

  // F2 — submit only the questions that have valid answers; defer the rest
  function handleSubmitPartial() {
    if (isSubmitting) return
    const partial: Record<string, string> = {}
    for (const q of questions) {
      const v = answers[q.field] ?? ''
      if (isAnswered(q, v)) partial[q.field] = v
    }
    if (Object.keys(partial).length > 0) {
      onSubmit(partial)
    }
  }

  return (
    <div
      className="rounded-lg border border-orange-800 bg-dark-800 px-4 py-4 space-y-4"
      data-testid="clarification-panel"
    >
      <div className="flex items-start gap-2">
        <MessageCircle className="w-5 h-5 text-orange-600 shrink-0 mt-0.5" />
        <div>
          <h4 className="text-sm font-semibold text-orange-400">Clarification Needed</h4>
          {context && (
            <p className="text-xs text-orange-400 mt-0.5" data-testid="clarification-context">
              {context}
            </p>
          )}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {questions.map((q, idx) => {
          const answerType = inferAnswerType(q)
          const value = answers[q.field] ?? ''
          const selectedMulti = value.split(',').map((s) => s.trim()).filter(Boolean)

          return (
            <div key={`${q.field}-${idx}`} className="space-y-1">
              <label
                htmlFor={`clarify-${q.field}`}
                className="block text-sm font-medium text-orange-400"
              >
                {q.question}
                {q.required && <span className="text-red-500 ml-1">*</span>}
                <span
                  className="ml-2 inline-block px-1.5 py-0.5 text-[10px] uppercase tracking-wide rounded border border-orange-800/60 text-orange-300/80"
                  data-testid={`clarify-type-${idx}`}
                >
                  {answerType.replace('_', ' ')}
                </span>
              </label>

              {q.rationale && (
                <p
                  className="flex items-start gap-1 text-[11px] text-orange-300/70"
                  data-testid={`clarify-rationale-${idx}`}
                >
                  <HelpCircle className="w-3 h-3 mt-0.5 shrink-0" />
                  <span>{q.rationale}</span>
                </p>
              )}

              {answerType === 'single_select' && (
                <div className="flex flex-wrap gap-2" data-testid={`clarify-options-${idx}`}>
                  {(q.options ?? []).map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => setAnswer(q.field, opt)}
                      className={[
                        'px-3 py-1.5 rounded-full text-xs font-medium border transition-colors',
                        value === opt
                          ? 'bg-orange-600 text-white border-orange-600'
                          : 'bg-dark-700 text-orange-400 border-orange-700 hover:bg-dark-600',
                      ].join(' ')}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              )}

              {answerType === 'multi_select' && (
                <div
                  className="flex flex-wrap gap-2"
                  data-testid={`clarify-multi-options-${idx}`}
                  role="group"
                  aria-label={q.question}
                >
                  {(q.options ?? []).map((opt) => {
                    const checked = selectedMulti.includes(opt)
                    return (
                      <button
                        key={opt}
                        type="button"
                        aria-pressed={checked}
                        onClick={() => toggleMulti(q.field, opt)}
                        className={[
                          'px-3 py-1.5 rounded-full text-xs font-medium border transition-colors',
                          checked
                            ? 'bg-orange-600 text-white border-orange-600'
                            : 'bg-dark-700 text-orange-400 border-orange-700 hover:bg-dark-600',
                        ].join(' ')}
                      >
                        {checked ? '✓ ' : ''}
                        {opt}
                      </button>
                    )
                  })}
                </div>
              )}

              {answerType === 'numeric' && (
                <input
                  id={`clarify-${q.field}`}
                  data-testid={`clarify-input-${idx}`}
                  type="number"
                  step="any"
                  min={q.min_value ?? undefined}
                  max={q.max_value ?? undefined}
                  value={value}
                  onChange={(e) => setAnswer(q.field, e.target.value)}
                  className="input text-sm w-full"
                  placeholder={
                    q.min_value != null || q.max_value != null
                      ? `Number${q.min_value != null ? ` ≥ ${q.min_value}` : ''}${
                          q.max_value != null ? ` ≤ ${q.max_value}` : ''
                        }`
                      : 'Numeric answer'
                  }
                />
              )}

              {answerType === 'free_text' && (
                <input
                  id={`clarify-${q.field}`}
                  data-testid={`clarify-input-${idx}`}
                  type="text"
                  value={value}
                  onChange={(e) => setAnswer(q.field, e.target.value)}
                  className="input text-sm w-full"
                  placeholder={`Answer for: ${q.question}`}
                />
              )}
            </div>
          )
        })}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={!canSubmit || isSubmitting}
            className="btn btn-primary flex items-center gap-2"
            data-testid="submit-answers-btn"
          >
            {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
            Submit Answers
          </button>

          {/* F2 — partial accept */}
          <button
            type="button"
            onClick={handleSubmitPartial}
            disabled={!canSubmitPartial || isSubmitting}
            className="btn btn-secondary flex items-center gap-2"
            data-testid="submit-partial-btn"
            title="Send the answers you've completed and let the parser ask the rest later"
          >
            Submit answered ({answeredCount}/{questions.length})
          </button>

          {canSubmitPartial && (
            <span className="text-[11px] text-orange-300/70">
              Defer the remaining {questions.length - answeredCount} for the next turn.
            </span>
          )}
        </div>
      </form>
    </div>
  )
}
