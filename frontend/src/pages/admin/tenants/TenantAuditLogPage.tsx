/**
 * TenantAuditLogPage — /admin/tenants/:tenant_id/audit-logs
 *
 * Displays paginated audit log entries for a single tenant.
 * Accessible to platform_admin and platform_viewer only (enforced by AdminGuard).
 *
 * Backend endpoint: GET /api/v1/tenants/{tenant_id}/audit-logs
 */
import { useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, ChevronLeft, ClipboardList } from 'lucide-react';
import { api } from '../../../services/api';

const STALE_TIME = 30_000;
const PAGE_SIZE = 25;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AuditLogEntry {
  log_id: string;
  tenant_id: string;
  event_type: string;
  actor_id: string;
  actor_role: string;
  previous_data: Record<string, unknown> | null;
  new_data: Record<string, unknown> | null;
  occurred_at: string;
  reason: string | null;
}

interface AuditLogResponse {
  data: AuditLogEntry[];
  meta: {
    total: number;
    page: number;
    page_size: number;
    has_next: boolean;
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  } catch {
    return iso;
  }
}

function truncateId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) + '…' : id;
}

async function fetchTenantAuditLogs(
  tenantId: string,
  page: number,
  eventType?: string,
  actorId?: string,
): Promise<AuditLogResponse> {
  const params: Record<string, string | number> = { page, page_size: PAGE_SIZE };
  if (eventType) params.event_type = eventType;
  if (actorId) params.actor_id = actorId;
  const res = await api.get<AuditLogResponse>(`/tenants/${tenantId}/audit-logs`, { params });
  return res.data;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TenantAuditLogPage() {
  const { tenant_id } = useParams<{ tenant_id: string }>();

  const [page, setPage] = useState(1);
  const [eventTypeFilter, setEventTypeFilter] = useState('');
  const [actorIdFilter, setActorIdFilter] = useState('');
  const [appliedEventType, setAppliedEventType] = useState('');
  const [appliedActorId, setAppliedActorId] = useState('');

  const { data, isLoading, isError } = useQuery({
    queryKey: ['tenant-audit-logs', tenant_id, page, appliedEventType, appliedActorId],
    queryFn: () =>
      fetchTenantAuditLogs(
        tenant_id!,
        page,
        appliedEventType || undefined,
        appliedActorId || undefined,
      ),
    staleTime: STALE_TIME,
    enabled: !!tenant_id,
  });

  const handleApplyFilters = useCallback(() => {
    setAppliedEventType(eventTypeFilter.trim());
    setAppliedActorId(actorIdFilter.trim());
    setPage(1);
  }, [eventTypeFilter, actorIdFilter]);

  const handleClearFilters = useCallback(() => {
    setEventTypeFilter('');
    setActorIdFilter('');
    setAppliedEventType('');
    setAppliedActorId('');
    setPage(1);
  }, []);

  const entries = data?.data ?? [];
  const meta = data?.meta;

  return (
    <div data-testid="tenant-audit-log-page">
      {/* Header */}
      <div className="mb-6">
        <Link
          to={`/admin/tenants/${tenant_id}`}
          className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors mb-4"
        >
          <ChevronLeft className="w-4 h-4" aria-hidden="true" />
          Back to Tenant
        </Link>
        <div className="flex items-center gap-3">
          <ClipboardList className="w-6 h-6 text-primary-400" aria-hidden="true" />
          <h1 className="text-2xl font-bold text-white">Audit Logs</h1>
        </div>
        {meta && (
          <p className="text-sm text-gray-400 mt-1">{meta.total} entries total</p>
        )}
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap gap-3 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-400">Event type</label>
          <input
            type="text"
            value={eventTypeFilter}
            onChange={e => setEventTypeFilter(e.target.value)}
            placeholder="e.g. tenant_created"
            className="rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:border-primary-500 focus:outline-none w-48"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-400">Actor ID (UUID)</label>
          <input
            type="text"
            value={actorIdFilter}
            onChange={e => setActorIdFilter(e.target.value)}
            placeholder="actor UUID"
            className="rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:border-primary-500 focus:outline-none w-56"
          />
        </div>
        <button
          onClick={handleApplyFilters}
          className="px-4 py-1.5 rounded-lg bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium transition-colors"
        >
          Apply
        </button>
        {(appliedEventType || appliedActorId) && (
          <button
            onClick={handleClearFilters}
            className="px-4 py-1.5 rounded-lg border border-dark-600 text-gray-400 hover:text-white text-sm transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      {/* Error */}
      {isError && (
        <div role="alert" className="flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400 mb-4">
          <AlertCircle className="w-5 h-5 shrink-0" aria-hidden="true" />
          <span>Failed to load audit logs. Please try again.</span>
        </div>
      )}

      {/* Table */}
      {isLoading ? (
        <div className="space-y-2 animate-pulse">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-12 rounded-lg bg-dark-800/60" />
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-dark-700/60 bg-dark-800/60 overflow-hidden">
          {entries.length === 0 ? (
            <div className="px-6 py-12 text-center text-sm text-gray-500">
              No audit log entries found.
            </div>
          ) : (
            <table className="w-full text-sm" data-testid="audit-log-table">
              <thead>
                <tr className="border-b border-dark-700/60 text-left text-xs text-gray-400 uppercase tracking-wide">
                  <th className="px-4 py-3">Event</th>
                  <th className="px-4 py-3">Actor</th>
                  <th className="px-4 py-3">Role</th>
                  <th className="px-4 py-3">Reason</th>
                  <th className="px-4 py-3">Occurred At</th>
                </tr>
              </thead>
              <tbody>
                {entries.map(entry => (
                  <tr
                    key={entry.log_id}
                    className="border-b border-dark-700/40 hover:bg-dark-700/30 transition-colors"
                  >
                    <td className="px-4 py-3 font-mono text-primary-300">{entry.event_type}</td>
                    <td className="px-4 py-3 font-mono text-gray-300 text-xs">
                      {truncateId(entry.actor_id)}
                    </td>
                    <td className="px-4 py-3 text-gray-400">{entry.actor_role}</td>
                    <td className="px-4 py-3 text-gray-400">{entry.reason ?? '—'}</td>
                    <td className="px-4 py-3 text-gray-400 whitespace-nowrap">
                      {formatDate(entry.occurred_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Pagination */}
      {meta && (meta.page > 1 || meta.has_next) && (
        <div className="mt-4 flex items-center justify-between text-sm text-gray-400">
          <span>
            Page {meta.page} · {meta.total} total
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(p => p - 1)}
              disabled={meta.page <= 1}
              className="px-3 py-1.5 rounded-lg border border-dark-600 hover:bg-dark-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Previous
            </button>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={!meta.has_next}
              className="px-3 py-1.5 rounded-lg border border-dark-600 hover:bg-dark-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
