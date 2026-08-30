import { useState } from 'react'
import { ChevronDown, ChevronUp, ShieldCheck, Lightbulb, Info } from 'lucide-react'
import type { ParseExplanationItem, ParseTrustSummary } from '@/types/nlRuleBuilder'

interface ExplainabilitySectionProps {
  items: ParseExplanationItem[]
  trustSummary?: ParseTrustSummary | null
}

const BAND_STYLES: Record<string, { badge: string; label: string }> = {
  high: { badge: 'bg-success-soft text-success ring-success/30', label: 'High confidence' },
  medium: { badge: 'bg-warning-soft text-warning ring-warning/30', label: 'Medium confidence' },
  low: { badge: 'bg-danger-soft text-danger ring-danger/30', label: 'Low confidence' },
}

function groupByTopic(items: ParseExplanationItem[]): Map<string, ParseExplanationItem[]> {
  const map = new Map<string, ParseExplanationItem[]>()
  for (const item of items) {
    const key = item.topic || 'other'
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(item)
  }
  return map
}

export default function ExplainabilitySection({ items, trustSummary }: ExplainabilitySectionProps) {
  const bandKey = trustSummary?.confidence_band ?? 'low'
  // Default expanded when low/medium confidence to surface the "why"
  const [collapsed, setCollapsed] = useState(bandKey === 'high')

  if ((!items || items.length === 0) && !trustSummary) return null

  const style = BAND_STYLES[bandKey] ?? BAND_STYLES.low
  const scorePct = trustSummary ? Math.round(trustSummary.confidence_score * 100) : null
  const grouped = groupByTopic(items ?? [])

  return (
    <div
      className="rounded-2xl border border-edge bg-surface-raised p-4 space-y-3"
      data-testid="explainability-section"
    >
      {/* Header row */}
      <button
        className="flex w-full items-center justify-between text-sm font-medium text-content"
        onClick={() => setCollapsed((v) => !v)}
        aria-expanded={!collapsed}
        data-testid="explainability-toggle"
      >
        <span className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-brand" />
          <span>Why this rule?</span>
          <span
            className={`ml-1 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ring-1 ring-inset ${style.badge}`}
            data-testid="trust-tier-badge"
          >
            {style.label}
            {scorePct !== null && ` · ${scorePct}%`}
          </span>
        </span>
        {collapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
      </button>

      {/* Expanded content */}
      {!collapsed && (
        <div className="space-y-4 pt-1" data-testid="explainability-body">
          {/* Recommendation */}
          {trustSummary?.recommendation ? (
            <div className="rounded-lg border border-brand/30 bg-brand-soft p-3 text-sm text-content">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-brand">
                <Lightbulb className="h-3.5 w-3.5" /> Recommendation
              </div>
              <p className="mt-1">{trustSummary.recommendation}</p>
            </div>
          ) : null}

          {/* Assumptions */}
          {trustSummary && trustSummary.assumptions.length > 0 && (
            <div data-testid="assumptions-list">
              <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-content-muted">
                <Info className="h-3.5 w-3.5" /> Assumptions
              </p>
              <ul className="ml-4 list-disc space-y-0.5 text-xs text-content-muted">
                {trustSummary.assumptions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Caveats */}
          {trustSummary && trustSummary.caveats.length > 0 && (
            <div data-testid="caveats-list">
              <p className="mb-1 text-xs font-semibold text-warning">Caveats</p>
              <ul className="ml-4 list-disc space-y-0.5 text-xs text-content-muted">
                {trustSummary.caveats.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Signals grouped by topic */}
          {grouped.size > 0 ? (
            <div className="space-y-3">
              {Array.from(grouped.entries()).map(([topic, entries]) => (
                <div key={topic} className="space-y-1.5">
                  <p className="text-xs font-semibold uppercase tracking-widest text-content-muted">
                    {topic.replace(/_/g, ' ')}
                  </p>
                  <div className="space-y-1.5">
                    {entries.map((item, idx) => (
                      <div
                        key={idx}
                        className="rounded-lg border border-edge bg-surface px-3 py-2 text-xs"
                        data-testid={`signal-entry-${topic}-${idx}`}
                      >
                        <span className="text-content">{item.decision}</span>
                        {item.evidence.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {item.evidence.map((ev, eidx) => (
                              <span
                                key={eidx}
                                className="rounded border border-edge bg-surface-raised px-1.5 py-0.5 text-content-muted"
                              >
                                {ev}
                              </span>
                            ))}
                          </div>
                        )}
                        {item.caveat && (
                          <p className="mt-1 italic text-warning">{item.caveat}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
