// F031 P05 — SeverityBadge component

import type { IssueSeverity } from '../../types/issue'

const SEVERITY_STYLES: Record<IssueSeverity, string> = {
  critical: 'text-red-400 bg-red-400/10 border-red-400/30',
  major: 'text-orange-400 bg-orange-400/10 border-orange-400/30',
  minor: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30',
  informational: 'text-blue-400 bg-blue-400/10 border-blue-400/30',
}

interface SeverityBadgeProps {
  severity: IssueSeverity
}

export default function SeverityBadge({ severity }: SeverityBadgeProps) {
  const style = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.informational
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${style}`}
      data-testid="severity-badge"
    >
      {severity}
    </span>
  )
}
