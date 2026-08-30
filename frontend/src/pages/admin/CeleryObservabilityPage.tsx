/**
 * CeleryObservabilityPage — F6 platform-only Celery / Flower dashboard
 *
 * Route: /admin/celery
 *
 * Surfaces worker health, registered tasks per worker, and recent task history
 * (proxied from Flower's REST API by the backend).
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity, RefreshCw, AlertTriangle, CheckCircle2, ExternalLink } from 'lucide-react';
import {
  getCeleryHealth,
  getCeleryWorkers,
  getCeleryTasks,
} from '../../services/celeryObservabilityService';

const REFRESH_MS = 15_000;

const STATE_BADGE: Record<string, string> = {
  SUCCESS: 'bg-green-900/50 text-green-300 border-green-700',
  FAILURE: 'bg-red-900/50 text-red-300 border-red-700',
  STARTED: 'bg-blue-900/50 text-blue-300 border-blue-700',
  RETRY:   'bg-yellow-900/50 text-yellow-300 border-yellow-700',
  PENDING: 'bg-slate-800 text-slate-300 border-slate-600',
};

export default function CeleryObservabilityPage() {
  const [stateFilter, setStateFilter] = useState<string>('');

  const health = useQuery({
    queryKey: ['celery-health'],
    queryFn: getCeleryHealth,
    refetchInterval: REFRESH_MS,
    staleTime: REFRESH_MS,
  });

  const workers = useQuery({
    queryKey: ['celery-workers'],
    queryFn: getCeleryWorkers,
    refetchInterval: REFRESH_MS,
    staleTime: REFRESH_MS,
  });

  const tasks = useQuery({
    queryKey: ['celery-tasks', stateFilter],
    queryFn: () => getCeleryTasks({ limit: 50, state: stateFilter || undefined }),
    refetchInterval: REFRESH_MS,
    staleTime: REFRESH_MS,
  });

  const refetchAll = () => {
    health.refetch();
    workers.refetch();
    tasks.refetch();
  };

  const h = health.data;
  const flowerUrl = (typeof window !== 'undefined') ? `${window.location.protocol}//${window.location.hostname}:5555` : '';

  return (
    <div className="p-6 space-y-6" data-testid="celery-page">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100 flex items-center gap-2">
            <Activity className="h-6 w-6 text-orange-400" />
            Celery Observability
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Platform-wide background worker health, registered tasks, and recent execution history.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={flowerUrl}
            target="_blank"
            rel="noreferrer"
            className="px-3 py-2 text-sm border border-slate-700 rounded text-slate-300 hover:bg-slate-800 flex items-center gap-2"
            data-testid="celery-flower-link"
          >
            <ExternalLink className="h-4 w-4" /> Open Flower
          </a>
          <button
            onClick={refetchAll}
            className="px-3 py-2 text-sm border border-slate-700 rounded text-slate-300 hover:bg-slate-800 flex items-center gap-2"
            data-testid="celery-refresh"
          >
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
        </div>
      </header>

      {/* Health KPIs */}
      <div className="grid grid-cols-4 gap-3">
        <KPI label="Status" value={h?.status ?? '—'} highlight={h?.status === 'ok' ? 'green' : h?.status === 'degraded' ? 'yellow' : 'red'} testId="celery-kpi-status" />
        <KPI label="Workers online" value={h ? `${h.workers_online} / ${h.workers_total}` : '—'} testId="celery-kpi-workers" />
        <KPI label="Broker" value={h?.broker_url || '—'} small testId="celery-kpi-broker" />
        <KPI label="Detail" value={h?.detail ?? 'OK'} small testId="celery-kpi-detail" />
      </div>

      {/* Workers */}
      <section>
        <h2 className="text-sm font-semibold text-slate-300 uppercase mb-2">Workers</h2>
        <div className="border border-slate-700 rounded overflow-hidden">
          {workers.isLoading && <div className="p-6 text-slate-400 text-sm">Loading workers…</div>}
          {workers.isError && <div className="p-6 text-red-400 text-sm">Failed to load workers.</div>}
          {!workers.isLoading && (workers.data?.workers ?? []).length === 0 && (
            <div className="p-6 text-slate-400 text-sm flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-yellow-400" /> No workers detected.
            </div>
          )}
          {(workers.data?.workers ?? []).length > 0 && (
            <table className="w-full text-sm" data-testid="celery-workers-table">
              <thead className="bg-slate-900 text-xs text-slate-400 uppercase">
                <tr>
                  <th className="text-left px-3 py-2">Worker</th>
                  <th className="text-left px-3 py-2">Status</th>
                  <th className="text-left px-3 py-2">Registered tasks</th>
                </tr>
              </thead>
              <tbody>
                {workers.data!.workers.map((w) => (
                  <tr key={w.name} className="border-t border-slate-800" data-testid={`celery-worker-${w.name}`}>
                    <td className="px-3 py-2 text-slate-200 font-mono text-xs">{w.name}</td>
                    <td className="px-3 py-2">
                      {w.status ? (
                        <span className="px-2 py-0.5 rounded border text-xs bg-green-900/50 text-green-300 border-green-700 inline-flex items-center gap-1">
                          <CheckCircle2 className="h-3 w-3" /> online
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded border text-xs bg-red-900/50 text-red-300 border-red-700 inline-flex items-center gap-1">
                          <AlertTriangle className="h-3 w-3" /> offline
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-slate-400 text-xs">
                      {w.registered_tasks?.length ?? 0} tasks
                      <details className="mt-1">
                        <summary className="cursor-pointer text-slate-500">show</summary>
                        <ul className="mt-1 ml-4 list-disc text-slate-400">
                          {w.registered_tasks?.map((t) => (
                            <li key={t} className="font-mono">{t}</li>
                          ))}
                        </ul>
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* Recent tasks */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-semibold text-slate-300 uppercase">Recent tasks</h2>
          <div className="flex gap-1">
            {['', 'SUCCESS', 'FAILURE', 'STARTED', 'RETRY'].map((s) => (
              <button
                key={s || 'all'}
                onClick={() => setStateFilter(s)}
                className={`px-3 py-1 text-xs rounded border ${
                  stateFilter === s
                    ? 'bg-slate-700 text-slate-100 border-slate-500'
                    : 'bg-slate-900 text-slate-400 border-slate-700 hover:bg-slate-800'
                }`}
                data-testid={`celery-task-filter-${s || 'all'}`}
              >
                {s || 'All'}
              </button>
            ))}
          </div>
        </div>
        <div className="border border-slate-700 rounded overflow-hidden">
          {tasks.isLoading && <div className="p-6 text-slate-400 text-sm">Loading tasks…</div>}
          {tasks.isError && <div className="p-6 text-red-400 text-sm">Failed to load tasks.</div>}
          {!tasks.isLoading && (tasks.data?.tasks ?? []).length === 0 && (
            <div className="p-6 text-slate-400 text-sm">No tasks recorded yet.</div>
          )}
          {(tasks.data?.tasks ?? []).length > 0 && (
            <table className="w-full text-sm" data-testid="celery-tasks-table">
              <thead className="bg-slate-900 text-xs text-slate-400 uppercase">
                <tr>
                  <th className="text-left px-3 py-2">Task</th>
                  <th className="text-left px-3 py-2">State</th>
                  <th className="text-left px-3 py-2">Worker</th>
                  <th className="text-left px-3 py-2">Runtime</th>
                  <th className="text-left px-3 py-2">Received</th>
                </tr>
              </thead>
              <tbody>
                {tasks.data!.tasks.map((t) => (
                  <tr key={t.id} className="border-t border-slate-800" data-testid={`celery-task-${t.id}`}>
                    <td className="px-3 py-2">
                      <div className="text-slate-200">{t.name || '—'}</div>
                      <div className="text-slate-500 font-mono text-xs">{t.id}</div>
                      {t.exception && (
                        <div className="text-red-400 text-xs mt-1 truncate max-w-md" title={t.exception}>
                          {t.exception}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`px-2 py-0.5 rounded border text-xs ${STATE_BADGE[t.state || ''] ?? 'bg-slate-800 text-slate-300 border-slate-600'}`}>
                        {t.state || '—'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-slate-400 font-mono text-xs">{t.worker || '—'}</td>
                    <td className="px-3 py-2 text-slate-400 text-xs">
                      {t.runtime != null ? `${t.runtime.toFixed(2)}s` : '—'}
                    </td>
                    <td className="px-3 py-2 text-slate-400 text-xs">
                      {t.received ? new Date(t.received * 1000).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}

function KPI({ label, value, highlight, small, testId }: {
  label: string; value: string; highlight?: 'green' | 'yellow' | 'red'; small?: boolean; testId?: string;
}) {
  const colorClass =
    highlight === 'green'  ? 'text-green-400'  :
    highlight === 'yellow' ? 'text-yellow-400' :
    highlight === 'red'    ? 'text-red-400'    : 'text-slate-200';
  return (
    <div className="border border-slate-700 rounded p-3 bg-slate-900/50" data-testid={testId}>
      <div className="text-xs text-slate-500 uppercase">{label}</div>
      <div className={`mt-1 ${small ? 'text-sm font-mono break-all' : 'text-2xl font-semibold'} ${colorClass}`}>
        {value}
      </div>
    </div>
  );
}
