/**
 * AnomaliesPage — F5 persisted anomaly review (workspace-scoped)
 *
 * Route: /hub/ws/:workspace_id/anomalies
 *
 * Features:
 *   - "Run detection" button (calls /anomalies/run, toasts result)
 *   - Filter chips: status (open/acknowledged/resolved/suppressed), severity
 *   - Table of anomalies with severity + status badges
 *   - Row click → detail drawer with notes and lifecycle actions
 */
import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2, EyeOff, Play, RefreshCw, X, Activity } from 'lucide-react';
import toast from 'react-hot-toast';
import EmptyState from '../../components/common/EmptyState';

import {
  acknowledgeAnomaly,
  listAnomalies,
  resolveAnomaly,
  runAnomalyDetection,
  suppressAnomaly,
} from '../../services/anomaliesService';
import type {
  Anomaly,
  AnomalySeverity,
  AnomalyStatus,
} from '../../services/anomaliesService';

const STATUS_BADGE: Record<AnomalyStatus, string> = {
  open:         'bg-red-900/50 text-red-300 border-red-700',
  acknowledged: 'bg-yellow-900/50 text-yellow-300 border-yellow-700',
  resolved:     'bg-green-900/50 text-green-300 border-green-700',
  suppressed:   'bg-slate-800 text-slate-400 border-slate-600',
};

const SEVERITY_BADGE: Record<AnomalySeverity, string> = {
  Critical: 'bg-red-900/50 text-red-300 border-red-700',
  High:     'bg-orange-900/50 text-orange-300 border-orange-700',
  Medium:   'bg-yellow-900/50 text-yellow-300 border-yellow-700',
  Low:      'bg-slate-800 text-slate-300 border-slate-600',
};

const STATUSES: (AnomalyStatus | '')[] = ['', 'open', 'acknowledged', 'resolved', 'suppressed'];
const SEVERITIES: (AnomalySeverity | '')[] = ['', 'Critical', 'High', 'Medium', 'Low'];

const REFRESH_MS = 30_000;

export default function AnomaliesPage() {
  const { workspace_id } = useParams<{ workspace_id: string }>();
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<AnomalyStatus | ''>('open');
  const [severityFilter, setSeverityFilter] = useState<AnomalySeverity | ''>('');
  const [selected, setSelected] = useState<Anomaly | null>(null);
  const [notes, setNotes] = useState('');

  const queryKey = useMemo(
    () => ['anomalies', workspace_id, statusFilter, severityFilter] as const,
    [workspace_id, statusFilter, severityFilter],
  );

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey,
    queryFn: () =>
      listAnomalies(workspace_id!, {
        status: statusFilter || undefined,
        severity: severityFilter || undefined,
        limit: 200,
      }),
    enabled: !!workspace_id,
    staleTime: REFRESH_MS,
    refetchInterval: REFRESH_MS,
  });

  const runMutation = useMutation({
    mutationFn: () => runAnomalyDetection(workspace_id!),
    onSuccess: (r) => {
      toast.success(`Detection complete: ${r.detected} found (${r.inserted} new, ${r.updated} updated)`);
      qc.invalidateQueries({ queryKey: ['anomalies', workspace_id] });
    },
    onError: () => toast.error('Anomaly detection failed'),
  });

  function handleLifecycle(action: 'acknowledge' | 'resolve' | 'suppress') {
    if (!selected) return;
    const fn =
      action === 'acknowledge' ? acknowledgeAnomaly :
      action === 'resolve'     ? resolveAnomaly :
                                 suppressAnomaly;
    fn(workspace_id!, selected.id, notes || undefined)
      .then((updated) => {
        toast.success(`Anomaly ${updated.status}`);
        setSelected(null);
        setNotes('');
        qc.invalidateQueries({ queryKey: ['anomalies', workspace_id] });
      })
      .catch(() => toast.error(`Failed to ${action}`));
  }

  const items = data?.items ?? [];

  return (
    <div className="p-6 space-y-6" data-testid="anomalies-page">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100 flex items-center gap-2">
            <Activity className="h-6 w-6 text-orange-400" />
            Anomalies
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Persisted statistical anomalies detected across rule and flow executions.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            className="px-3 py-2 text-sm border border-slate-700 rounded text-slate-300 hover:bg-slate-800 flex items-center gap-2"
            data-testid="anomalies-refresh"
          >
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
          <button
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
            className="px-3 py-2 text-sm bg-orange-600 hover:bg-orange-500 text-white rounded flex items-center gap-2 disabled:opacity-50"
            data-testid="anomalies-run-detection"
          >
            <Play className="h-4 w-4" /> {runMutation.isPending ? 'Running…' : 'Run detection'}
          </button>
        </div>
      </header>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div>
          <label className="text-xs text-slate-400 block mb-1">Status</label>
          <div className="flex gap-1">
            {STATUSES.map((s) => (
              <button
                key={s || 'all'}
                onClick={() => setStatusFilter(s)}
                className={`px-3 py-1 text-xs rounded border ${
                  statusFilter === s
                    ? 'bg-slate-700 text-slate-100 border-slate-500'
                    : 'bg-slate-900 text-slate-400 border-slate-700 hover:bg-slate-800'
                }`}
                data-testid={`anomalies-filter-status-${s || 'all'}`}
              >
                {s || 'All'}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="text-xs text-slate-400 block mb-1">Severity</label>
          <div className="flex gap-1">
            {SEVERITIES.map((s) => (
              <button
                key={s || 'all'}
                onClick={() => setSeverityFilter(s)}
                className={`px-3 py-1 text-xs rounded border ${
                  severityFilter === s
                    ? 'bg-slate-700 text-slate-100 border-slate-500'
                    : 'bg-slate-900 text-slate-400 border-slate-700 hover:bg-slate-800'
                }`}
                data-testid={`anomalies-filter-severity-${s || 'all'}`}
              >
                {s || 'All'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="border border-slate-700 rounded overflow-hidden">
        {isLoading && (
          <div className="p-6 text-slate-400 text-sm">Loading anomalies…</div>
        )}
        {isError && (
          <div className="p-6 text-red-400 text-sm">Failed to load anomalies.</div>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <EmptyState
            icon={AlertTriangle}
            title="No anomalies"
            description="No anomalies match the current filters. Run detection to evaluate the latest data."
          />
        )}
        {!isLoading && items.length > 0 && (
          <table className="w-full text-sm" data-testid="anomalies-table">
            <thead className="bg-slate-900 text-xs text-slate-400 uppercase">
              <tr>
                <th className="text-left px-3 py-2">Severity</th>
                <th className="text-left px-3 py-2">Type</th>
                <th className="text-left px-3 py-2">Dataset / Column</th>
                <th className="text-left px-3 py-2">Summary</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-left px-3 py-2">Detected</th>
              </tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr
                  key={a.id}
                  onClick={() => { setSelected(a); setNotes(a.notes || ''); }}
                  className="border-t border-slate-800 hover:bg-slate-900 cursor-pointer"
                  data-testid={`anomalies-row-${a.id}`}
                >
                  <td className="px-3 py-2">
                    <span className={`px-2 py-0.5 rounded border text-xs ${SEVERITY_BADGE[a.severity] ?? ''}`}>
                      {a.severity}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-slate-300">{a.anomaly_type}</td>
                  <td className="px-3 py-2 text-slate-300">
                    {a.dataset || '—'}
                    {a.column ? <span className="text-slate-500"> · {a.column}</span> : null}
                  </td>
                  <td className="px-3 py-2 text-slate-200">{a.summary}</td>
                  <td className="px-3 py-2">
                    <span className={`px-2 py-0.5 rounded border text-xs ${STATUS_BADGE[a.status] ?? ''}`}>
                      {a.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-slate-400 text-xs">
                    {a.detected_at ? new Date(a.detected_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Detail drawer */}
      {selected && (
        <div className="fixed inset-0 z-50 flex" data-testid="anomaly-detail-overlay">
          <div className="flex-1 bg-black/50" onClick={() => setSelected(null)} />
          <div
            className="w-full max-w-xl bg-slate-900 border-l border-slate-700 overflow-y-auto"
            data-testid="anomaly-detail-drawer"
          >
            <div className="flex items-start justify-between p-4 border-b border-slate-700">
              <div>
                <h2 className="text-lg font-semibold text-slate-100">{selected.summary}</h2>
                <div className="flex gap-2 mt-2">
                  <span className={`px-2 py-0.5 rounded border text-xs ${SEVERITY_BADGE[selected.severity] ?? ''}`}>
                    {selected.severity}
                  </span>
                  <span className={`px-2 py-0.5 rounded border text-xs ${STATUS_BADGE[selected.status] ?? ''}`}>
                    {selected.status}
                  </span>
                </div>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-slate-400 hover:text-slate-200"
                aria-label="Close"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <dl className="grid grid-cols-2 gap-3 p-4 text-sm">
              <div><dt className="text-slate-500 text-xs">Type</dt><dd className="text-slate-200">{selected.anomaly_type}</dd></div>
              <div><dt className="text-slate-500 text-xs">Dataset</dt><dd className="text-slate-200">{selected.dataset || '—'}</dd></div>
              <div><dt className="text-slate-500 text-xs">Column</dt><dd className="text-slate-200">{selected.column || '—'}</dd></div>
              <div><dt className="text-slate-500 text-xs">Rule</dt><dd className="text-slate-200 font-mono text-xs">{selected.rule_id || '—'}</dd></div>
              <div><dt className="text-slate-500 text-xs">Current</dt><dd className="text-slate-200">{selected.current_value || '—'}</dd></div>
              <div><dt className="text-slate-500 text-xs">Expected</dt><dd className="text-slate-200">{selected.expected_value || '—'}</dd></div>
              <div className="col-span-2"><dt className="text-slate-500 text-xs">Deviation</dt><dd className="text-slate-200">{selected.deviation || '—'}</dd></div>
              <div><dt className="text-slate-500 text-xs">Detected</dt><dd className="text-slate-200">{selected.detected_at ? new Date(selected.detected_at).toLocaleString() : '—'}</dd></div>
              <div><dt className="text-slate-500 text-xs">Acknowledged</dt><dd className="text-slate-200">{selected.acknowledged_at ? new Date(selected.acknowledged_at).toLocaleString() : '—'}</dd></div>
              <div><dt className="text-slate-500 text-xs">Resolved</dt><dd className="text-slate-200">{selected.resolved_at ? new Date(selected.resolved_at).toLocaleString() : '—'}</dd></div>
            </dl>

            <div className="p-4 border-t border-slate-700">
              <label className="block text-xs text-slate-400 mb-1">Notes</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={4}
                className="w-full px-3 py-2 text-sm bg-slate-950 border border-slate-700 rounded text-slate-200"
                placeholder="Investigation notes, root cause, remediation…"
                data-testid="anomaly-notes"
              />
            </div>

            <div className="p-4 border-t border-slate-700 flex flex-wrap gap-2">
              <button
                onClick={() => handleLifecycle('acknowledge')}
                disabled={selected.status !== 'open'}
                className="px-3 py-2 text-sm bg-yellow-600 hover:bg-yellow-500 text-white rounded disabled:opacity-50 flex items-center gap-2"
                data-testid="anomaly-acknowledge"
              >
                <CheckCircle2 className="h-4 w-4" /> Acknowledge
              </button>
              <button
                onClick={() => handleLifecycle('resolve')}
                disabled={selected.status === 'resolved'}
                className="px-3 py-2 text-sm bg-green-600 hover:bg-green-500 text-white rounded disabled:opacity-50 flex items-center gap-2"
                data-testid="anomaly-resolve"
              >
                <CheckCircle2 className="h-4 w-4" /> Resolve
              </button>
              <button
                onClick={() => handleLifecycle('suppress')}
                disabled={selected.status === 'suppressed'}
                className="px-3 py-2 text-sm bg-slate-700 hover:bg-slate-600 text-slate-100 rounded disabled:opacity-50 flex items-center gap-2"
                data-testid="anomaly-suppress"
              >
                <EyeOff className="h-4 w-4" /> Suppress
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
