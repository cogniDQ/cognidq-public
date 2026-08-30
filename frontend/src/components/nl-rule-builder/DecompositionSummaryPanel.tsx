import type { DecompositionSummary } from '@/types/nlRuleBuilder'

interface DecompositionSummaryProps {
  summary: DecompositionSummary
}

const LOGIC_COLORS: Record<string, string> = {
  AND: 'bg-blue-100 text-blue-700',
  OR: 'bg-purple-100 text-purple-700',
  INDEPENDENT: 'bg-gray-100 text-gray-600',
}

export default function DecompositionSummaryPanel({ summary }: DecompositionSummaryProps) {
  if (!summary || summary.count <= 1) return null

  const logicColor = summary.logic ? (LOGIC_COLORS[summary.logic] ?? 'bg-gray-100 text-gray-600') : 'bg-gray-100 text-gray-600'
  const logicLabel = summary.logic ?? 'INDEPENDENT'

  return (
    <div
      className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 space-y-2"
      data-testid="decomposition-summary"
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-blue-800">
        <span>{summary.count} obligations detected</span>
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${logicColor}`}>
          {logicLabel}
        </span>
      </div>
      <ul className="pl-4 list-disc space-y-1 text-sm text-blue-700">
        {summary.obligations.map((ob, idx) => (
          <li key={idx}>{ob}</li>
        ))}
      </ul>
    </div>
  )
}
