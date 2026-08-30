/**
 * F3 — Compound rule obligation breakdown.
 *
 * Renders each atomic SIR in a compound parsed_rule as an expandable card so
 * users can inspect operator/object/conditions/threshold per obligation
 * before continuing to flow generation.
 */
import { useState } from 'react'
import { ChevronRight, ChevronDown, GitBranch } from 'lucide-react'
import type { StructuredIntermediateRepresentation } from '@/types/nlRuleBuilder'

interface ObligationsBreakdownPanelProps {
  parsedRule: StructuredIntermediateRepresentation
}

const LOGIC_BADGE: Record<string, string> = {
  AND: 'bg-blue-900/40 text-blue-300 border-blue-700',
  OR: 'bg-purple-900/40 text-purple-300 border-purple-700',
  INDEPENDENT: 'bg-gray-800 text-gray-400 border-gray-700',
}

function ObligationCard({
  obligation,
  index,
}: {
  obligation: StructuredIntermediateRepresentation
  index: number
}) {
  const [open, setOpen] = useState(false)
  const subject = obligation.subject?.raw_text ?? '(no subject)'
  const operator = obligation.operator ?? '—'
  const objectText = obligation.object?.raw_text ?? null
  const conditions = obligation.conditions ?? []
  const ruleType = obligation.rule_type ?? 'unknown'

  return (
    <li
      className="rounded border border-dark-700 bg-dark-900 text-xs"
      data-testid={`obligation-card-${index}`}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-dark-800 rounded"
      >
        {open ? (
          <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-gray-400" />
        )}
        <span className="text-[10px] uppercase tracking-wide text-gray-500 shrink-0">
          #{index + 1}
        </span>
        <span className="font-medium text-gray-100 truncate">{subject}</span>
        <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-gray-400">
          <span className="px-1.5 py-0.5 rounded border border-dark-700 bg-dark-800">
            {ruleType}
          </span>
        </span>
      </button>

      {open && (
        <div className="px-3 pb-3 pt-1 space-y-2 border-t border-dark-700">
          <Row label="Subject" value={subject} />
          <Row label="Operator" value={operator} />
          {objectText && <Row label="Object" value={objectText} />}
          {obligation.threshold_pass != null && (
            <Row label="Threshold pass" value={String(obligation.threshold_pass)} />
          )}
          {obligation.threshold_warn != null && (
            <Row label="Threshold warn" value={String(obligation.threshold_warn)} />
          )}
          {obligation.inline_severity && (
            <Row label="Severity" value={obligation.inline_severity} />
          )}
          {conditions.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">
                Conditions
              </div>
              <ul className="space-y-1">
                {conditions.map((c, i) => (
                  <li
                    key={i}
                    className="text-gray-300 font-mono text-[11px]"
                    data-testid={`obligation-${index}-condition-${i}`}
                  >
                    {c.field?.raw_text ?? '?'} {c.operator}{' '}
                    {c.value != null ? JSON.stringify(c.value) : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </li>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <span className="text-[10px] uppercase tracking-wide text-gray-500 w-24 shrink-0">
        {label}
      </span>
      <span className="text-gray-200 break-all">{value}</span>
    </div>
  )
}

export default function ObligationsBreakdownPanel({
  parsedRule,
}: ObligationsBreakdownPanelProps) {
  if (!parsedRule?.is_compound) return null
  const obligations = parsedRule.obligations ?? []
  if (obligations.length <= 1) return null
  const logic = parsedRule.obligation_logic ?? 'INDEPENDENT'
  const badgeClass = LOGIC_BADGE[logic] ?? LOGIC_BADGE.INDEPENDENT

  return (
    <div
      className="card border border-dark-700"
      data-testid="obligations-breakdown-panel"
    >
      <div className="flex items-center gap-2 mb-3">
        <GitBranch className="w-4 h-4 text-primary-400" />
        <h3 className="text-sm font-semibold text-gray-100">
          Obligation breakdown
        </h3>
        <span
          className={`ml-1 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide border ${badgeClass}`}
        >
          {logic}
        </span>
        <span className="ml-auto text-[11px] text-gray-500">
          {obligations.length} atomic checks
        </span>
      </div>
      <ol className="space-y-2">
        {obligations.map((ob, i) => (
          <ObligationCard key={i} obligation={ob} index={i} />
        ))}
      </ol>
      <p className="mt-3 text-[11px] text-gray-500">
        Each obligation becomes its own check in the generated flow. Use the
        SIR editor above to refine the parent rule, or rephrase your
        statement to split obligations differently.
      </p>
    </div>
  )
}
