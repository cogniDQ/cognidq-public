import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { SignalBreakdown } from '@/types/resolution';

interface SignalBreakdownTooltipProps {
  breakdown: SignalBreakdown[];
}

export function SignalBreakdownTooltip({ breakdown }: SignalBreakdownTooltipProps) {
  const [expanded, setExpanded] = useState(false);

  if (!breakdown.length) return null;

  return (
    <div className="mt-1">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
        data-testid="signal-toggle"
      >
        {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        {expanded ? 'Hide' : 'Show'} signal details
      </button>
      {expanded && (
        <div className="mt-1 space-y-1" data-testid="signal-details">
          {breakdown.map((s) => (
            <div key={s.signal_name} className="flex items-center justify-between text-xs">
              <span className="text-gray-600">{s.signal_name.replace(/_/g, ' ')}</span>
              <div className="flex items-center gap-2">
                <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full"
                    style={{ width: `${s.score * 100}%` }}
                  />
                </div>
                <span className="text-gray-500 w-8 text-right">{(s.score * 100).toFixed(0)}%</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
