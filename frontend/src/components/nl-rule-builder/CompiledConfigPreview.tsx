import type { CheckConfigOutput } from '@/types/nlRuleBuilder'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'

interface CompiledConfigPreviewProps {
  configs: CheckConfigOutput[]
}

const SEVERITY_STYLES: Record<string, string> = {
  critical: 'bg-red-900/30 text-red-400',
  high: 'bg-orange-900/30 text-orange-400',
  medium: 'bg-yellow-900/30 text-yellow-400',
  low: 'bg-blue-900/30 text-blue-400',
  info: 'bg-dark-700 text-gray-400',
}

export default function CompiledConfigPreview({ configs }: CompiledConfigPreviewProps) {
  if (!configs || configs.length === 0) {
    return (
      <div
        className="flex items-start gap-2 rounded-lg border border-yellow-800 bg-yellow-900/20 px-4 py-3 text-sm text-yellow-400"
        data-testid="compiled-config-empty"
      >
        <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
        <span>No check configurations were generated for this rule. Submission is disabled.</span>
      </div>
    )
  }

  return (
    <div className="space-y-3" data-testid="compiled-config-list">
      {configs.map((cfg, idx) => {
        const severityStyle = SEVERITY_STYLES[cfg.severity] ?? SEVERITY_STYLES.info
        return (
          <div
            key={idx}
            className="card space-y-2"
            data-testid={`config-card-${idx}`}
          >
            <div className="flex items-start justify-between gap-2">
              <span className="text-sm font-semibold text-gray-100 flex items-center gap-1">
                <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
                {cfg.rule_name}
              </span>
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${severityStyle}`}>
                {cfg.severity}
              </span>
            </div>

            <div className="flex flex-wrap gap-2 text-xs">
              <span className="bg-dark-700 text-gray-400 px-2 py-0.5 rounded">
                {cfg.check_dimension}
              </span>
              <span className="bg-dark-700 text-gray-400 px-2 py-0.5 rounded">
                {cfg.check_subtype}
              </span>
              {cfg.columns.map((col, cidx) => (
                <span key={cidx} className="bg-primary-900/30 text-primary-400 px-2 py-0.5 rounded">
                  {col}
                </span>
              ))}
            </div>

            {cfg.thresholds && (
              <div className="text-xs text-gray-400 flex gap-3">
                <span>Pass ≥ {cfg.thresholds.threshold_pass}%</span>
                <span>Warn ≥ {cfg.thresholds.threshold_warn}%</span>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
