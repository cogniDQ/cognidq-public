/**
 * FaultyRecordsModal — universal viewer for failing/faulty records.
 *
 * Sources:
 *  - `source: 'execution'` → fetches `RuleViolation` rows for a rule execution
 *    via `GET /workspaces/{ws}/executions/{id}/violations`.
 *  - `source: 'issue'` → fetches the captured (masked) issue sample via
 *    `GET /workspaces/{ws}/issues/{id}/samples` (F034).
 *
 * Used by:
 *  - DatasetQualityPanel (per-rule "View faulty records" button)
 *  - IssueDetailPage     ("View captured records" button)
 *  - IncidentDetailDrawer (linked-issue "View records" button)
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { X, AlertTriangle, ShieldAlert, Loader2 } from 'lucide-react';

import { getExecutionViolations } from '../../services/ruleService';
import { getIssueSamples } from '../../services/issuesService';

type Source =
  | { kind: 'execution'; executionId: string; title?: string; subtitle?: string }
  | { kind: 'issue'; issueId: string; title?: string; subtitle?: string };

interface Props {
  workspaceId: string;
  source: Source | null;
  onClose: () => void;
}

interface NormalizedRow {
  rowKey: string;
  rowIdentifier?: string | null;
  rowNumber?: number | null;
  severity?: string | null;
  payload: Record<string, unknown>;
}

function normalizeRows(
  source: Source,
  data: unknown,
): { rows: NormalizedRow[]; meta: Record<string, string> } {
  if (source.kind === 'execution') {
    const list = Array.isArray(data) ? data : [];
    const rows = list.map((v: any, i) => ({
      rowKey: String(v?.id ?? i),
      rowIdentifier: v?.row_identifier ?? null,
      rowNumber: v?.row_number ?? null,
      severity: v?.severity ?? null,
      payload: (v?.violation_details as Record<string, unknown>) ?? {},
    }));
    return {
      rows,
      meta: { count: String(rows.length) },
    };
  }
  // issue samples
  const obj = (data ?? {}) as {
    rows?: Array<Record<string, unknown>>;
    sample_count?: number;
    masking_applied?: boolean;
    masking_threshold?: string | null;
    captured_at?: string | null;
  };
  const list = Array.isArray(obj.rows) ? obj.rows : [];
  const rows = list.map((r, i) => ({
    rowKey: String(i),
    payload: r,
  }));
  const meta: Record<string, string> = {
    count: String(obj.sample_count ?? rows.length),
  };
  if (obj.masking_applied) {
    meta.masking = obj.masking_threshold
      ? `Masked (${obj.masking_threshold}+)`
      : 'Masked';
  }
  if (obj.captured_at) {
    try {
      meta.captured = new Date(obj.captured_at).toLocaleString();
    } catch {
      meta.captured = obj.captured_at;
    }
  }
  return { rows, meta };
}

export default function FaultyRecordsModal({
  workspaceId,
  source,
  onClose,
}: Props) {
  const queryEnabled = !!source && !!workspaceId;
  const queryKey = source
    ? source.kind === 'execution'
      ? ['execution-violations', workspaceId, source.executionId]
      : ['issue-samples', workspaceId, source.issueId]
    : ['faulty-records-disabled'];

  const queryFn = async () => {
    if (!source) return null;
    if (source.kind === 'execution') {
      return getExecutionViolations(workspaceId, source.executionId, {
        limit: 500,
      });
    }
    return getIssueSamples(workspaceId, source.issueId);
  };

  const { data, isLoading, isError, error } = useQuery({
    queryKey,
    queryFn,
    enabled: queryEnabled,
    staleTime: 30_000,
  });

  const { rows, meta } = useMemo(() => {
    if (!source || data == null) return { rows: [], meta: {} as Record<string, string> };
    return normalizeRows(source, data);
  }, [source, data]);

  const columns = useMemo(() => {
    const set = new Set<string>();
    rows.forEach((r) => Object.keys(r.payload).forEach((k) => set.add(k)));
    return Array.from(set);
  }, [rows]);

  const open = source !== null;

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Faulty records"
      data-testid="faulty-records-modal"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="flex h-[85vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-edge-strong bg-surface-raised shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-edge px-5 py-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-danger" />
              <h3 className="text-sm font-semibold text-content">
                {source.title ?? 'Faulty records'}
              </h3>
            </div>
            {source.subtitle && (
              <p className="mt-0.5 truncate text-xs text-content-muted">
                {source.subtitle}
              </p>
            )}
            <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-content-muted">
              <span className="rounded-full bg-surface px-2 py-0.5">
                {meta.count ?? 0} record{meta.count === '1' ? '' : 's'}
              </span>
              {meta.masking && (
                <span className="inline-flex items-center gap-1 rounded-full bg-warning-soft px-2 py-0.5 text-warning">
                  <ShieldAlert className="h-3 w-3" />
                  {meta.masking}
                </span>
              )}
              {meta.captured && (
                <span className="rounded-full bg-surface px-2 py-0.5">
                  Captured {meta.captured}
                </span>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-content-muted hover:bg-surface-overlay hover:text-content"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto p-4">
          {isLoading && (
            <div className="flex h-32 items-center justify-center gap-2 text-sm text-content-muted">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading faulty records…
            </div>
          )}
          {isError && (
            <div className="rounded-md border border-danger/40 bg-danger-soft p-3 text-sm text-danger">
              Failed to load faulty records.
              {error instanceof Error ? ` ${error.message}` : ''}
            </div>
          )}
          {!isLoading && !isError && rows.length === 0 && (
            <div className="rounded-md border border-edge bg-surface p-6 text-center text-sm text-content-muted">
              No faulty records were captured for this run.
              <p className="mt-2 text-xs text-content-subtle">
                Either the check passed for every scanned row, or the engine
                did not persist a sample for this execution.
              </p>
            </div>
          )}
          {!isLoading && !isError && rows.length > 0 && (
            <div className="overflow-x-auto rounded-md border border-edge">
              <table className="min-w-full text-xs">
                <thead className="bg-surface text-content-muted">
                  <tr>
                    {source.kind === 'execution' && (
                      <>
                        <th className="px-2 py-1.5 text-left font-medium">#</th>
                        <th className="px-2 py-1.5 text-left font-medium">
                          Row id
                        </th>
                        <th className="px-2 py-1.5 text-left font-medium">
                          Severity
                        </th>
                      </>
                    )}
                    {columns.map((c) => (
                      <th
                        key={c}
                        className="px-2 py-1.5 text-left font-medium font-mono"
                      >
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr
                      key={r.rowKey}
                      className="border-t border-edge-subtle hover:bg-surface-overlay/30"
                    >
                      {source.kind === 'execution' && (
                        <>
                          <td className="px-2 py-1.5 text-content-subtle">
                            {r.rowNumber ?? '—'}
                          </td>
                          <td className="px-2 py-1.5 font-mono text-content">
                            {r.rowIdentifier ?? '—'}
                          </td>
                          <td className="px-2 py-1.5">
                            {r.severity ? (
                              <span className="rounded bg-danger-soft px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-danger">
                                {r.severity}
                              </span>
                            ) : (
                              '—'
                            )}
                          </td>
                        </>
                      )}
                      {columns.map((c) => {
                        const v = r.payload[c];
                        return (
                          <td
                            key={c}
                            className="px-2 py-1.5 align-top text-content"
                          >
                            {v == null ? (
                              <span className="text-content-subtle">null</span>
                            ) : typeof v === 'object' ? (
                              <code className="font-mono text-[10px] text-content-muted">
                                {JSON.stringify(v)}
                              </code>
                            ) : (
                              String(v)
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
