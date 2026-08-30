import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { ArrowLeft, Edit, Zap } from 'lucide-react';
import { getDataSource, testConnection } from '../../services/datasource';
import type { DataSourceDetailResponse } from '../../types/dataSource';
import { getActorRole } from '../../utils/jwt';
import StatusBadge from '../../components/data-sources/StatusBadge';
import TestStatusBadge from '../../components/data-sources/TestStatusBadge';
import ArchiveModal from '../../components/data-sources/ArchiveModal';
import RestoreModal from '../../components/data-sources/RestoreModal';
import AuditLogPanel from '../../components/data-sources/AuditLogPanel';
import { useTenantScopedPath } from '../../hooks/useTenantScopedPath';

export default function DataSourceDetailPage() {
  const { workspace_id, data_source_id } = useParams<{
    workspace_id: string;
    data_source_id: string;
  }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { wsPath } = useTenantScopedPath();

  const [showArchiveModal, setShowArchiveModal] = useState(false);
  const [showRestoreModal, setShowRestoreModal] = useState(false);

  const token = localStorage.getItem('access_token');
  const role = getActorRole(token);
  const canWrite = role === 'workspace_administrator' || role === 'data_engineer' || role === 'platform_admin';

  const queryKey = ['data-source', workspace_id, data_source_id];

  const { data: ds, isLoading, isError } = useQuery({
    queryKey,
    queryFn: () => getDataSource(workspace_id!, data_source_id!),
    enabled: !!(workspace_id && data_source_id),
    staleTime: 30_000,
  });

  const testMutation = useMutation({
    mutationFn: () => testConnection(workspace_id!, data_source_id!),
    onSuccess: (result) => {
      // Immediately update the badge without waiting for the refetch
      qc.setQueryData<DataSourceDetailResponse>(queryKey, (old) =>
        old ? { ...old, last_test_status: result.status, last_tested_at: result.tested_at } : old
      );
      qc.invalidateQueries({ queryKey });
      toast.success('Connection test complete');
    },
    onError: () => {
      toast.error('Connection test failed');
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-8 w-48 rounded-lg bg-gray-800" />
        <div className="h-48 rounded-2xl bg-gray-800/60" />
      </div>
    );
  }

  if (isError || !ds) {
    return (
      <div>
        <button
          type="button"
          onClick={() => navigate(wsPath(workspace_id!, '/data-sources'))}
          className="mb-4 flex items-center gap-1 text-sm text-gray-400 hover:text-white"
        >
          <ArrowLeft className="w-4 h-4" />
          Data Sources
        </button>
        <div
          role="alert"
          className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400 text-sm"
        >
          Failed to load data source.
        </div>
      </div>
    );
  }

  const isArchived = ds.status === 'archived';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            to={`/workspaces/${workspace_id}/data-sources`}
            className="flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Data Sources
          </Link>
          <h1 className="text-xl font-semibold text-white">{ds.source_name}</h1>
        </div>

        {canWrite && (
          <div className="flex gap-2">
            {!isArchived && (
              <Link
                to={`/workspaces/${workspace_id}/data-sources/${ds.data_source_id}/edit`}
                data-testid="edit-data-source-btn"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-600 text-gray-300 hover:text-white text-sm font-medium transition-colors"
              >
                <Edit className="w-4 h-4" />
                Edit
              </Link>
            )}
            {isArchived ? (
              <button
                type="button"
                data-testid="restore-data-source-btn"
                onClick={() => setShowRestoreModal(true)}
                className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium transition-colors"
              >
                Restore
              </button>
            ) : (
              <button
                type="button"
                data-testid="archive-data-source-btn"
                onClick={() => setShowArchiveModal(true)}
                className="px-3 py-1.5 rounded-lg bg-red-600/80 hover:bg-red-500 text-white text-sm font-medium transition-colors"
              >
                Archive
              </button>
            )}
          </div>
        )}
      </div>

      {/* Detail card */}
      <div className="bg-gray-800/60 border border-gray-700 rounded-2xl p-6 space-y-4">
        <div className="flex flex-wrap gap-3 items-center">
          <StatusBadge status={ds.status} />
          <TestStatusBadge status={ds.last_test_status} />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-gray-400">Source Type</p>
            <p className="text-white font-medium mt-0.5">{ds.source_type}</p>
          </div>
          <div>
            <p className="text-gray-400">Connection Mode</p>
            <p className="text-white font-medium mt-0.5">{ds.connection_mode}</p>
          </div>
          <div>
            <p className="text-gray-400">Environment</p>
            <p className="text-white font-medium mt-0.5">{ds.environment}</p>
          </div>
          {ds.description && (
            <div>
              <p className="text-gray-400">Description</p>
              <p className="text-white font-medium mt-0.5">{ds.description}</p>
            </div>
          )}
          {ds.last_tested_at && (
            <div>
              <p className="text-gray-400">Last Tested</p>
              <p className="text-white font-medium mt-0.5">
                {new Date(ds.last_tested_at).toLocaleString()}
              </p>
            </div>
          )}
          <div>
            <p className="text-gray-400">Created</p>
            <p className="text-white font-medium mt-0.5">
              {new Date(ds.created_at).toLocaleDateString()}
            </p>
          </div>
        </div>

        {/* Test Connection button — only for active, non-agent sources */}
        {!isArchived && ds.connection_mode === 'direct' && (
          <div className="pt-2">
            <button
              type="button"
              data-testid="test-connection-btn"
              disabled={testMutation.isPending}
              onClick={() => testMutation.mutate()}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600/80 hover:bg-blue-500 text-white text-sm font-medium transition-colors disabled:opacity-60"
            >
              <Zap className="w-4 h-4" />
              {testMutation.isPending ? 'Testing…' : 'Test Connection'}
            </button>
          </div>
        )}
      </div>

      {/* Audit log */}
      <AuditLogPanel workspaceId={workspace_id!} dataSourceId={ds.data_source_id} />

      {/* Modals */}
      {showArchiveModal && (
        <ArchiveModal
          workspaceId={workspace_id!}
          dataSourceId={ds.data_source_id}
          dataSourceName={ds.source_name}
          onClose={() => setShowArchiveModal(false)}
          onSuccess={() => qc.invalidateQueries({ queryKey })}
        />
      )}
      {showRestoreModal && (
        <RestoreModal
          workspaceId={workspace_id!}
          dataSourceId={ds.data_source_id}
          dataSourceName={ds.source_name}
          onClose={() => setShowRestoreModal(false)}
          onSuccess={() => qc.invalidateQueries({ queryKey })}
        />
      )}
    </div>
  );
}
