import { Link, useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, ArrowLeft, Upload } from 'lucide-react';
import { listDatasets } from '../../services/datasetService';
import { listConnections } from '../../services/connectionService';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import { useTenantScopedPath } from '../../hooks/useTenantScopedPath';
import { getActorId, getActorRole } from '../../utils/jwt';
import { useWorkspacePermissions } from '../../hooks/useWorkspacePermissions';
import FileUploadModal from '../../components/datasets/FileUploadModal';
import type { DatasetStatus, DatasetType, Criticality } from '../../types/dataset';

const STATUSES: DatasetStatus[] = ['draft', 'active', 'inactive', 'archived'];
const DATASET_TYPES: DatasetType[] = ['table', 'view', 'file', 'logical'];
const CRITICALITIES: Criticality[] = ['low', 'medium', 'high', 'critical'];

const STATUS_COLORS: Record<DatasetStatus, string> = {
  draft: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30',
  active: 'text-green-400 bg-green-400/10 border-green-400/30',
  inactive: 'text-gray-400 bg-gray-400/10 border-gray-400/30',
  archived: 'text-red-400 bg-red-400/10 border-red-400/30',
};

export default function DatasetListPage() {
  const { workspace_id } = useParams<{ workspace_id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentTenantId } = useWorkspace();
  const { wsPath } = useTenantScopedPath();
  const [uploadOpen, setUploadOpen] = useState(false);

  const page = parseInt(searchParams.get('page') ?? '1', 10);
  const status = (searchParams.get('status') ?? '') as DatasetStatus | '';
  const datasetType = (searchParams.get('dataset_type') ?? '') as DatasetType | '';
  const criticality = (searchParams.get('criticality') ?? '') as Criticality | '';
  const search = searchParams.get('search') ?? '';
  const dataSourceId = searchParams.get('data_source_id') ?? '';

  const token = localStorage.getItem('access_token');
  const actorId = getActorId(token);
  const { can } = useWorkspacePermissions(workspace_id, actorId ?? undefined);
  const actorRole = getActorRole(token);
  const canWrite = can('datasets:write') || actorRole === 'platform_admin' || actorRole === 'tenant_admin';

  const queryParams = {
    page,
    page_size: 25,
    ...(status ? { status } : {}),
    ...(datasetType ? { dataset_type: datasetType } : {}),
    ...(criticality ? { criticality } : {}),
    ...(search ? { search } : {}),
    ...(dataSourceId ? { data_source_id: dataSourceId } : {}),
  };

  const { data, isLoading, isError } = useQuery({
    queryKey: ['datasets', workspace_id, queryParams],
    queryFn: () => listDatasets(workspace_id!, queryParams),
    enabled: !!workspace_id,
    staleTime: 30_000,
  });

  // Connection (data source) filter dropdown options.
  // Restricted to tenant connections authorized to this workspace via
  // control.workspace_connection_assignments (managed on the Connections page).
  const { data: dataSourcesData } = useQuery({
    queryKey: ['data-sources', currentTenantId, workspace_id, 'filter'],
    queryFn: () =>
      listConnections(currentTenantId!, {
        workspace_id,
        page_size: 100,
      }),
    enabled: !!workspace_id && !!currentTenantId,
    staleTime: 60_000,
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
            to={wsPath(workspace_id ?? '', '/overview')}
            className="flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Workspace
          </Link>
          <h1 className="text-xl font-semibold text-white">Datasets</h1>
        </div>
        {canWrite && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setUploadOpen(true)}
              data-testid="upload-file-btn"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-600 text-gray-200 text-sm font-medium hover:bg-gray-800 transition-colors"
            >
              <Upload className="w-4 h-4" />
              Upload File
            </button>
            <Link
              to={wsPath(workspace_id ?? '', '/datasets/new')}
              data-testid="create-dataset-btn"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-purple-600 to-blue-600 text-white text-sm font-medium hover:opacity-90 transition-opacity"
            >
              <Plus className="w-4 h-4" />
              Register Dataset
            </Link>
          </div>
        )}
      </div>

      {uploadOpen && workspace_id && (
        <FileUploadModal
          workspaceId={workspace_id}
          onClose={() => setUploadOpen(false)}
          onCreated={(datasetId) => {
            setUploadOpen(false);
            queryClient.invalidateQueries({ queryKey: ['datasets', workspace_id] });
            navigate(wsPath(workspace_id ?? '', `/datasets/${datasetId}`));
          }}
        />
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select
          value={status}
          onChange={(e) => setParam('status', e.target.value)}
          className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
          aria-label="Filter by status"
          data-testid="status-filter"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={datasetType}
          onChange={(e) => setParam('dataset_type', e.target.value)}
          className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
          aria-label="Filter by type"
          data-testid="type-filter"
        >
          <option value="">All types</option>
          {DATASET_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select
          value={criticality}
          onChange={(e) => setParam('criticality', e.target.value)}
          className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
          aria-label="Filter by criticality"
        >
          <option value="">All criticalities</option>
          {CRITICALITIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select
          value={dataSourceId}
          onChange={(e) => setParam('data_source_id', e.target.value)}
          className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
          aria-label="Filter by connection"
          data-testid="connection-filter"
        >
          <option value="">All connections</option>
          {dataSourcesData?.items?.map((ds) => (
            <option key={ds.connection_id} value={ds.connection_id}>
              {ds.source_name}
            </option>
          ))}
        </select>
        <input
          type="search"
          placeholder="Search datasets…"
          value={search}
          onChange={(e) => setParam('search', e.target.value)}
          className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
          data-testid="search-input"
        />
      </div>

      {/* Error */}
      {isError && (
        <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400 text-sm">
          Failed to load datasets.
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
          data-testid="dataset-list"
          className="rounded-2xl border border-gray-700 bg-gray-800/60 overflow-hidden"
        >
          {data?.items && data.items.length === 0 ? (
            <div className="px-6 py-12 text-center text-gray-400 text-sm">
              No datasets found.{' '}
              {canWrite && (
                <Link
                  to={wsPath(workspace_id ?? '', '/datasets/new')}
                  className="text-purple-400 hover:text-purple-300"
                >
                  Register one
                </Link>
              )}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left px-5 py-3 text-gray-400 font-medium">Name</th>
                  <th className="text-left px-5 py-3 text-gray-400 font-medium">Type</th>
                  <th className="text-left px-5 py-3 text-gray-400 font-medium">Data Source</th>
                  <th className="text-left px-5 py-3 text-gray-400 font-medium">Criticality</th>
                  <th className="text-left px-5 py-3 text-gray-400 font-medium">Status</th>
                  <th className="text-left px-5 py-3 text-gray-400 font-medium">Fields</th>
                </tr>
              </thead>
              <tbody>
                {data?.items?.map((ds) => (
                  <tr
                    key={ds.dataset_id}
                    data-testid={`dataset-row-${ds.dataset_id}`}
                    className="border-b border-gray-700/50 hover:bg-gray-700/30 cursor-pointer transition-colors"
                    onClick={() =>
                      navigate(wsPath(workspace_id ?? '', `/datasets/${ds.dataset_id}`))
                    }
                  >
                    <td className="px-5 py-3 text-white font-medium">{ds.dataset_name}</td>
                    <td className="px-5 py-3 text-gray-300">{ds.dataset_type}</td>
                    <td className="px-5 py-3 text-gray-300">{ds.data_source_name ?? '—'}</td>
                    <td className="px-5 py-3 text-gray-300 capitalize">{ds.criticality}</td>
                    <td className="px-5 py-3">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${STATUS_COLORS[ds.status as DatasetStatus] ?? ''}`}
                      >
                        {ds.status}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-gray-300">{ds.field_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Pagination */}
      {data && data.total > data.page_size && (
        <div className="flex items-center justify-end gap-2 text-sm text-gray-400">
          <button
            disabled={page <= 1}
            onClick={() => setParam('page', String(page - 1))}
            className="px-3 py-1 rounded border border-gray-600 disabled:opacity-40 hover:bg-gray-700 transition-colors"
          >
            Previous
          </button>
          <span>Page {page}</span>
          <button
            disabled={page * data.page_size >= data.total}
            onClick={() => setParam('page', String(page + 1))}
            className="px-3 py-1 rounded border border-gray-600 disabled:opacity-40 hover:bg-gray-700 transition-colors"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
