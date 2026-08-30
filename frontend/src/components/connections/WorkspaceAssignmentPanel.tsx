/**
 * F130 — WorkspaceAssignmentPanel
 *
 * Workspace authorization control for a tenant connection.
 * Admin users can add/remove workspace access; non-admin gets read-only view.
 * Fetches the tenant workspace list from WorkspaceContext.
 */
import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Building2, Check, Shield, ShieldOff } from 'lucide-react';
import {
  getConnectionAssignments,
  replaceConnectionAssignments,
} from '../../services/connectionService';
import { listWorkspaces } from '../../services/workspace';

interface Props {
  tenantId: string;
  connectionId: string;
  isAdmin: boolean;
}

export default function WorkspaceAssignmentPanel({
  tenantId,
  connectionId,
  isAdmin,
}: Props) {
  const queryClient = useQueryClient();

  // Fetch workspaces for the connection's tenant. Tenant-scoped JWT users
  // (tenant_admin, workspace members) get their tenant's workspaces
  // implicitly — the `tenant_id` query param is reserved for platform_admin/
  // platform_viewer and the API rejects it with 403 otherwise.
  const { data: tenantWorkspacesResp } = useQuery({
    queryKey: ['workspaces-for-tenant', tenantId],
    queryFn: () => listWorkspaces({ page_size: 100 }),
    enabled: !!tenantId,
    staleTime: 60_000,
  });
  const allWorkspaces = (tenantWorkspacesResp?.data ?? []).filter(
    (w) => w.status === 'active',
  );

  const { data: assignments = [], isLoading } = useQuery({
    queryKey: ['connection-assignments', tenantId, connectionId],
    queryFn: () => getConnectionAssignments(tenantId, connectionId),
    staleTime: 30_000,
  });

  const [selected, setSelected] = useState<Set<string>>(new Set<string>());
  const [initialized, setInitialized] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Sync selected state when assignments load
  useEffect(() => {
    if (!isLoading && !initialized) {
      setSelected(new Set(assignments.map((a) => a.workspace_id)));
      setInitialized(true);
    }
  }, [assignments, isLoading, initialized]);

  const { mutate: save, isPending, isSuccess } = useMutation({
    mutationFn: (ids: string[]) =>
      replaceConnectionAssignments(tenantId, connectionId, ids),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['connection-assignments', tenantId, connectionId],
      });
      setDirty(false);
    },
  });

  function toggle(workspaceId: string) {
    if (!isAdmin) return;
    const next = new Set(selected);
    if (next.has(workspaceId)) next.delete(workspaceId);
    else next.add(workspaceId);
    setSelected(next);
    setDirty(true);
  }

  function handleSave() {
    save(Array.from(selected));
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500 py-2">
        <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
        </svg>
        Loading workspace assignments…
      </div>
    );
  }

  const assignedIds = new Set(assignments.map((a) => a.workspace_id));

  return (
    <div data-testid="workspace-assignment-panel" className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield size={16} className="text-primary-400" />
          <h3 className="text-sm font-semibold text-gray-200">Workspace Access</h3>
          <span className="text-xs px-2 py-0.5 rounded-full bg-dark-700 text-gray-400 border border-dark-600">
            {assignments.length} authorized
          </span>
        </div>
        {isAdmin && dirty && (
          <button
            onClick={handleSave}
            disabled={isPending}
            className="btn btn-primary text-xs py-1.5 px-3 disabled:opacity-50"
            data-testid="save-assignments-btn"
          >
            {isPending ? 'Saving…' : 'Save changes'}
          </button>
        )}
        {isAdmin && !dirty && isSuccess && (
          <span className="flex items-center gap-1 text-xs text-green-400">
            <Check size={12} /> Saved
          </span>
        )}
      </div>

      {!isAdmin && (
        <p className="text-xs text-gray-500">Only tenant administrators can modify workspace access.</p>
      )}

      {allWorkspaces.length === 0 ? (
        <div className="py-6 text-center">
          <Building2 size={24} className="mx-auto text-dark-600 mb-2" />
          <p className="text-sm text-gray-500">No workspaces found.</p>
        </div>
      ) : (
        <div className="divide-y divide-dark-800">
          {allWorkspaces.map((ws) => {
            const isAssigned = isAdmin
              ? selected.has(ws.workspace_id)
              : assignedIds.has(ws.workspace_id);
            return (
              <div
                key={ws.workspace_id}
                className={`flex items-center justify-between py-3 px-1 ${isAdmin ? 'cursor-pointer hover:bg-dark-800/50 rounded-lg transition-colors' : ''}`}
                onClick={() => toggle(ws.workspace_id)}
                data-testid={`ws-row-${ws.workspace_id}`}
              >
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold flex-shrink-0 ${isAssigned ? 'bg-primary-600/20 text-primary-400' : 'bg-dark-700 text-gray-500'}`}>
                    {ws.workspace_name.charAt(0).toUpperCase()}
                  </div>
                  <span className={`text-sm ${isAssigned ? 'text-gray-100' : 'text-gray-500'}`}>
                    {ws.workspace_name}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {isAssigned ? (
                    <span className="flex items-center gap-1 text-xs text-green-400 bg-green-900/20 border border-green-800/40 px-2 py-0.5 rounded-full">
                      <Check size={10} /> Access granted
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs text-gray-600 bg-dark-800 border border-dark-700 px-2 py-0.5 rounded-full">
                      <ShieldOff size={10} /> No access
                    </span>
                  )}
                  {isAdmin && (
                    <input
                      type="checkbox"
                      checked={isAssigned}
                      onChange={() => toggle(ws.workspace_id)}
                      onClick={(e) => e.stopPropagation()}
                      className="h-4 w-4 rounded border-dark-600 bg-dark-800 text-primary-600 focus:ring-primary-500"
                      data-testid={`ws-check-${ws.workspace_id}`}
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {isAdmin && (
        <div className="pt-2 flex items-center justify-between border-t border-dark-800">
          <span className="text-xs text-gray-500">
            {selected.size} workspace{selected.size !== 1 ? 's' : ''} selected
          </span>
          <button
            onClick={handleSave}
            disabled={isPending || !dirty}
            className="btn btn-primary text-sm disabled:opacity-40"
            data-testid="save-assignments-btn-bottom"
          >
            {isPending ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      )}
    </div>
  );
}
