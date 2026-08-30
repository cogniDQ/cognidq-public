/**
 * F130 — ConnectionDetailPage
 *
 * Detail view for a tenant-scoped connection at /hub/connections/:connection_id.
 * Shows WorkspaceAssignmentPanel for tenant_admin only.
 */
import { Link, useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Edit2, Trash2, CheckCircle, Zap } from 'lucide-react';
import {
  getConnection,
  deleteConnection,
  testConnection,
} from '../../services/connectionService';
import { getTenantId, getActorRole } from '../../utils/jwt';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import WorkspaceAssignmentPanel from '../../components/connections/WorkspaceAssignmentPanel';

export default function ConnectionDetailPage() {
  const { connection_id, tenant_id: urlTenantId } = useParams<{ connection_id: string; tenant_id?: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const token = localStorage.getItem('access_token');
  const { currentTenantId } = useWorkspace();
  const tenantId = urlTenantId ?? currentTenantId ?? getTenantId(token);
  const connectionsBase = tenantId ? `/hub/t/${tenantId}/connections` : '/hub/connections';
  const actorRole = getActorRole(token);
  const isAdmin = actorRole === 'tenant_admin' || actorRole === 'platform_admin';

  const { data: connection, isLoading, isError } = useQuery({
    queryKey: ['connection', tenantId, connection_id],
    queryFn: () => getConnection(tenantId!, connection_id!),
    enabled: !!tenantId && !!connection_id,
    staleTime: 30_000,
  });

  const { mutate: runDelete, isPending: isDeleting } = useMutation({
    mutationFn: () => deleteConnection(tenantId!, connection_id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connections', tenantId] });
      navigate(connectionsBase);
    },
  });

  const { mutate: runTest, isPending: isTesting, data: testResult } = useMutation({
    mutationFn: () => testConnection(tenantId!, connection_id!),
  });

  if (isLoading) {
    return (
      <div className="p-6 flex items-center gap-2 text-gray-400 text-sm">
        <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/></svg>
        Loading…
      </div>
    );
  }

  if (isError || !connection) {
    return (
      <div className="p-6 space-y-3">
        <div className="p-4 rounded-lg bg-red-900/20 border border-red-800 text-red-400 text-sm">
          Connection not found.
        </div>
        <Link to={connectionsBase} className="text-primary-400 hover:text-primary-300 text-sm flex items-center gap-1">
          <ArrowLeft size={14} /> Back to connections
        </Link>
      </div>
    );
  }

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

  return (
    <div className="p-6 space-y-6 w-full max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link to={connectionsBase} className="text-gray-500 hover:text-gray-300 transition-colors">
          <ArrowLeft size={18} />
        </Link>
        <div>
          <h1 className="text-2xl font-bold gradient-text">{connection.name}</h1>
          <p className="text-gray-500 text-sm font-mono mt-0.5">{connection.source_type}</p>
        </div>
      </div>

      {/* Details card */}
      <div className="card space-y-0 p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-dark-700">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">Connection Details</h2>
        </div>
        <dl className="grid grid-cols-1 sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-dark-800">
          {[
            { label: 'Type', value: <span className="font-mono text-sm text-gray-200">{connection.source_type}</span>, testId: 'field-source-type' },
            { label: 'Mode', value: <span className="text-gray-200">{connection.connection_mode}</span>, testId: 'field-mode' },
            { label: 'Environment', value: <span className={`text-[11px] uppercase tracking-wide px-2 py-0.5 rounded font-medium ${ENV_BADGE[connection.environment] ?? 'text-gray-400'}`}>{connection.environment}</span>, testId: 'field-environment' },
            { label: 'Status', value: <span className={`text-[11px] uppercase tracking-wide px-2 py-0.5 rounded font-medium ${STATUS_BADGE[connection.status] ?? 'text-gray-400 border border-dark-600'}`}>{connection.status}</span>, testId: 'field-status' },
          ].map(({ label, value, testId }) => (
            <div key={label} className="px-5 py-4">
              <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">{label}</dt>
              <dd data-testid={testId}>{value}</dd>
            </div>
          ))}
        </dl>
        {connection.description && (
          <div className="px-5 py-4 border-t border-dark-800">
            <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Description</dt>
            <dd className="text-gray-300 text-sm" data-testid="field-description">{connection.description}</dd>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-3">
        <button
          onClick={() => runTest()}
          disabled={isTesting}
          className="btn btn-secondary flex items-center gap-2"
          data-testid="test-btn"
        >
          <Zap size={14} />
          {isTesting ? 'Testing…' : 'Test Connection'}
        </button>

        {isAdmin && (
          <>
            <Link
              to={`${connectionsBase}/${connection_id}/edit`}
              className="btn btn-secondary flex items-center gap-2"
              data-testid="edit-btn"
            >
              <Edit2 size={14} />
              Edit
            </Link>
            <button
              onClick={() => runDelete()}
              disabled={isDeleting}
              className="btn flex items-center gap-2 bg-red-900/30 text-red-400 border border-red-800 hover:bg-red-900/50 disabled:opacity-50"
              data-testid="delete-btn"
            >
              <Trash2 size={14} />
              {isDeleting ? 'Deleting…' : 'Delete'}
            </button>
          </>
        )}
      </div>

      {testResult && (
        <div
          className={`p-4 rounded-lg text-sm flex items-center gap-2 ${testResult.success ? 'bg-green-900/20 border border-green-800 text-green-400' : 'bg-red-900/20 border border-red-800 text-red-400'}`}
          data-testid="test-result"
        >
          <CheckCircle size={16} />
          {testResult.message}
          {testResult.latency_ms != null && <span className="text-xs opacity-70">({testResult.latency_ms}ms)</span>}
        </div>
      )}

      {isAdmin && (
        <div className="card">
          <WorkspaceAssignmentPanel
            tenantId={tenantId!}
            connectionId={connection_id!}
            isAdmin={isAdmin}
          />
        </div>
      )}
    </div>
  );
}
