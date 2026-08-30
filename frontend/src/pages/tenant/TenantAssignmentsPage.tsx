/**
 * TenantAssignmentsPage — role matrix for the tenant admin.
 *
 * Route: /tenant-admin/assignments
 *
 * Shows every tenant user vs every workspace in the tenant, letting the
 * tenant admin assign, change, or revoke workspace roles (including the
 * workspace_administrator role) from a single screen — addressing the
 * requirement "I don't see where tenant can assign workspace admin to be
 * admin of a workspace (or multiple workspaces)".
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ArrowLeft, Loader2, RefreshCw } from 'lucide-react';

import { useAuth } from '../../contexts/AuthContext';
import { getTenantId } from '../../utils/jwt';
import { listWorkspaces, WorkspaceSummary } from '../../services/workspace';
import { listTenantMembers, TenantMember } from '../../services/tenantMembers';
import {
  assignMemberRole,
  revokeMemberRole,
  ALL_ROLE_NAMES,
  ROLE_DISPLAY_NAMES,
  WorkspaceRoleName,
} from '../../services/workspaceRoles';

const NONE = '__none__';

export default function TenantAssignmentsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const params = useParams<{ tenant_id?: string }>();
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const tenantId = params.tenant_id ?? user?.tenant_id ?? getTenantId(token) ?? null;
  const tenantBase = tenantId ? `/hub/t/${tenantId}` : '/hub';

  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [members, setMembers] = useState<TenantMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyCell, setBusyCell] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    setError(null);
    try {
      const [wsResp, m] = await Promise.all([
        listWorkspaces({ page_size: 100 }),
        listTenantMembers(tenantId),
      ]);
      setWorkspaces(wsResp.data.filter((w) => w.status === 'active'));
      setMembers(m);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load assignments');
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Map (user, workspace) -> current role for O(1) lookup.
  const roleMap = useMemo(() => {
    const m = new Map<string, string>();
    members.forEach((mem) => {
      mem.assignments.forEach((a) => {
        m.set(`${mem.user_id}:${a.workspace_id}`, a.role_name);
      });
    });
    return m;
  }, [members]);

  async function handleChange(userId: string, workspaceId: string, newRole: string) {
    const key = `${userId}:${workspaceId}`;
    const current = roleMap.get(key) ?? NONE;
    if (current === newRole) return;
    setBusyCell(key);
    try {
      if (newRole === NONE) {
        await revokeMemberRole(workspaceId, userId);
        toast.success('Role revoked.');
      } else {
        await assignMemberRole(workspaceId, userId, newRole as WorkspaceRoleName);
        toast.success('Role updated.');
      }
      await load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to update role';
      toast.error(msg);
    } finally {
      setBusyCell(null);
    }
  }

  if (!tenantId) {
    return <div className="p-6 text-amber-300">No tenant associated with your account.</div>;
  }

  return (
    <div className="space-y-6" data-testid="tenant-assignments-page">
      <div className="flex items-center justify-between">
        <div>
          <button
            onClick={() => navigate(tenantBase)}
            className="text-sm text-gray-400 hover:text-gray-200 flex items-center gap-1 mb-2"
          >
            <ArrowLeft className="w-3 h-3" /> Back to Tenant Administration
          </button>
          <h1 className="text-2xl font-bold gradient-text mb-1">Workspace Role Assignments</h1>
          <p className="text-gray-400 text-sm">
            Assign any tenant user to any workspace with the desired role, including
            workspace administrator across one or many workspaces.
          </p>
        </div>
        <button
          onClick={() => void load()}
          className="px-3 py-2 text-sm text-gray-300 hover:text-white flex items-center gap-1"
          aria-label="Refresh"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-10">
          <Loader2 className="w-6 h-6 animate-spin text-teal-400" />
        </div>
      ) : error ? (
        <div className="glass p-4 rounded-lg text-amber-300 text-sm">{error}</div>
      ) : workspaces.length === 0 ? (
        <div className="glass p-6 rounded-lg text-gray-400 text-sm">
          No active workspaces in this tenant.
        </div>
      ) : members.length === 0 ? (
        <div className="glass p-6 rounded-lg text-gray-400 text-sm">
          No users in this tenant yet. Use the Members page to invite new users.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-700">
          <table className="min-w-full text-sm" data-testid="assignments-matrix">
            <thead className="bg-gray-800 border-b border-gray-700">
              <tr>
                <th className="px-4 py-3 text-left text-gray-400 font-medium sticky left-0 bg-gray-800">
                  User
                </th>
                {workspaces.map((w) => (
                  <th
                    key={w.workspace_id}
                    className="px-4 py-3 text-left text-gray-400 font-medium whitespace-nowrap"
                  >
                    {w.workspace_name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700/50">
              {members.map((m) => (
                <tr key={m.user_id} className="bg-gray-900 hover:bg-gray-800/60">
                  <td className="px-4 py-3 sticky left-0 bg-gray-900">
                    <div className="font-medium text-white">{m.full_name ?? m.email}</div>
                    <div className="text-xs text-gray-500">{m.email}</div>
                    {m.platform_role && (
                      <div className="text-xs text-teal-400 mt-0.5">{m.platform_role}</div>
                    )}
                  </td>
                  {workspaces.map((w) => {
                    const key = `${m.user_id}:${w.workspace_id}`;
                    const current = roleMap.get(key) ?? NONE;
                    const busy = busyCell === key;
                    return (
                      <td key={w.workspace_id} className="px-4 py-3">
                        <select
                          disabled={busy}
                          value={current}
                          onChange={(e) => handleChange(m.user_id, w.workspace_id, e.target.value)}
                          className="px-2 py-1 rounded bg-gray-800 border border-gray-600 text-xs text-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          data-testid={`assignment-${m.user_id}-${w.workspace_id}`}
                        >
                          <option value={NONE}>— none —</option>
                          {ALL_ROLE_NAMES.map((r) => (
                            <option key={r} value={r}>
                              {ROLE_DISPLAY_NAMES[r]}
                            </option>
                          ))}
                        </select>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
