/**
 * IncidentsPage — workspace-scoped incident list and management (F079)
 *
 * Route: /hub/ws/:workspace_id/incidents
 *
 * Features:
 *   - Filterable list (status, severity, priority)
 *   - Status badge with SLA breach flag
 *   - Inline status transition via dropdown (incidents:write only)
 *   - CSV export
 *   - Pagination
 */
import { useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertOctagon, Download, ChevronUp, ChevronDown, ShieldAlert, Settings, Sparkles } from 'lucide-react';
import toast from 'react-hot-toast';

import {
  listIncidents,
  updateIncident,
  exportIncidentsCsv,
  INCIDENT_STATUSES,
  INCIDENT_SEVERITIES,
  INCIDENT_PRIORITIES,
  ALLOWED_TRANSITIONS,
} from '../../services/incidentsService';
import { loadWorkspaceDemoData } from '../../services/workspaceDemoData';
import type { IncidentStatus, IncidentSeverity, IncidentPriority } from '../../services/incidentsService';
import { getActorRole } from '../../utils/jwt';
import { useTenantScopedPath } from '../../hooks/useTenantScopedPath';
import IncidentDetailDrawer from '../../components/incidents/IncidentDetailDrawer';
import EmptyState from '../../components/common/EmptyState';

// ─────────────────────────────────────────────────────────────────────────────
// Style maps
// ─────────────────────────────────────────────────────────────────────────────

const STATUS_BADGE: Record<IncidentStatus, string> = {
  open:         'bg-red-900/50 text-red-300 border-red-700',
  acknowledged: 'bg-yellow-900/50 text-yellow-300 border-yellow-700',
  mitigated:    'bg-blue-900/50 text-blue-300 border-blue-700',
  resolved:     'bg-green-900/50 text-green-300 border-green-700',
  closed:       'bg-gray-700/50 text-gray-400 border-gray-600',
  reopened:     'bg-orange-900/50 text-orange-300 border-orange-700',
};

const SEVERITY_BADGE: Record<IncidentSeverity, string> = {
  critical:      'bg-red-900/50 text-red-300 border-red-700',
  major:         'bg-orange-900/50 text-orange-300 border-orange-700',
  minor:         'bg-yellow-900/50 text-yellow-300 border-yellow-700',
  informational: 'bg-gray-700/50 text-gray-400 border-gray-600',
};

const PRIORITY_BADGE: Record<IncidentPriority, string> = {
  P1: 'text-red-400 font-bold',
  P2: 'text-orange-400 font-semibold',
  P3: 'text-yellow-400',
  P4: 'text-gray-400',
};

const STALE_TIME = 30_000;

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export default function IncidentsPage() {
  const { workspace_id } = useParams<{ workspace_id: string }>();
  const { wsPath } = useTenantScopedPath();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [exporting, setExporting] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [drawerIncidentId, setDrawerIncidentId] = useState<string | null>(null);

  const token = localStorage.getItem('access_token');
  const actorRole = getActorRole(token);
  const canWrite = actorRole === 'workspace_administrator'
    || actorRole === 'data_engineer'
    || actorRole === 'data_steward';

  const page = parseInt(searchParams.get('page') ?? '1', 10);
  const statusFilter = searchParams.get('status') ?? '';
  const severityFilter = searchParams.get('severity') ?? '';
  const priorityFilter = searchParams.get('priority') ?? '';

  const queryParams = {
    page,
    page_size: 25,
    ...(statusFilter   ? { status:   statusFilter }   : {}),
    ...(severityFilter ? { severity: severityFilter } : {}),
    ...(priorityFilter ? { priority: priorityFilter } : {}),
  };

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['incidents', workspace_id, queryParams],
    queryFn: () => listIncidents(workspace_id!, queryParams),
    enabled: !!workspace_id,
    staleTime: STALE_TIME,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const hasNext = data?.has_next ?? false;

  const [seeding, setSeeding] = useState(false);
  async function handleLoadSample() {
    if (!workspace_id || seeding) return;
    setSeeding(true);
    try {
      await loadWorkspaceDemoData(workspace_id);
      toast.success('Sample data loaded.');
      await queryClient.invalidateQueries({ queryKey: ['incidents', workspace_id] });
      refetch();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Failed to load sample data.');
    } finally {
      setSeeding(false);
    }
  }

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value); else next.delete(key);
    next.delete('page');
    setSearchParams(next);
  }

  function goToPage(p: number) {
    const next = new URLSearchParams(searchParams);
    next.set('page', String(p));
    setSearchParams(next);
  }

  async function handleStatusChange(incidentId: string, currentStatus: IncidentStatus, newStatus: IncidentStatus) {
    if (newStatus === currentStatus) return;
    const needsResolution = newStatus === 'resolved' || newStatus === 'closed';
    if (needsResolution) {
      const summary = window.prompt(
        `Enter a resolution summary (required to mark as ${newStatus}):`,
      );
      if (!summary?.trim()) {
        toast.error('Resolution summary is required.');
        return;
      }
      setUpdatingId(incidentId);
      try {
        await updateIncident(workspace_id!, incidentId, {
          status: newStatus,
          resolution_summary: summary.trim(),
        });
        await queryClient.invalidateQueries({ queryKey: ['incidents', workspace_id] });
        toast.success(`Incident marked as ${newStatus}.`);
      } catch {
        toast.error('Failed to update incident status.');
      } finally {
        setUpdatingId(null);
      }
      return;
    }

    setUpdatingId(incidentId);
    try {
      await updateIncident(workspace_id!, incidentId, { status: newStatus });
      await queryClient.invalidateQueries({ queryKey: ['incidents', workspace_id] });
      toast.success(`Incident marked as ${newStatus}.`);
    } catch {
      toast.error('Failed to update incident status.');
    } finally {
      setUpdatingId(null);
    }
  }

  async function handleExport() {
    setExporting(true);
    try {
      await exportIncidentsCsv(workspace_id!, {
        ...(statusFilter   ? { status:   statusFilter }   : {}),
        ...(severityFilter ? { severity: severityFilter } : {}),
        ...(priorityFilter ? { priority: priorityFilter } : {}),
      });
    } catch {
      toast.error('Export failed.');
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* ── Header ────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <AlertOctagon className="w-6 h-6 text-red-400" />
          <div>
            <h1 className="text-xl font-semibold text-white">Incidents</h1>
            <p className="text-sm text-gray-400">
              {total > 0 ? `${total} incident${total !== 1 ? 's' : ''}` : 'No incidents'}
              {statusFilter || severityFilter || priorityFilter ? ' (filtered)' : ''}
            </p>
          </div>
        </div>

        <button
          onClick={handleExport}
          disabled={exporting}
          className="flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:text-white border border-gray-600 hover:border-gray-500 rounded-lg transition-colors disabled:opacity-40"
        >
          <Download className="w-4 h-4" />
          {exporting ? 'Exporting…' : 'Export CSV'}
        </button>
      </div>

      {/* ── Filters ───────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 mb-5">
        <select
          value={statusFilter}
          onChange={e => setParam('status', e.target.value)}
          className="px-3 py-1.5 bg-gray-800 border border-gray-600 rounded-lg text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">All Statuses</option>
          {INCIDENT_STATUSES.map(s => (
            <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
          ))}
        </select>

        <select
          value={severityFilter}
          onChange={e => setParam('severity', e.target.value)}
          className="px-3 py-1.5 bg-gray-800 border border-gray-600 rounded-lg text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">All Severities</option>
          {INCIDENT_SEVERITIES.map(s => (
            <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
          ))}
        </select>

        <select
          value={priorityFilter}
          onChange={e => setParam('priority', e.target.value)}
          className="px-3 py-1.5 bg-gray-800 border border-gray-600 rounded-lg text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">All Priorities</option>
          {INCIDENT_PRIORITIES.map(p => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>

        {(statusFilter || severityFilter || priorityFilter) && (
          <button
            onClick={() => setSearchParams(new URLSearchParams())}
            className="px-3 py-1.5 text-sm text-gray-400 hover:text-white transition-colors"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* ── Loading / Error ────────────────────────────────────────── */}
      {isLoading && (
        <div className="text-gray-400 text-sm">Loading incidents…</div>
      )}
      {isError && (
        <EmptyState
          variant="error"
          title="Couldn't load incidents"
          description="We hit a snag fetching incidents for this workspace. Try again or check your connection."
          onRetry={() => refetch()}
          testId="incidents-error"
        />
      )}

      {/* ── Table ───────────────────────────────────────── */}
      {!isLoading && !isError && (
        <>
          {items.length === 0 ? (
            (statusFilter || severityFilter || priorityFilter) ? (
              <EmptyState
                icon={ShieldAlert}
                title="No incidents match these filters"
                description="Adjust or clear the filters above to see other incidents."
                primaryAction={{
                  label: 'Clear filters',
                  onClick: () => setSearchParams(new URLSearchParams()),
                }}
                testId="incidents-empty-filtered"
              />
            ) : (
              <EmptyState
                icon={ShieldAlert}
                title="No incidents — your workspace is healthy"
                description="Incidents are opened automatically when an Issue meets the severity and recurrence thresholds in your auto-incident policy. Issues from failing rules will appear here as incidents."
                primaryAction={{
                  label: 'View Issues',
                  to: wsPath(workspace_id ?? '', '/issues'),
                }}
                secondaryAction={{
                  label: 'Configure policy',
                  to: wsPath(workspace_id ?? '', '/settings'),
                  icon: Settings,
                }}
                tertiaryAction={{
                  label: seeding ? 'Loading…' : 'Load sample data',
                  onClick: handleLoadSample,
                  icon: Sparkles,
                }}
                testId="incidents-empty"
              />
            )
          ) : (
            <div className="rounded-xl border border-gray-700 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-800 border-b border-gray-700">
                  <tr>
                    <th className="px-4 py-3 text-left text-gray-400 font-medium">Title</th>
                    <th className="px-4 py-3 text-left text-gray-400 font-medium">Severity</th>
                    <th className="px-4 py-3 text-left text-gray-400 font-medium">Priority</th>
                    <th className="px-4 py-3 text-left text-gray-400 font-medium">Status</th>
                    <th className="px-4 py-3 text-left text-gray-400 font-medium">Issues</th>
                    <th className="px-4 py-3 text-left text-gray-400 font-medium">Owner</th>
                    <th className="px-4 py-3 text-left text-gray-400 font-medium">Opened</th>
                    {canWrite && (
                      <th className="px-4 py-3 text-right text-gray-400 font-medium">Actions</th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-700/50">
                  {items.map(inc => {
                    const transitions = ALLOWED_TRANSITIONS[inc.status] ?? [];
                    return (
                      <tr
                        key={inc.id}
                        className="bg-gray-900 hover:bg-gray-800/60 transition-colors cursor-pointer"
                        onClick={() => setDrawerIncidentId(inc.id)}
                      >
                        {/* Title */}
                        <td className="px-4 py-3 max-w-xs">
                          <div className="font-medium text-white truncate">{inc.title}</div>
                          {inc.has_sla_breach && (
                            <span className="text-xs text-red-400 font-semibold">SLA BREACH</span>
                          )}
                        </td>

                        {/* Severity */}
                        <td className="px-4 py-3">
                          <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium border ${SEVERITY_BADGE[inc.severity]}`}>
                            {inc.severity}
                          </span>
                        </td>

                        {/* Priority */}
                        <td className={`px-4 py-3 text-xs ${PRIORITY_BADGE[inc.priority]}`}>
                          {inc.priority}
                        </td>

                        {/* Status */}
                        <td className="px-4 py-3">
                          <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium border ${STATUS_BADGE[inc.status]}`}>
                            {inc.status}
                          </span>
                        </td>

                        {/* Issue count */}
                        <td className="px-4 py-3 text-gray-400">{inc.issue_count}</td>

                        {/* Owner */}
                        <td className="px-4 py-3 text-gray-400 text-xs">
                          {inc.owner_name ?? '—'}
                        </td>

                        {/* Opened date */}
                        <td className="px-4 py-3 text-gray-500 text-xs">
                          {new Date(inc.opened_at).toLocaleDateString(undefined, {
                            year: 'numeric', month: 'short', day: 'numeric',
                          })}
                        </td>

                        {/* Actions */}
                        {canWrite && (
                          <td className="px-4 py-3 text-right" onClick={e => e.stopPropagation()}>
                            {transitions.length > 0 ? (
                              <select
                                disabled={updatingId === inc.id}
                                value=""
                                onChange={e => {
                                  if (e.target.value) {
                                    handleStatusChange(inc.id, inc.status, e.target.value as IncidentStatus);
                                    e.target.value = '';
                                  }
                                }}
                                className="text-xs px-2 py-1 bg-gray-800 border border-gray-600 rounded text-gray-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-40 cursor-pointer"
                              >
                                <option value="" disabled>Move to…</option>
                                {transitions.map(t => (
                                  <option key={t} value={t}>
                                    {t.charAt(0).toUpperCase() + t.slice(1)}
                                  </option>
                                ))}
                              </select>
                            ) : (
                              <span className="text-xs text-gray-600">—</span>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* ── Pagination ─────────────────────────────────────────── */}
          {(page > 1 || hasNext) && (
            <div className="flex items-center justify-between mt-4 text-sm text-gray-400">
              <button
                disabled={page <= 1}
                onClick={() => goToPage(page - 1)}
                className="flex items-center gap-1 px-3 py-1.5 rounded border border-gray-700 hover:border-gray-500 disabled:opacity-30 transition-colors"
              >
                <ChevronUp className="w-4 h-4 rotate-[-90deg]" />
                Previous
              </button>
              <span>Page {page}</span>
              <button
                disabled={!hasNext}
                onClick={() => goToPage(page + 1)}
                className="flex items-center gap-1 px-3 py-1.5 rounded border border-gray-700 hover:border-gray-500 disabled:opacity-30 transition-colors"
              >
                Next
                <ChevronDown className="w-4 h-4 rotate-[-90deg]" />
              </button>
            </div>
          )}
        </>
      )}

      {/* Detail drawer (C2) */}
      <IncidentDetailDrawer
        workspaceId={workspace_id!}
        incidentId={drawerIncidentId}
        onClose={() => setDrawerIncidentId(null)}
      />
    </div>
  );
}
