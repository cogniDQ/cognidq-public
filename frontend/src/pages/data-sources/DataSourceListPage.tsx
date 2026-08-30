import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Plus, ArrowLeft } from 'lucide-react';
import { listDataSources } from '../../services/datasource';
import { getActorId, getActorRole } from '../../utils/jwt';
import { useWorkspacePermissions } from '../../hooks/useWorkspacePermissions';
import type { DataSourceStatus, SourceType, DataSourceEnvironment } from '../../types/dataSource';
import StatusBadge from '../../components/data-sources/StatusBadge';
import TestStatusBadge from '../../components/data-sources/TestStatusBadge';

const SOURCE_TYPES: SourceType[] = ['postgresql', 'mysql', 'mssql', 'oracle', 'snowflake', 'bigquery'];
const ENVIRONMENTS: DataSourceEnvironment[] = ['development', 'staging', 'production'];

export default function DataSourceListPage() {
  const { workspace_id } = useParams<{ workspace_id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();

  const page = parseInt(searchParams.get('page') ?? '1', 10);
  const status = (searchParams.get('status') ?? '') as DataSourceStatus | '';
  const sourceType = (searchParams.get('source_type') ?? '') as SourceType | '';
  const environment = (searchParams.get('environment') ?? '') as DataSourceEnvironment | '';

  const token = localStorage.getItem('access_token');
  const actorId = getActorId(token);
  const actorRole = getActorRole(token);
  const { can } = useWorkspacePermissions(workspace_id, actorId ?? undefined);
  const canWrite = can('datasources:write') || actorRole === 'platform_admin';

  const queryParams = {
    page,
    page_size: 25,
    ...(status ? { status } : {}),
    ...(sourceType ? { source_type: sourceType } : {}),
    ...(environment ? { environment } : {}),
  };

  const { data, isLoading, isError } = useQuery({
    queryKey: ['data-sources', workspace_id, queryParams],
    queryFn: () => listDataSources(workspace_id!, queryParams),
    enabled: !!workspace_id,
    staleTime: 30_000,
  });

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('page');
    setSearchParams(next);
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            to={`/workspaces/${workspace_id}`}
            className="flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Workspace
          </Link>
          <h1 className="text-xl font-semibold text-white">Data Sources</h1>
        </div>
        {canWrite && (
          <Link
            to={`/workspaces/${workspace_id}/data-sources/new`}
            data-testid="create-data-source-btn"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-purple-600 to-blue-600 text-white text-sm font-medium hover:opacity-90 transition-opacity"
          >
            <Plus className="w-4 h-4" />
            New Data Source
          </Link>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select
          value={status}
          onChange={(e) => setParam('status', e.target.value)}
          className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="archived">Archived</option>
        </select>
        <select
          value={sourceType}
          onChange={(e) => setParam('source_type', e.target.value)}
          className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
          aria-label="Filter by source type"
        >
          <option value="">All types</option>
          {SOURCE_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select
          value={environment}
          onChange={(e) => setParam('environment', e.target.value)}
          className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
          aria-label="Filter by environment"
        >
          <option value="">All environments</option>
          {ENVIRONMENTS.map((env) => (
            <option key={env} value={env}>{env}</option>
          ))}
        </select>
      </div>

      {/* Error */}
      {isError && (
        <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400 text-sm">
          Failed to load data sources.
        </div>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <div className="animate-pulse space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 rounded-lg bg-gray-800" />
          ))}
        </div>
      )}

      {/* Table */}
      {!isLoading && !isError && (
        <div
          data-testid="data-source-list"
          className="rounded-2xl border border-gray-700 bg-gray-800/60 overflow-hidden"
        >
          {data?.items && data.items.length === 0 ? (
            <div className="px-6 py-12 text-center text-gray-400 text-sm">
              No data sources found.{' '}
              {canWrite && (
                <Link
                  to={`/workspaces/${workspace_id}/data-sources/new`}
                  className="text-purple-400 hover:text-purple-300"
                >
                  Create one
                </Link>
              )}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left px-5 py-3 text-gray-400 font-medium">Name</th>
                  <th className="text-left px-5 py-3 text-gray-400 font-medium">Type</th>
                  <th className="text-left px-5 py-3 text-gray-400 font-medium">Environment</th>
                  <th className="text-left px-5 py-3 text-gray-400 font-medium">Status</th>
                  <th className="text-left px-5 py-3 text-gray-400 font-medium">Test Status</th>
                </tr>
              </thead>
              <tbody>
                {data?.items?.map((ds) => (
                  <tr
                    key={ds.data_source_id}
                    className="border-b border-gray-700/50 last:border-0 hover:bg-gray-700/30 cursor-pointer transition-colors"
                    onClick={() =>
                      (window.location.href = `/workspaces/${workspace_id}/data-sources/${ds.data_source_id}`)
                    }
                  >
                    <td className="px-5 py-3 text-white font-medium">{ds.source_name}</td>
                    <td className="px-5 py-3 text-gray-300">{ds.source_type}</td>
                    <td className="px-5 py-3 text-gray-300">{ds.environment}</td>
                    <td className="px-5 py-3">
                      <StatusBadge status={ds.status} />
                    </td>
                    <td className="px-5 py-3">
                      <TestStatusBadge status={ds.last_test_status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Pagination */}
      {data?.meta && (
        <div className="flex items-center justify-between text-sm text-gray-400">
          <span>
            {data.meta.total} total
          </span>
          <div className="flex gap-2">
            {page > 1 && (
              <button
                type="button"
                onClick={() => setParam('page', String(page - 1))}
                className="px-3 py-1.5 rounded-lg border border-gray-600 hover:text-white transition-colors"
              >
                Previous
              </button>
            )}
            {data.meta.has_next && (
              <button
                type="button"
                onClick={() => setParam('page', String(page + 1))}
                className="px-3 py-1.5 rounded-lg border border-gray-600 hover:text-white transition-colors"
              >
                Next
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
