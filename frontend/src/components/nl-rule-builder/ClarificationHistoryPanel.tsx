/**
 * F1 — Multi-turn clarification history panel.
 *
 * Read-only chronological list of prior Q/A pairs the user has resolved with
 * the parser during the current session. Surfaces directly above the active
 * ClarificationPanel so users see what the parser already knows.
 */
import type { ClarificationTurn } from '@/types/nlRuleBuilder'
import { History, MessageSquare, CheckCircle2 } from 'lucide-react'

interface ClarificationHistoryPanelProps {
  turns: ClarificationTurn[]
}

export default function ClarificationHistoryPanel({
  turns,
}: ClarificationHistoryPanelProps) {
  if (!turns || turns.length === 0) return null

  return (
    <div
      className="card border border-dark-700"
      data-testid="clarification-history-panel"
    >
      <div className="flex items-center gap-2 mb-3">
        <History className="w-4 h-4 text-primary-400" />
        <h3 className="text-sm font-semibold text-gray-100">
          Clarification history
        </h3>
        <span className="text-[11px] uppercase tracking-wide text-gray-500">
          {turns.length} {turns.length === 1 ? 'turn' : 'turns'}
        </span>
      </div>
      <ol className="space-y-2">
        {turns.map((t, i) => (
          <li
            key={`${t.field}-${i}`}
            className="rounded border border-dark-700 bg-dark-900 px-3 py-2 text-xs text-gray-300"
            data-testid={`clarification-turn-${i}`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] uppercase tracking-wide text-gray-500">
                Turn {i + 1} · {t.field}
              </span>
              {t.answered_at && (
                <span className="text-[10px] text-gray-500">
                  {new Date(t.answered_at).toLocaleString()}
                </span>
              )}
            </div>
            <div className="flex items-start gap-2">
              <MessageSquare className="w-3.5 h-3.5 mt-0.5 text-gray-500 shrink-0" />
              <span className="text-gray-300">{t.question}</span>
            </div>
            <div className="flex items-start gap-2 mt-1">
              <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 text-green-500 shrink-0" />
              <span className="text-gray-100 font-medium">{t.answer}</span>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
