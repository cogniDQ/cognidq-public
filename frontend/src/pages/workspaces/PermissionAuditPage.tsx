/**
 * F008 — Permission Audit Visibility
 * PermissionAuditPage — page container. Route: /workspaces/:workspace_id/audit
 *
 * Responsibilities:
 *   - Reads filter parameters and page/sort_dir from URLSearchParams (React Router).
 *   - Calls permissionAuditService.fetchEntries on every dependency change.
 *   - Propagates filter changes back to the URL via setSearchParams (replaces history entry).
 *   - Renders PermissionAuditFilters + PermissionAuditTable + pagination + Export CSV button.
 *
 * Export CSV:
 *   Uses fetch() + Blob + URL.createObjectURL() to carry the Authorization header.
 *   window.location.href is explicitly NOT used (see TDD TA-007).
 *
 * Access: Accessible to users with the view_audit_logs workspace permission.
 * The backend enforces RBAC; the frontend renders for any authenticated user
 * who reaches this route, relying on the API to return 403 when denied.
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { AlertCircle, Download } from 'lucide-react';

import type { AuditFilters } from '../../services/permissionAuditService';
import { buildExportUrl, fetchEntries } from '../../services/permissionAuditService';
import type { PermissionAuditPage as AuditPageData } from '../../types/audit';
import PermissionAuditFilters from '../../components/audit/PermissionAuditFilters';
import PermissionAuditTable from '../../components/audit/PermissionAuditTable';

const PAGE_SIZE = 25;

/** Extract AuditFilters from URLSearchParams. */
function extractFilters(params: URLSearchParams): AuditFilters {
  return {
    actor_id: params.get('actor_id') ?? undefined,
    action_type: params.get('action_type') ?? undefined,
    target_entity_id: params.get('target_entity_id') ?? undefined,
    target_entity_type: params.get('target_entity_type') ?? undefined,
    from_date: params.get('from_date') ?? undefined,
    to_date: params.get('to_date') ?? undefined,
    sort_dir: params.get('sort_dir') ?? 'desc',
  };
}

export default function PermissionAuditPage() {
  const { workspace_id } = useParams<{ workspace_id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();

  const [data, setData] = useState<AuditPageData | null>(null);
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
      const result = await fetchEntries(
        workspace_id,
        extractFilters(searchParams),
        Number(searchParams.get('page') ?? '1'),
        PAGE_SIZE,
      );
      setData(result);
    } catch {
      setError('Failed to load permission audit log. Please try again.');
    } finally {
      setIsLoading(false);
    }
   
  }, [workspace_id, searchParams.toString()]);

  useEffect(() => {
    void load();
  }, [load]);

  /** Merge new filters into URL params and reset page to 1. */
  const handleFiltersChange = (newFilters: AuditFilters) => {
    const next = new URLSearchParams();
    for (const [k, v] of Object.entries(newFilters)) {
      if (v !== undefined && v !== '') next.set(k, v);
    }
    next.set('page', '1');
    if (!newFilters.sort_dir) next.set('sort_dir', 'desc');
    setSearchParams(next, { replace: true });
  };

  /** Toggle sort direction in URL and reset page to 1. */
  const handleSortToggle = () => {
    const next = new URLSearchParams(searchParams);
    next.set('sort_dir', sortDir === 'desc' ? 'asc' : 'desc');
    next.set('page', '1');
    setSearchParams(next, { replace: true });
  };

  /** Advance or retreat pagination by delta pages. */
  const handlePageChange = (delta: number) => {
    const next = new URLSearchParams(searchParams);
    next.set('page', String(currentPage + delta));
    setSearchParams(next, { replace: true });
  };

  /**
   * Export CSV via fetch() + Blob + URL.createObjectURL().
   * This pattern is required because auth is carried in the Authorization header
   * and cannot be passed via URL navigation (TA-007).
   */
  const handleExport = async () => {
    if (!workspace_id || isExporting) return;
    setIsExporting(true);
    try {
      const exportFilters: AuditFilters = {
        actor_id: filters.actor_id,
        action_type: filters.action_type,
        target_entity_id: filters.target_entity_id,
        target_entity_type: filters.target_entity_type,
        from_date: filters.from_date,
        to_date: filters.to_date,
      };
      const url = buildExportUrl(workspace_id, exportFilters);
      const token = localStorage.getItem('access_token');
      const response = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error(`Export failed: ${response.status}`);
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = `permission-audit-${workspace_id}.csv`;
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
    <div className="space-y-6" data-testid="permission-audit-page">
      {/* Page header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-white">Permission Audit Log</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            Access-control changes for this workspace
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
          data-testid="audit-error-banner"
        >
          <AlertCircle className="w-5 h-5 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {/* Filters */}
      <PermissionAuditFilters filters={filters} onFiltersChange={handleFiltersChange} />

      {/* Table */}
      <PermissionAuditTable
        items={data?.items ?? []}
        sortDir={sortDir}
        onSortToggle={handleSortToggle}
        isLoading={isLoading}
      />

      {/* Pagination */}
      {data && data.total > 0 && (
        <div
          className="flex items-center justify-between text-sm text-gray-400"
          data-testid="pagination-controls"
        >
          <span>
            Showing {paginationStart}–{paginationEnd} of {data.total}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => handlePageChange(-1)}
              disabled={currentPage <= 1}
              data-testid="prev-page-btn"
              className="rounded-lg border border-dark-600 px-3 py-1 disabled:opacity-40 hover:text-white transition-colors"
            >
              Prev
            </button>
            <button
              type="button"
              onClick={() => handlePageChange(1)}
              disabled={!data.has_next}
              data-testid="next-page-btn"
              className="rounded-lg border border-dark-600 px-3 py-1 disabled:opacity-40 hover:text-white transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
