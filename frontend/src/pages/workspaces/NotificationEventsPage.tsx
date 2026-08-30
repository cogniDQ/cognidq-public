/**
 * NotificationEventsPage — workspace-scoped notification delivery log (F081)
 *
 * Route: /hub/ws/:workspace_id/notification-events
 *
 * Features:
 *   - Summary stat cards (pending / sent / failed / retrying)
 *   - Filterable event list by status
 *   - Auto-refreshes every 30 s (delivery status changes over time)
 *   - Paginated via offset/limit
 */
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Bell, RefreshCw, AlertTriangle, CheckCircle2, Clock, RotateCcw, X } from 'lucide-react';
import EmptyState from '../../components/common/EmptyState';

import {
  listNotificationEvents,
  getNotificationEventSummary,
  NOTIFICATION_STATUSES,
  STATUS_LABELS,
} from '../../services/notificationEventsService';
import type { NotificationEvent, NotificationStatus } from '../../services/notificationEventsService';

// ─────────────────────────────────────────────────────────────────────────────
// Style maps
// ─────────────────────────────────────────────────────────────────────────────

const STATUS_BADGE: Record<NotificationStatus, string> = {
  pending:  'bg-yellow-900/50 text-yellow-300 border-yellow-700',
  sent:     'bg-green-900/50 text-green-300 border-green-700',
  failed:   'bg-red-900/50 text-red-300 border-red-700',
  retrying: 'bg-blue-900/50 text-blue-300 border-blue-700',
};

const STATUS_ICON: Record<NotificationStatus, React.ReactNode> = {
  pending:  <Clock className="h-3.5 w-3.5" />,
  sent:     <CheckCircle2 className="h-3.5 w-3.5" />,
  failed:   <AlertTriangle className="h-3.5 w-3.5" />,
  retrying: <RotateCcw className="h-3.5 w-3.5" />,
};

const STAT_CARD_COLOR: Record<NotificationStatus, string> = {
  pending:  'border-yellow-700/50 bg-yellow-900/10',
  sent:     'border-green-700/50 bg-green-900/10',
  failed:   'border-red-700/50 bg-red-900/10',
  retrying: 'border-blue-700/50 bg-blue-900/10',
};

const PAGE_SIZE = 50;
const REFRESH_INTERVAL = 30_000;

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export default function NotificationEventsPage() {
  const { workspace_id } = useParams<{ workspace_id: string }>();
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [page, setPage] = useState(0); // offset-based: page * PAGE_SIZE
  // F4 — detail drawer
  const [selectedEvent, setSelectedEvent] = useState<NotificationEvent | null>(null);

  const offset = page * PAGE_SIZE;

  // Summary stats
  const {
    data: summary,
    isLoading: summaryLoading,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['notification-events-summary', workspace_id],
    queryFn: () => getNotificationEventSummary(workspace_id!),
    enabled: !!workspace_id,
    staleTime: REFRESH_INTERVAL,
    refetchInterval: REFRESH_INTERVAL,
  });

  // Event list
  const {
    data: events = [],
    isLoading: eventsLoading,
    isError,
    refetch: refetchEvents,
  } = useQuery({
    queryKey: ['notification-events', workspace_id, statusFilter, offset],
    queryFn: () =>
      listNotificationEvents(workspace_id!, {
        status: statusFilter || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    enabled: !!workspace_id,
    staleTime: REFRESH_INTERVAL,
    refetchInterval: REFRESH_INTERVAL,
  });

  function handleRefresh() {
    refetchSummary();
    refetchEvents();
  }

  function handleStatusFilter(s: string) {
    setStatusFilter(s);
    setPage(0);
  }

  const hasMore = events.length === PAGE_SIZE;

  return (
    <div className="min-h-screen bg-gray-950 p-6 text-white">
      {/* Page header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bell className="h-6 w-6 text-blue-400" />
          <h1 className="text-2xl font-bold text-white">Notification Events</h1>
        </div>
        <button
          onClick={handleRefresh}
          title="Refresh"
          className="flex items-center gap-2 rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-300 hover:border-gray-500 hover:text-white transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Summary cards */}
      {!summaryLoading && summary && (
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {NOTIFICATION_STATUSES.map(s => (
            <button
              key={s}
              onClick={() => handleStatusFilter(statusFilter === s ? '' : s)}
              className={`rounded-lg border p-4 text-left transition-all ${
                STAT_CARD_COLOR[s]
              } ${
                statusFilter === s
                  ? 'ring-2 ring-blue-500'
                  : 'hover:brightness-110'
              }`}
            >
              <div className="mb-1 text-2xl font-bold text-white">
                {summary[s]}
              </div>
              <div className="text-sm capitalize text-gray-400">{STATUS_LABELS[s]}</div>
            </button>
          ))}
        </div>
      )}

      {/* Status filter bar */}
      <div className="mb-4 flex items-center gap-2">
        <span className="text-sm text-gray-500">Filter:</span>
        <button
          onClick={() => handleStatusFilter('')}
          className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
            statusFilter === ''
              ? 'bg-blue-600 text-white'
              : 'bg-gray-800 text-gray-400 hover:text-white border border-gray-700'
          }`}
        >
          All
        </button>
        {NOTIFICATION_STATUSES.map(s => (
          <button
            key={s}
            onClick={() => handleStatusFilter(s)}
            className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
              statusFilter === s
                ? 'bg-blue-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-white border border-gray-700'
            }`}
          >
            {STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      {/* Event table */}
      {eventsLoading && (
        <p className="text-sm text-gray-500">Loading notification events…</p>
      )}
      {isError && (
        <EmptyState
          variant="error"
          title="Couldn't load notification events"
          description="We couldn't reach the notification log service. Try again or check your connection."
          onRetry={() => refetchEvents()}
          testId="notif-events-error"
        />
      )}
      {!eventsLoading && !isError && events.length === 0 && (
        <EmptyState
          icon={Bell}
          title={statusFilter
            ? `No ${STATUS_LABELS[statusFilter as NotificationStatus]} events`
            : 'No notifications dispatched yet'}
          description={statusFilter
            ? 'Try clearing the status filter to see other events.'
            : 'When alert rules fire, the dispatcher will send notifications and log every attempt here. Configure rules and channels in Alerts to start delivering.'}
          primaryAction={statusFilter ? {
            label: 'Show all events',
            onClick: () => handleStatusFilter(''),
          } : {
            label: 'Configure Alerts',
            to: wsPath(workspace_id ?? '', '/alerts'),
            icon: Bell,
          }}
          testId="notif-events-empty"
        />
      )}
      {!eventsLoading && events.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-gray-700">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 bg-gray-900">
                <th className="px-4 py-3 text-left font-medium text-gray-400">Status</th>
                <th className="px-4 py-3 text-left font-medium text-gray-400">Recipient</th>
                <th className="px-4 py-3 text-left font-medium text-gray-400">Rule ID</th>
                <th className="px-4 py-3 text-left font-medium text-gray-400">Channel ID</th>
                <th className="px-4 py-3 text-left font-medium text-gray-400">Retries</th>
                <th className="px-4 py-3 text-left font-medium text-gray-400">Error</th>
                <th className="px-4 py-3 text-left font-medium text-gray-400">Created</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev, i) => (
                <tr
                  key={ev.id}
                  onClick={() => setSelectedEvent(ev)}
                  data-testid={`notification-row-${ev.id}`}
                  className={`cursor-pointer border-b border-gray-800 transition-colors hover:bg-gray-800/40 ${
                    i % 2 === 0 ? 'bg-gray-900/30' : 'bg-gray-900/10'
                  }`}
                >
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[ev.status]}`}>
                      {STATUS_ICON[ev.status]}
                      {STATUS_LABELS[ev.status]}
                    </span>
                  </td>
                  <td className="max-w-[180px] truncate px-4 py-3 text-gray-200">
                    {ev.recipient}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-500" title={ev.alert_rule_id}>
                    {ev.alert_rule_id.slice(0, 8)}…
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-500" title={ev.alert_channel_id}>
                    {ev.alert_channel_id.slice(0, 8)}…
                  </td>
                  <td className="px-4 py-3 text-gray-400">
                    {ev.retry_count}
                    {ev.retry_count > 0 && (
                      <span className="text-gray-600">/{ev.max_retries}</span>
                    )}
                  </td>
                  <td className="max-w-[220px] truncate px-4 py-3 text-xs text-red-400" title={ev.last_error ?? ''}>
                    {ev.last_error ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {new Date(ev.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {(page > 0 || hasMore) && (
        <div className="mt-4 flex items-center justify-between">
          <button
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
            className="rounded border border-gray-700 bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:border-gray-500 hover:text-white disabled:opacity-40 transition-colors"
          >
            ← Previous
          </button>
          <span className="text-sm text-gray-500">Page {page + 1}</span>
          <button
            onClick={() => setPage(p => p + 1)}
            disabled={!hasMore}
            className="rounded border border-gray-700 bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:border-gray-500 hover:text-white disabled:opacity-40 transition-colors"
          >
            Next →
          </button>
        </div>
      )}

      {/* F4 — Event detail drawer */}
      {selectedEvent && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/50"
          onClick={() => setSelectedEvent(null)}
          data-testid="notification-detail-overlay"
        >
          <div
            className="h-full w-full max-w-xl overflow-y-auto border-l border-gray-700 bg-gray-950 p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
            data-testid="notification-detail-drawer"
          >
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Notification event</h3>
              <button
                onClick={() => setSelectedEvent(null)}
                className="rounded p-1 text-gray-400 hover:bg-gray-800 hover:text-white"
                aria-label="Close"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
              <dt className="text-gray-500">Event ID</dt>
              <dd className="font-mono text-gray-200 break-all">{selectedEvent.id}</dd>
              <dt className="text-gray-500">Status</dt>
              <dd>
                <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium ${STATUS_BADGE[selectedEvent.status]}`}>
                  {STATUS_ICON[selectedEvent.status]}
                  {STATUS_LABELS[selectedEvent.status]}
                </span>
              </dd>
              <dt className="text-gray-500">Recipient</dt>
              <dd className="text-gray-200 break-all">{selectedEvent.recipient}</dd>
              <dt className="text-gray-500">Rule ID</dt>
              <dd className="font-mono text-gray-200 break-all">{selectedEvent.alert_rule_id}</dd>
              <dt className="text-gray-500">Channel ID</dt>
              <dd className="font-mono text-gray-200 break-all">{selectedEvent.alert_channel_id}</dd>
              <dt className="text-gray-500">Retries</dt>
              <dd className="text-gray-200">
                {selectedEvent.retry_count} / {selectedEvent.max_retries}
              </dd>
              <dt className="text-gray-500">Created</dt>
              <dd className="text-gray-200">
                {new Date(selectedEvent.created_at).toLocaleString()}
              </dd>
              <dt className="text-gray-500">Sent at</dt>
              <dd className="text-gray-200">
                {selectedEvent.sent_at ? new Date(selectedEvent.sent_at).toLocaleString() : '—'}
              </dd>
              <dt className="text-gray-500">Delivered at</dt>
              <dd className="text-gray-200">
                {selectedEvent.delivered_at
                  ? new Date(selectedEvent.delivered_at).toLocaleString()
                  : '—'}
              </dd>
              <dt className="text-gray-500">Updated</dt>
              <dd className="text-gray-200">
                {new Date(selectedEvent.updated_at).toLocaleString()}
              </dd>
            </dl>

            {selectedEvent.last_error && (
              <div className="mt-4">
                <h4 className="mb-1 text-xs uppercase tracking-wide text-gray-500">
                  Last error
                </h4>
                <pre className="whitespace-pre-wrap rounded border border-red-800 bg-red-900/20 p-3 text-xs text-red-300">
                  {selectedEvent.last_error}
                </pre>
              </div>
            )}

            <div className="mt-4">
              <h4 className="mb-1 text-xs uppercase tracking-wide text-gray-500">
                Payload
              </h4>
              <pre
                className="max-h-96 overflow-auto rounded border border-gray-700 bg-gray-900 p-3 text-[11px] text-gray-300"
                data-testid="notification-detail-payload"
              >
                {selectedEvent.payload
                  ? JSON.stringify(selectedEvent.payload, null, 2)
                  : '— (no payload)'}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
