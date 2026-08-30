/**
 * F130 — EditConnectionPage (dark theme)
 *
 * Edit form for a tenant-scoped connection at /hub/connections/:connection_id/edit.
 * source_type and connection_mode are read-only (immutable fields per API).
 * Redirects to detail page on success.
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft } from 'lucide-react';
import {
  getConnection,
  updateConnection,
  type UpdateConnectionPayload,
  type ConnectionEnvironment,
} from '../../services/connectionService';
import { getTenantId } from '../../utils/jwt';
import { useWorkspace } from '../../contexts/WorkspaceContext';

const ENVIRONMENTS: ConnectionEnvironment[] = [
  'development', 'staging', 'production',
];

export default function EditConnectionPage() {
  const { connection_id, tenant_id: urlTenantId } = useParams<{ connection_id: string; tenant_id?: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const token = localStorage.getItem('access_token');
  const { currentTenantId } = useWorkspace();
  const tenantId = urlTenantId ?? currentTenantId ?? getTenantId(token);
  const connectionsBase = tenantId ? `/hub/t/${tenantId}/connections` : '/hub/connections';

  const { data: connection, isLoading } = useQuery({
    queryKey: ['connection', tenantId, connection_id],
    queryFn: () => getConnection(tenantId!, connection_id!),
    enabled: !!tenantId && !!connection_id,
    staleTime: 30_000,
  });

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [environment, setEnvironment] = useState<ConnectionEnvironment>('development');

  useEffect(() => {
    if (connection) {
      setName(connection.name);
      setDescription(connection.description ?? '');
      setEnvironment(connection.environment);
    }
  }, [connection]);

  const { mutate, isPending, isError, error } = useMutation({
    mutationFn: (payload: UpdateConnectionPayload) =>
      updateConnection(tenantId!, connection_id!, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['connection', tenantId, connection_id],
      });
      queryClient.invalidateQueries({ queryKey: ['connections', tenantId] });
      navigate(`${connectionsBase}/${connection_id}`);
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    mutate({
      name,
      description: description || undefined,
      environment,
    });
  }

  if (isLoading) {
    return (
      <div className="p-6 flex items-center gap-2 text-gray-400 text-sm">
        <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/></svg>
        Loading…
      </div>
    );
  }

  if (!connection) {
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

  return (
    <div className="p-6 space-y-6 max-w-xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          to={`${connectionsBase}/${connection_id}`}
          className="text-gray-500 hover:text-gray-300 transition-colors"
        >
          <ArrowLeft size={18} />
        </Link>
        <div>
          <h1 className="text-2xl font-bold gradient-text">Edit Connection</h1>
          <p className="text-gray-500 text-sm mt-0.5">{connection.source_name}</p>
        </div>
      </div>

      {isError && (
        <div className="p-4 rounded-lg bg-red-900/20 border border-red-800 text-red-400 text-sm" data-testid="edit-error">
          {(error as Error)?.message ?? 'Failed to update connection.'}
        </div>
      )}

      <form onSubmit={handleSubmit} className="card space-y-5" data-testid="edit-connection-form">
        <div>
          <label className="block text-sm font-medium text-gray-400 mb-1.5">Name</label>
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="input"
            data-testid="field-name"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-400 mb-1.5">Source Type</label>
          <input
            disabled
            value={connection.source_type}
            className="input opacity-50 cursor-not-allowed"
            data-testid="field-source-type"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-400 mb-1.5">Mode</label>
          <input
            disabled
            value={connection.connection_mode}
            className="input opacity-50 cursor-not-allowed"
            data-testid="field-mode"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-400 mb-1.5">Environment</label>
          <select
            value={environment}
            onChange={(e) => setEnvironment(e.target.value as ConnectionEnvironment)}
            className="input"
            data-testid="field-environment"
          >
            {ENVIRONMENTS.map((env) => (
              <option key={env} value={env}>{env}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-400 mb-1.5">Description</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            className="textarea"
            data-testid="field-description"
          />
        </div>

        <div className="flex items-center gap-3 pt-1">
          <button
            type="submit"
            disabled={isPending}
            className="btn btn-primary disabled:opacity-50"
            data-testid="submit-btn"
          >
            {isPending ? 'Saving…' : 'Save Changes'}
          </button>
          <Link
            to={`${connectionsBase}/${connection_id}`}
            className="btn btn-secondary"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
