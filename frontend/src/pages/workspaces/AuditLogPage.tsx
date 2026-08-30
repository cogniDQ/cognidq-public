/**
 * F082 — Activity Log Page
 *
 * Displays the full workspace audit/activity log using the F053 backend
 * endpoints (GET /workspaces/{ws}/audit/logs and /audit/logs/export).
 *
 * Distinct from PermissionAuditPage (F008) which shows only RBAC-specific
 * access-control events via /audit/permissions. This page shows ALL workspace
 * events: dataset changes, rule edits, execution triggers, member changes, etc.
 *
 * Access: workspace_administrator only (view_audit_logs permission).
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  Download,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ChevronDown,
} from 'lucide-react';
import {
  listAuditLogs,
  buildAuditLogExportUrl,
  type AuditLogEntry,
  type AuditLogPage,
  type AuditLogFilters,
} from '../../services/auditLogService';

const PAGE_SIZE = 50;

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function extractFilters(params: URLSearchParams): AuditLogFilters {
  return {
    action_type: params.get('action_type') ?? undefined,
    entity_type: params.get('entity_type') ?? undefined,
    actor_id: params.get('actor_id') ?? undefined,
    from_date: params.get('from_date') ?? undefined,
    to_date: params.get('to_date') ?? undefined,
    sort_dir: (params.get('sort_dir') ?? 'desc') as 'asc' | 'desc',
  };
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: 'short',
      timeStyle: 'short',
    });
  } catch {
    return iso;
  }
}

function truncateId(id: string | null): string {
  if (!id) return '—';
  return id.length > 8 ? id.slice(0, 8) + '…' : id;
}

// ─────────────────────────────────────────────────────────────────────────────
// Filter Bar
// ─────────────────────────────────────────────────────────────────────────────

interface FilterBarProps {
  filters: AuditLogFilters;
  onChange: (f: AuditLogFilters) => void;
}

function FilterBar({ filters, onChange }: FilterBarProps) {
  const [local, setLocal] = useState<AuditLogFilters>(filters);

  // sync when URL changes externally
  useEffect(() => { setLocal(filters); }, [filters]);

  const set = (key: keyof AuditLogFilters, value: string) =>
    setLocal(prev => ({ ...prev, [key]: value || undefined }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onChange(local);
  };

  const handleClear = () => {
    const cleared: AuditLogFilters = { sort_dir: 'desc' };
    setLocal(cleared);
    onChange(cleared);
  };

  const hasFilters =
    local.action_type || local.entity_type || local.actor_id ||
    local.from_date || local.to_date;

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-wrap gap-3 items-end"
      data-testid="audit-log-filter-bar"
    >
      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-400">Action type</label>
        <input
          type="text"
          value={local.action_type ?? ''}
          onChange={e => set('action_type', e.target.value)}
          placeholder="e.g. rule.created"
          className="rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none w-44"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-400">Entity type</label>
        <input
          type="text"
          value={local.entity_type ?? ''}
          onChange={e => set('entity_type', e.target.value)}
          placeholder="e.g. dataset"
          className="rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none w-36"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-400">Actor ID</label>
        <input
          type="text"
          value={local.actor_id ?? ''}
          onChange={e => set('actor_id', e.target.value)}
          placeholder="User ID"
          className="rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none w-36"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-400">From</label>
        <input
          type="date"
          value={local.from_date ?? ''}
          onChange={e => set('from_date', e.target.value)}
          className="rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none w-36"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-400">To</label>
        <input
          type="date"
          value={local.to_date ?? ''}
          onChange={e => set('to_date', e.target.value)}
          className="rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none w-36"
        />
      </div>

      <button
        type="submit"
        className="rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
      >
        Search
      </button>

      {hasFilters && (
        <button
          type="button"
          onClick={handleClear}
          className="rounded-lg border border-dark-600 px-3 py-1.5 text-sm text-gray-400 hover:text-white transition-colors"
        >
          Clear
        </button>
      )}
    </form>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Results Table
// ─────────────────────────────────────────────────────────────────────────────

interface TableProps {
  items: AuditLogEntry[];
  sortDir: 'asc' | 'desc';
  onSortToggle: () => void;
  isLoading: boolean;
}

function AuditLogTable({ items, sortDir, onSortToggle, isLoading }: TableProps) {
  const SortIcon = sortDir === 'desc' ? ChevronDown : ChevronUp;

  if (isLoading) {
    return (
      <div className="space-y-2" data-testid="audit-log-loading">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-10 rounded-lg bg-dark-700 animate-pulse" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div
        className="rounded-xl border border-dark-600 bg-dark-800 px-6 py-12 text-center text-gray-400"
        data-testid="audit-log-empty"
      >
        No audit log entries match the current filters.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-dark-600" data-testid="audit-log-table">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-dark-600 bg-dark-700 text-left text-xs text-gray-400 uppercase tracking-wider">
            <th className="px-4 py-3">
              <button
                type="button"
                onClick={onSortToggle}
                className="flex items-center gap-1 hover:text-white transition-colors"
                data-testid="sort-toggle"
              >
                When
                <SortIcon className="w-3 h-3" aria-hidden="true" />
              </button>
            </th>
            <th className="px-4 py-3">Action</th>
            <th className="px-4 py-3">Entity type</th>
            <th className="px-4 py-3">Entity ID</th>
            <th className="px-4 py-3">Actor</th>
            <th className="px-4 py-3">Role</th>
            <th className="px-4 py-3">Request</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-dark-600">
          {items.map(entry => (
            <tr
              key={entry.log_id}
              className="bg-dark-800 hover:bg-dark-700 transition-colors"
              data-testid="audit-log-row"
            >
              <td className="px-4 py-3 text-gray-300 whitespace-nowrap">
                {formatDate(entry.occurred_at)}
              </td>
              <td className="px-4 py-3">
                <span className="rounded-md bg-blue-500/10 px-2 py-0.5 text-xs font-mono text-blue-300">
                  {entry.action_type ?? '—'}
                </span>
              </td>
              <td className="px-4 py-3 text-gray-300 font-mono text-xs">
                {entry.target_entity_type ?? '—'}
              </td>
              <td
                className="px-4 py-3 text-gray-400 font-mono text-xs"
                title={entry.target_entity_id ?? undefined}
              >
                {truncateId(entry.target_entity_id)}
              </td>
              <td className="px-4 py-3">
                <div className="text-sm text-white leading-tight">
                  {entry.actor_display_name ?? '—'}
                </div>
                {entry.actor_id && (
                  <div
                    className="text-xs text-gray-500 font-mono"
                    title={entry.actor_id}
                  >
                    {truncateId(entry.actor_id)}
                  </div>
                )}
              </td>
              <td className="px-4 py-3 text-gray-400 text-xs capitalize">
                {entry.actor_role ?? '—'}
              </td>
              <td
                className="px-4 py-3 text-gray-500 font-mono text-xs"
                title={entry.request_id ?? undefined}
              >
                {truncateId(entry.request_id)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

export default function AuditLogPage() {
  const { workspace_id } = useParams<{ workspace_id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();

  const [data, setData] = useState<AuditLogPage | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  const filters = extractFilters(searchParams);
  const currentPage = Number(searchParams.get('page') ?? '1');
  const sortDir = (searchParams.get('sort_dir') ?? 'desc') as 'asc' | 'desc';

  const load = useCallback(async () => {
    if (!workspace_id) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await listAuditLogs(
        workspace_id,
        extractFilters(searchParams),
        Number(searchParams.get('page') ?? '1'),
        PAGE_SIZE,
      );
      setData(result);
    } catch {
      setError('Failed to load activity log. Please try again.');
    } finally {
      setIsLoading(false);
    }
   
  }, [workspace_id, searchParams.toString()]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleFiltersChange = (newFilters: AuditLogFilters) => {
    const next = new URLSearchParams();
    for (const [k, v] of Object.entries(newFilters)) {
      if (v !== undefined && v !== '') next.set(k, v as string);
    }
    next.set('page', '1');
    if (!newFilters.sort_dir) next.set('sort_dir', 'desc');
    setSearchParams(next, { replace: true });
  };

  const handleSortToggle = () => {
    const next = new URLSearchParams(searchParams);
    next.set('sort_dir', sortDir === 'desc' ? 'asc' : 'desc');
    next.set('page', '1');
    setSearchParams(next, { replace: true });
  };

  const handlePageChange = (delta: number) => {
    const next = new URLSearchParams(searchParams);
    next.set('page', String(currentPage + delta));
    setSearchParams(next, { replace: true });
  };

  const handleExport = async () => {
    if (!workspace_id || isExporting) return;
    setIsExporting(true);
    try {
      const exportFilters: AuditLogFilters = {
        action_type: filters.action_type,
        entity_type: filters.entity_type,
        actor_id: filters.actor_id,
        from_date: filters.from_date,
        to_date: filters.to_date,
      };
      const url = buildAuditLogExportUrl(workspace_id, exportFilters);
      const token = localStorage.getItem('access_token');
      const response = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error(`Export failed: ${response.status}`);
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = `activity-log-${workspace_id}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(objectUrl);
    } catch {
      setError('Export failed. Please try again.');
    } finally {
      setIsExporting(false);
    }
  };

  const paginationStart = data ? Math.min((currentPage - 1) * PAGE_SIZE + 1, data.total) : 0;
  const paginationEnd = data ? Math.min(currentPage * PAGE_SIZE, data.total) : 0;

  return (
    <div className="space-y-6" data-testid="activity-log-page">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-white">Activity Log</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            Full workspace audit trail — datasets, rules, executions, members, and more
          </p>
        </div>

        <button
          type="button"
          onClick={() => { void handleExport(); }}
          disabled={isExporting}
          data-testid="export-csv-btn"
          className="flex items-center gap-1.5 rounded-lg border border-dark-600 px-3 py-1.5 text-sm text-gray-300 hover:text-white disabled:opacity-50 transition-colors"
        >
          <Download className="w-4 h-4" aria-hidden="true" />
          {isExporting ? 'Exporting…' : 'Export CSV'}
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400"
          data-testid="audit-log-error-banner"
        >
          <AlertCircle className="w-5 h-5 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {/* Filters */}
      <FilterBar filters={filters} onChange={handleFiltersChange} />

      {/* Summary */}
      {data && !isLoading && (
        <p className="text-sm text-gray-400" data-testid="audit-log-summary">
          {data.total.toLocaleString()} {data.total === 1 ? 'entry' : 'entries'} found
        </p>
      )}

      {/* Table */}
      <AuditLogTable
        items={data?.items ?? []}
        sortDir={sortDir}
        onSortToggle={handleSortToggle}
        isLoading={isLoading}
      />

      {/* Pagination */}
      {data && data.total > PAGE_SIZE && (
        <div
          className="flex items-center justify-between text-sm text-gray-400"
          data-testid="pagination-controls"
        >
          <span>
            {paginationStart}–{paginationEnd} of {data.total.toLocaleString()}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => handlePageChange(-1)}
              disabled={currentPage <= 1}
              data-testid="pagination-prev"
              className="flex items-center gap-1 rounded-lg border border-dark-600 px-3 py-1.5 hover:text-white disabled:opacity-40 transition-colors"
            >
              <ChevronLeft className="w-4 h-4" aria-hidden="true" />
              Prev
            </button>
            <button
              type="button"
              onClick={() => handlePageChange(1)}
              disabled={!data.has_next}
              data-testid="pagination-next"
              className="flex items-center gap-1 rounded-lg border border-dark-600 px-3 py-1.5 hover:text-white disabled:opacity-40 transition-colors"
            >
              Next
              <ChevronRight className="w-4 h-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
