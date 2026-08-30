/**
 * F7 — Lightweight modal that displays the recent execution history of a rule.
 * Opened from RulesPage when the URL carries `?rule=<id>&tab=executions`,
 * typically deep-linked from the dataset detail page's Quality panel.
 */
import { Fragment } from 'react';
import { useQuery } from '@tanstack/react-query';
import { X, PlayCircle } from 'lucide-react';
import {
  getRuleExecutionHistory,
  type RuleExecutionResponse,
} from '../../services/ruleService';

interface Props {
  workspaceId: string;
  ruleId: string;
  ruleName?: string;
  onClose: () => void;
}

function statusColor(status?: string | null): string {
  switch (status) {
    case 'completed':
      return 'text-green-400';
    case 'running':
    case 'pending':
      return 'text-blue-400';
    case 'failed':
      return 'text-red-400';
    case 'cancelled':
      return 'text-gray-400';
    default:
      return 'text-gray-500';
  }
}

function fmtDuration(secs?: number | null): string {
  if (secs == null) return '—';
  if (secs < 1) return `${Math.round(secs * 1000)}ms`;
  if (secs < 60) return `${secs.toFixed(1)}s`;
  const m = Math.floor(secs / 60);
  const s = Math.round(secs % 60);
  return `${m}m ${s}s`;
}

export default function RuleExecutionsModal({
  workspaceId,
  ruleId,
  ruleName,
  onClose,
}: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['rule-executions-modal', workspaceId, ruleId],
    queryFn: () => getRuleExecutionHistory(workspaceId, ruleId, { limit: 20 }),
    enabled: !!workspaceId && !!ruleId,
    staleTime: 10_000,
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="rule-executions-title"
      data-testid="rule-executions-modal"
    >
      <div
        className="w-full max-w-3xl max-h-[85vh] flex flex-col rounded-xl border border-gray-700 bg-gray-900 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3 border-b border-gray-700 px-5 py-3">
          <div>
            <h2
              id="rule-executions-title"
              className="text-sm font-semibold text-white flex items-center gap-2"
            >
              <PlayCircle className="w-4 h-4 text-purple-300" />
              Executions
            </h2>
            {ruleName && (
              <p className="mt-0.5 text-xs text-gray-400 truncate">{ruleName}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading && <p className="text-sm text-gray-400">Loading executions…</p>}
          {isError && (
            <p className="text-sm text-red-300">Failed to load execution history.</p>
          )}
          {!isLoading && !isError && (data?.length ?? 0) === 0 && (
            <p className="text-sm text-gray-400">
              No executions recorded for this rule yet.
            </p>
          )}
          {!isLoading && !isError && data && data.length > 0 && (
            <table className="w-full text-xs">
              <thead className="text-gray-400">
                <tr>
                  <th className="text-left py-2">Started</th>
                  <th className="text-left py-2">Status</th>
                  <th className="text-right py-2">Pass rate</th>
                  <th className="text-right py-2">Scanned</th>
                  <th className="text-right py-2">Failed</th>
                  <th className="text-right py-2">Duration</th>
                </tr>
              </thead>
              <tbody>
                {data.map((exec: RuleExecutionResponse) => (
                  <Fragment key={exec.id}>
                    <tr className="border-t border-gray-800">
                      <td className="py-2 text-gray-300">
                        {exec.started_at
                          ? new Date(exec.started_at).toLocaleString()
                          : new Date(exec.created_at).toLocaleString()}
                      </td>
                      <td className={`py-2 font-medium ${statusColor(exec.status)}`}>
                        {exec.status}
                      </td>
                      <td className="py-2 text-right text-gray-200">
                        {exec.pass_rate != null
                          ? `${Number(exec.pass_rate).toFixed(1)}%`
                          : '—'}
                      </td>
                      <td className="py-2 text-right text-gray-300">
                        {(exec.rows_scanned ?? 0).toLocaleString()}
                      </td>
                      <td
                        className={`py-2 text-right ${
                          (exec.rows_failed ?? 0) > 0 ? 'text-red-300' : 'text-gray-300'
                        }`}
                      >
                        {(exec.rows_failed ?? 0).toLocaleString()}
                      </td>
                      <td className="py-2 text-right text-gray-400">
                        {fmtDuration(exec.duration_seconds)}
                      </td>
                    </tr>
                    {exec.error_message && (
                      <tr className="border-t border-gray-800/60">
                        <td colSpan={6} className="py-2 text-red-300">
                          {exec.error_message}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
