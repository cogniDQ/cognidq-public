/**
 * F130 — ConnectionListPage
 *
 * Lists all tenant-scoped connections at /hub/connections.
 * "Add Connection" button is visible to tenant_admin only.
 */
import { Link, useParams } from 'react-router-dom';
import { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { listConnections, deleteConnection } from '../../services/connectionService';
import { getTenantId, getActorRole } from '../../utils/jwt';
import { useWorkspace } from '../../contexts/WorkspaceContext';

const CONNECTION_STATUSES = ['active', 'inactive', 'archived'] as const;

const TEST_STATUS_COLORS: Record<string, string> = {
  reachable: 'text-green-400',
  unreachable: 'text-red-400',
  test_failed: 'text-red-400',
  untested: 'text-gray-500',
};

const STATUS_BADGE: Record<string, string> = {
  active: 'bg-green-900/40 text-green-400 border border-green-800',
  inactive: 'bg-dark-700 text-gray-400 border border-dark-600',
  archived: 'bg-dark-700 text-gray-500 border border-dark-600',
};

const ENV_BADGE: Record<string, string> = {
  development: 'bg-blue-900/40 text-blue-400 border border-blue-800',
  staging: 'bg-amber-900/40 text-amber-400 border border-amber-800',
  production: 'bg-purple-900/40 text-purple-400 border border-purple-800',
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

export default function ConnectionListPage() {
  const queryClient = useQueryClient();
  const { tenant_id: urlTenantId } = useParams<{ tenant_id?: string }>();
  const token = localStorage.getItem('access_token');
  const { currentTenantId } = useWorkspace();
  // Prefer tenant_id from the URL (tenant-scoped routes), then the active
  // workspace's tenant, then the JWT tenant claim.
  const tenantId = urlTenantId ?? currentTenantId ?? getTenantId(token);
  const connectionsBase = tenantId ? `/hub/t/${tenantId}/connections` : '/hub/connections';
  const actorRole = getActorRole(token);
  const isAdmin = actorRole === 'tenant_admin' || actorRole === 'platform_admin';

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');

  const queryParams = useMemo(
    () => ({
      page: 1,
      page_size: 25,
      ...(search.trim() ? { search: search.trim() } : {}),
      ...(statusFilter ? { status: statusFilter } : {}),
    }),
    [search, statusFilter],
  );

  const { data, isLoading, isError } = useQuery({
    queryKey: ['connections', tenantId, queryParams],
    queryFn: () => listConnections(tenantId!, queryParams),
    enabled: !!tenantId,
    staleTime: 30_000,
  });

  const connections = data?.items ?? [];

  async function handleArchive(connectionId: string, name: string) {
    if (!window.confirm(`Archive connection "${name}"? This cannot be undone.`)) return;
    try {
      await deleteConnection(tenantId!, connectionId);
      toast.success(`Connection "${name}" archived`);
      queryClient.invalidateQueries({ queryKey: ['connections', tenantId] });
    } catch {
      toast.error('Failed to archive connection. Please try again.');
    }
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold gradient-text">Connections</h1>
          <p className="text-gray-400 mt-1">Manage tenant-wide data source connections</p>
        </div>
        {isAdmin && (
          <Link
            to={`${connectionsBase}/new`}
            className="btn btn-primary flex items-center gap-2"
            data-testid="add-connection-btn"
          >
            <Plus size={16} />
            Add Connection
          </Link>
        )}
      </div>

      {/* Filters */}
      <div className="glass p-4 border border-dark-700 rounded-xl" data-testid="connection-filters">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[240px]">
            <input
              type="search"
              placeholder="Search by name…"
              aria-label="Search connections"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="input w-full pl-10"
              data-testid="connection-search"
            />
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            </span>
          </div>
          <select
            aria-label="Filter by status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="input w-auto min-w-[140px]"
            data-testid="connection-status-filter"
          >
            <option value="">All statuses</option>
            {CONNECTION_STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          {(search || statusFilter) && (
            <button
              type="button"
              onClick={() => { setSearch(''); setStatusFilter(''); }}
              className="text-xs text-gray-500 hover:text-gray-300 underline"
              data-testid="connection-filters-clear"
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-gray-400 text-sm">
          <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/></svg>
          Loading connections…
        </div>
      )}

      {isError && (
        <div className="p-4 rounded-lg bg-red-900/20 border border-red-800 text-red-400 text-sm">
          Failed to load connections.
        </div>
      )}

      {!isLoading && !isError && connections.length === 0 && (
        <div className="card flex flex-col items-center justify-center py-16 gap-3" data-testid="empty-state">
          <svg className="w-10 h-10 text-dark-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18"/></svg>
          <p className="text-gray-400">No connections yet.</p>
          {isAdmin && (
            <Link to={`${connectionsBase}/new`} className="btn btn-primary text-sm">
              Add your first connection
            </Link>
          )}
        </div>
      )}

      {!isLoading && connections.length > 0 && (
        <div className="card overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="connection-table">
              <thead>
                <tr className="border-b border-dark-700 text-left">
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Name</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Type</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500 hidden md:table-cell">Description</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Environment</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Status</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Last Tested</th>
                  {isAdmin && <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-dark-800">
                {connections.map((c) => (
                  <tr
                    key={c.connection_id}
                    className="hover:bg-dark-800/50 transition-colors"
                    data-testid="connection-row"
                  >
                    <td className="px-4 py-3">
                      <Link
                        to={`${connectionsBase}/${c.connection_id}`}
                        className="font-medium text-primary-400 hover:text-primary-300"
                      >
                        {c.source_name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-gray-300 font-mono text-xs">{c.source_type}</td>
                    <td className="px-4 py-3 text-gray-400 max-w-xs truncate hidden md:table-cell">
                      {c.description ?? <span className="italic text-dark-600">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-[11px] uppercase tracking-wide px-2 py-0.5 rounded font-medium ${ENV_BADGE[c.environment] ?? 'text-gray-400'}`}>
                        {c.environment}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-[11px] uppercase tracking-wide px-2 py-0.5 rounded font-medium ${STATUS_BADGE[c.status] ?? 'text-gray-400 border border-dark-600'}`}>
                        {c.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`${TEST_STATUS_COLORS[c.last_test_status ?? 'untested'] ?? 'text-gray-500'} text-xs`}>
                        {c.last_test_status ?? 'untested'}
                      </span>
                      {c.last_tested_at && (
                        <span className="ml-1 text-gray-500 text-[11px]">
                          {formatDate(c.last_tested_at)}
                        </span>
                      )}
                    </td>
                    {isAdmin && (
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <Link
                            to={`${connectionsBase}/${c.connection_id}/edit`}
                            className="text-gray-500 hover:text-primary-400 transition-colors"
                            title="Edit connection"
                            data-testid="edit-connection-btn"
                          >
                            <Pencil size={14} />
                          </Link>
                          <button
                            onClick={() => handleArchive(c.connection_id, c.source_name)}
                            className="text-gray-500 hover:text-red-400 transition-colors"
                            title="Archive connection"
                            data-testid="archive-connection-btn"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
