/**
 * IncidentDetailDrawer — C2 enterprise incident detail side-drawer.
 *
 * Displays:
 *  - Incident metadata (title, severity, priority, status, owner, creator, dates)
 *  - Linked issues with dataset / rule context
 *  - Activity timeline from workspace audit log (incident_created,
 *    incident_status_changed, incident_assigned, etc.)
 */
import { Fragment, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { X, AlertOctagon, User, Clock, Link2, Activity, ExternalLink, Eye } from 'lucide-react';

import { getIncidentDetail } from '../../services/incidentsService';
import { useTenantScopedPath } from '../../hooks/useTenantScopedPath';
import FaultyRecordsModal from '../common/FaultyRecordsModal';
import type {
  IncidentDetailResponse,
  IncidentSeverity,
  IncidentStatus,
} from '../../services/incidentsService';

interface Props {
  workspaceId: string;
  incidentId: string | null;
  onClose: () => void;
}

const SEV_COLOR: Record<IncidentSeverity, string> = {
  critical: 'bg-red-900/50 text-red-300 border-red-700',
  major: 'bg-orange-900/50 text-orange-300 border-orange-700',
  minor: 'bg-yellow-900/50 text-yellow-300 border-yellow-700',
  informational: 'bg-gray-700/50 text-gray-400 border-gray-600',
};

const STATUS_COLOR: Record<IncidentStatus, string> = {
  open: 'bg-red-900/50 text-red-300 border-red-700',
  acknowledged: 'bg-yellow-900/50 text-yellow-300 border-yellow-700',
  mitigated: 'bg-blue-900/50 text-blue-300 border-blue-700',
  resolved: 'bg-green-900/50 text-green-300 border-green-700',
  closed: 'bg-gray-700/50 text-gray-400 border-gray-600',
  reopened: 'bg-orange-900/50 text-orange-300 border-orange-700',
};

const ACTION_LABEL: Record<string, string> = {
  incident_created: 'Incident created',
  incident_status_changed: 'Status changed',
  incident_owner_changed: 'Owner reassigned',
  incident_assigned: 'Owner assigned',
  incident_link_added: 'Issue linked',
  incident_link_removed: 'Issue unlinked',
};

function fmt(dt: string | null): string {
  if (!dt) return '—';
  try {
    return new Date(dt).toLocaleString();
  } catch {
    return dt;
  }
}

export default function IncidentDetailDrawer({ workspaceId, incidentId, onClose }: Props) {
  const open = incidentId !== null;
  const { wsPath } = useTenantScopedPath();
  const [faultyIssue, setFaultyIssue] = useState<
    | { issueId: string; title: string; subtitle: string }
    | null
  >(null);

  const { data, isLoading, isError } = useQuery<IncidentDetailResponse>({
    queryKey: ['incident-detail', workspaceId, incidentId],
    queryFn: () => getIncidentDetail(workspaceId, incidentId!),
    enabled: open,
    staleTime: 10_000,
  });

  return (
    <Fragment>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/60 z-40 transition-opacity"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Drawer */}
      <aside
        className={`fixed top-0 right-0 h-full w-full sm:w-[600px] bg-gray-900 border-l border-gray-700 shadow-2xl z-50 transform transition-transform duration-200 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
        role="dialog"
        aria-modal="true"
        aria-label="Incident detail"
      >
        {open && (
          <div className="flex flex-col h-full">
            {/* Header */}
            <header className="flex items-start justify-between gap-3 p-5 border-b border-gray-700 bg-gray-800/40">
              <div className="flex items-start gap-3 min-w-0 flex-1">
                <AlertOctagon className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-gray-500 mb-1">Incident</div>
                  <h2 className="text-lg font-semibold text-white truncate" title={data?.title}>
                    {isLoading ? 'Loading…' : data?.title ?? 'Incident'}
                  </h2>
                </div>
              </div>
              <button
                onClick={onClose}
                className="p-1 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
                aria-label="Close drawer"
              >
                <X className="w-5 h-5" />
              </button>
            </header>

            {/* Body */}
            <div className="flex-1 overflow-y-auto p-5 space-y-6">
              {isLoading && (
                <div className="text-sm text-gray-400">Loading incident details…</div>
              )}
              {isError && (
                <div className="rounded-lg border border-red-700 bg-red-900/20 p-3 text-sm text-red-300">
                  Failed to load incident details.
                </div>
              )}

              {data && (
                <>
                  {/* Badges row */}
                  <div className="flex flex-wrap gap-2">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium border ${SEV_COLOR[data.severity]}`}>
                      {data.severity}
                    </span>
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium border ${STATUS_COLOR[data.status]}`}>
                      {data.status}
                    </span>
                    <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium border border-gray-600 text-gray-300">
                      {data.priority}
                    </span>
                  </div>

                  {/* Metadata */}
                  <section>
                    <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2 tracking-wider">
                      Details
                    </h3>
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                      <dt className="text-gray-500 flex items-center gap-1.5"><User className="w-3.5 h-3.5" /> Owner</dt>
                      <dd className="text-gray-200">{data.owner_name ?? '—'}</dd>

                      <dt className="text-gray-500 flex items-center gap-1.5"><User className="w-3.5 h-3.5" /> Created by</dt>
                      <dd className="text-gray-200">{data.created_by_name ?? '—'}</dd>

                      <dt className="text-gray-500 flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" /> Opened</dt>
                      <dd className="text-gray-200">{fmt(data.opened_at)}</dd>

                      {data.acknowledged_at && (
                        <>
                          <dt className="text-gray-500 flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" /> Acknowledged</dt>
                          <dd className="text-gray-200">{fmt(data.acknowledged_at)}</dd>
                        </>
                      )}
                      {data.resolved_at && (
                        <>
                          <dt className="text-gray-500 flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" /> Resolved</dt>
                          <dd className="text-gray-200">{fmt(data.resolved_at)}</dd>
                        </>
                      )}
                      {data.closed_at && (
                        <>
                          <dt className="text-gray-500 flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" /> Closed</dt>
                          <dd className="text-gray-200">{fmt(data.closed_at)}</dd>
                        </>
                      )}
                      {data.external_ticket_id && (
                        <>
                          <dt className="text-gray-500 flex items-center gap-1.5"><ExternalLink className="w-3.5 h-3.5" /> Ticket</dt>
                          <dd className="text-gray-200">
                            {data.external_ticket_url ? (
                              <a href={data.external_ticket_url} target="_blank" rel="noreferrer" className="text-indigo-400 hover:underline">
                                {data.external_ticket_id}
                              </a>
                            ) : (
                              data.external_ticket_id
                            )}
                          </dd>
                        </>
                      )}
                    </dl>
                  </section>

                  {/* Impact / resolution */}
                  {data.impact_summary && (
                    <section>
                      <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2 tracking-wider">
                        Impact
                      </h3>
                      <p className="text-sm text-gray-200 whitespace-pre-wrap">
                        {data.impact_summary}
                      </p>
                    </section>
                  )}
                  {data.resolution_summary && (
                    <section>
                      <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2 tracking-wider">
                        Resolution
                      </h3>
                      <p className="text-sm text-gray-200 whitespace-pre-wrap">
                        {data.resolution_summary}
                      </p>
                    </section>
                  )}

                  {/* Linked issues */}
                  <section>
                    <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2 tracking-wider flex items-center gap-1.5">
                      <Link2 className="w-3.5 h-3.5" />
                      Linked Issues ({data.linked_issues.length})
                    </h3>
                    {data.linked_issues.length === 0 ? (
                      <p className="text-sm text-gray-500">No linked issues.</p>
                    ) : (
                      <ul className="space-y-2">
                        {data.linked_issues.map(iss => (
                          <li
                            key={iss.id}
                            className="rounded-lg border border-gray-700 bg-gray-800/40 p-3 hover:border-gray-600 transition-colors"
                            data-testid={`incident-linked-issue-${iss.id}`}
                          >
                            <div className="flex items-start justify-between gap-2 mb-1">
                              <Link
                                to={wsPath(workspaceId, `/issues/${iss.id}`)}
                                onClick={onClose}
                                className="text-sm text-gray-100 font-medium truncate flex-1 hover:text-purple-300"
                              >
                                {iss.title}
                              </Link>
                              <span className="text-xs text-gray-400 px-1.5 py-0.5 border border-gray-600 rounded">
                                {iss.status}
                              </span>
                            </div>
                            <div className="text-xs text-gray-500 flex flex-wrap gap-x-3 gap-y-1">
                              <span>severity: <span className="text-gray-300">{iss.severity}</span></span>
                              {iss.dataset_name && (
                                <span>dataset: <span className="text-gray-300">{iss.dataset_name}</span></span>
                              )}
                              {iss.rule_name && (
                                <span>rule: <span className="text-gray-300">{iss.rule_name}</span></span>
                              )}
                              {iss.opened_at && (
                                <span>opened: <span className="text-gray-300">{fmt(iss.opened_at)}</span></span>
                              )}
                            </div>
                            <div className="mt-2 flex items-center gap-3 text-[11px]">
                              <Link
                                to={wsPath(workspaceId, `/issues/${iss.id}`)}
                                onClick={onClose}
                                className="text-purple-300 hover:text-purple-200"
                              >
                                Open issue →
                              </Link>
                              <button
                                type="button"
                                onClick={() =>
                                  setFaultyIssue({
                                    issueId: iss.id,
                                    title: `Faulty records · ${iss.title}`,
                                    subtitle: [
                                      iss.dataset_name ?? null,
                                      iss.rule_name ?? null,
                                    ]
                                      .filter(Boolean)
                                      .join(' · '),
                                  })
                                }
                                className="inline-flex items-center gap-1 text-red-300 hover:text-red-200"
                                data-testid={`incident-issue-faulty-${iss.id}`}
                              >
                                <Eye className="w-3 h-3" /> View faulty records
                              </button>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>

                  {/* Activity timeline */}
                  <section>
                    <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2 tracking-wider flex items-center gap-1.5">
                      <Activity className="w-3.5 h-3.5" />
                      Activity ({data.activity.length})
                    </h3>
                    {data.activity.length === 0 ? (
                      <p className="text-sm text-gray-500">No activity recorded.</p>
                    ) : (
                      <ol className="relative border-l border-gray-700 ml-2 space-y-3">
                        {data.activity.map(entry => (
                          <li key={entry.log_id} className="ml-4">
                            <div className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full bg-indigo-500 border-2 border-gray-900" />
                            <div className="text-sm text-gray-200">
                              {ACTION_LABEL[entry.action_type] ?? entry.action_type}
                            </div>
                            <div className="text-xs text-gray-500">
                              {entry.actor_name ?? 'system'}
                              {entry.actor_role ? ` (${entry.actor_role})` : ''}
                              {' · '}
                              {fmt(entry.occurred_at)}
                            </div>
                          </li>
                        ))}
                      </ol>
                    )}
                  </section>
                </>
              )}
            </div>
          </div>
        )}
      </aside>

      <FaultyRecordsModal
        workspaceId={workspaceId}
        source={
          faultyIssue
            ? {
                kind: 'issue',
                issueId: faultyIssue.issueId,
                title: faultyIssue.title,
                subtitle: faultyIssue.subtitle,
              }
            : null
        }
        onClose={() => setFaultyIssue(null)}
      />
    </Fragment>
  );
}
