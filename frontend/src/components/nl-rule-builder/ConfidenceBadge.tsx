interface ConfidenceBadgeProps {
  confidence: number
}

export default function ConfidenceBadge({ confidence }: ConfidenceBadgeProps) {
  const pct = Math.round(confidence * 100)
  const color =
    confidence >= 0.9
      ? 'bg-green-500'
      : confidence >= 0.7
        ? 'bg-yellow-500'
        : 'bg-red-500'
  const textColor =
    confidence >= 0.9
      ? 'text-green-400'
      : confidence >= 0.7
        ? 'text-yellow-400'
        : 'text-red-400'
  const label =
    confidence >= 0.9
      ? 'High'
      : confidence >= 0.7
        ? 'Medium'
        : 'Low'

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 bg-dark-700 rounded-full h-2">
        <div
          className={`${color} h-2 rounded-full transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`text-sm font-semibold ${textColor}`}>
        {pct}%
      </span>
      <span className={`text-xs px-2 py-0.5 rounded-full ${color}/20 ${textColor} font-medium`}>
        {label}
      </span>
    </div>
  )
}
