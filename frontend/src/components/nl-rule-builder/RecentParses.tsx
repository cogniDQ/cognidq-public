import { useState } from 'react'
import { ChevronDown, ChevronRight, Clock, CheckCircle2, XCircle } from 'lucide-react'
import type { RecentParseEntry, SavedParseEntry } from '@/types/nlRuleBuilder'

interface RecentParsesProps {
  entries: RecentParseEntry[]
  savedEntries?: SavedParseEntry[]
  onRestore: (ruleText: string) => void
}

export default function RecentParses({ entries, savedEntries, onRestore }: RecentParsesProps) {
  const [collapsed, setCollapsed] = useState(false)

  // Prefer DB-backed saved entries, fall back to localStorage entries
  const useSaved = savedEntries && savedEntries.length > 0
  const count = useSaved ? savedEntries!.length : entries.length

  if (count === 0) return null

  return (
    <div className="card">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 w-full text-left"
      >
        {collapsed ? (
          <ChevronRight className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        )}
        <Clock className="w-4 h-4 text-gray-400" />
        <h3 className="text-sm font-semibold text-gray-300">Recent Parses</h3>
        <span className="text-xs text-gray-400 ml-auto">{count}</span>
      </button>

      {!collapsed && (
        <div className="mt-3 space-y-2">
          {useSaved
            ? savedEntries!.map((entry) => {
                const pct = Math.round(entry.confidence * 100)
                const color = entry.confidence >= 0.9 ? 'text-green-600' : entry.confidence >= 0.7 ? 'text-yellow-600' : 'text-red-600'
                return (
                  <button
                    key={entry.parse_result_id}
                    onClick={() => onRestore(entry.rule_text)}
                    className="w-full text-left text-xs bg-dark-800 hover:bg-dark-700 rounded p-2 transition-colors"
                  >
                    <div className="flex justify-between items-center">
                      <span className="text-gray-300 truncate max-w-[60%]">{entry.rule_text}</span>
                      <div className="flex items-center gap-2">
                        <span className={`font-mono ${color}`}>{pct}%</span>
                        {entry.validated ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
                        ) : entry.validated === false ? (
                          <XCircle className="w-3.5 h-3.5 text-red-400" />
                        ) : null}
                      </div>
                    </div>
                    <div className="flex justify-between items-center mt-1">
                      <span className="text-gray-400">{entry.rule_type.replace(/_/g, ' ')}</span>
                      <span className="text-gray-400">
                        {new Date(entry.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </button>
                )
              })
            : entries.map((entry, idx) => {
                const pct = Math.round(entry.confidence * 100)
                const color = entry.confidence >= 0.9 ? 'text-green-600' : entry.confidence >= 0.7 ? 'text-yellow-600' : 'text-red-600'
                return (
                  <button
                    key={idx}
                    onClick={() => onRestore(entry.rule_text)}
                    className="w-full text-left text-xs bg-dark-800 hover:bg-dark-700 rounded p-2 transition-colors"
                  >
                    <div className="flex justify-between items-center">
                      <span className="text-gray-300 truncate max-w-[70%]">{entry.rule_text}</span>
                      <span className={`font-mono ${color}`}>{pct}%</span>
                    </div>
                    <div className="flex justify-between items-center mt-1">
                      <span className="text-gray-400">{entry.rule_type.replace(/_/g, ' ')}</span>
                      <span className="text-gray-400">
                        {new Date(entry.timestamp).toLocaleDateString()}
                      </span>
                    </div>
                  </button>
                )
              })}
        </div>
      )}
    </div>
  )
}
