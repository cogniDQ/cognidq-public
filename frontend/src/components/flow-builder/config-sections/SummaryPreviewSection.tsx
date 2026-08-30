/**
 * SummaryPreviewSection — Read-only human-readable check description.
 * Updates live as the user fills in the form.
 * Always visible for all check types.
 */
import type { BaseCheckConfig } from '../../../schemas/dq-checks/types'

interface SummaryPreviewSectionProps {
  dimension: string
  summaryText: string
  config: BaseCheckConfig & Record<string, unknown>
}

export function SummaryPreviewSection({ summaryText }: SummaryPreviewSectionProps) {
  if (!summaryText) return null

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Summary</h4>
      <div className="bg-dark-900/50 border border-dark-700 rounded-lg p-3">
        {summaryText.split('\n').map((line, i) => (
          <p key={i} className={`text-xs ${i === 0 ? 'text-gray-200 font-medium' : 'text-gray-400'}`}>
            {line}
          </p>
        ))}
      </div>
    </div>
  )
}
