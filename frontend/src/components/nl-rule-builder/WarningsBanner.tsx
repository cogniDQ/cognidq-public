import { useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react'

interface WarningsBannerProps {
  warnings: string[]
}

export default function WarningsBanner({ warnings }: WarningsBannerProps) {
  const [collapsed, setCollapsed] = useState(false)

  if (!warnings || warnings.length === 0) return null

  return (
    <div
      className="rounded-lg border border-yellow-300 bg-yellow-50 px-4 py-3"
      role="alert"
      data-testid="warnings-banner"
    >
      <button
        className="flex w-full items-center justify-between text-sm font-medium text-yellow-800"
        onClick={() => setCollapsed((v) => !v)}
        aria-expanded={!collapsed}
      >
        <span className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {warnings.length} parse {warnings.length === 1 ? 'warning' : 'warnings'}
        </span>
        {collapsed ? (
          <ChevronDown className="w-4 h-4" />
        ) : (
          <ChevronUp className="w-4 h-4" />
        )}
      </button>

      {!collapsed && (
        <ul
          className="mt-2 space-y-1 pl-6 list-disc text-sm text-yellow-700"
          data-testid="warnings-list"
        >
          {warnings.map((w, idx) => (
            <li key={idx}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
