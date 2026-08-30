/**
 * WorkspaceMembersPage — list and manage workspace members (F078 P02/P03)
 *
 * Route: /hub/ws/:workspace_id/members
 *
 * Access control (UI level — backend enforces authoritatively):
 *   - workspace_administrator: full access (add, change role, remove)
 *   - data_engineer / data_steward / business_analyst / governance_viewer: read-only
 *   - platform_admin: full access (add, change role, remove)
 *   - platform_viewer: read-only
 *   - others: redirected to /404
 *
 * Functionality:
 *   - Lists all members with role badge and granted date
 *   - workspace_administrator can add members, change roles, remove members
 *   - Last-admin guard: cannot remove/demote the final workspace_administrator
 */
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Users, UserPlus, ChevronDown } from 'lucide-react';
import toast from 'react-hot-toast';

import { listWorkspaceMembers } from '../../services/workspaceMembers';
import { assignMemberRole, revokeMemberRole, listCustomRoles } from '../../services/workspaceRoles';
import type { WorkspaceRoleName } from '../../services/workspaceRoles';
import { ROLE_DISPLAY_NAMES, ALL_ROLE_NAMES } from '../../services/workspaceRoles';
import { getActorRole } from '../../utils/jwt';
import AddMemberModal from '../../components/workspaces/members/AddMemberModal';

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const ALLOWED_ROLES = new Set([
  'workspace_administrator',
  'data_engineer',
  'data_steward',
  'business_analyst',
  'governance_viewer',
  'platform_admin',
  'platform_viewer',
  'tenant_admin',
]);

const ROLE_BADGE_CLASSES: Record<string, string> = {
  workspace_administrator: 'bg-purple-900/50 text-purple-300 border border-purple-700',
  data_engineer:           'bg-blue-900/50 text-blue-300 border border-blue-700',
  data_steward:            'bg-green-900/50 text-green-300 border border-green-700',
  business_analyst:        'bg-yellow-900/50 text-yellow-300 border border-yellow-700',
  governance_viewer:       'bg-gray-700/50 text-gray-400 border border-gray-600',
};

const STALE_TIME = 30_000;

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export default function WorkspaceMembersPage() {
  const { workspace_id } = useParams<{ workspace_id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const token = localStorage.getItem('access_token');
  const actorRole = getActorRole(token);
  const canEdit = actorRole === 'workspace_administrator' || actorRole === 'platform_admin' || actorRole === 'tenant_admin';

  const [showAddModal, setShowAddModal] = useState(false);
  const [changingRoleFor, setChangingRoleFor] = useState<string | null>(null);
  const [removingUserId, setRemovingUserId] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['workspace-members', workspace_id],
    queryFn: () => listWorkspaceMembers(workspace_id!),
    enabled: !!workspace_id,
    staleTime: STALE_TIME,
  });

  const members = data?.members ?? [];
  const adminCount = members.filter(m => m.role_name === 'workspace_administrator').length;

  const { data: customRoles = [] } = useQuery({
    queryKey: ['custom-roles', workspace_id],
    queryFn: () => listCustomRoles(workspace_id!),
    enabled: !!workspace_id,
    staleTime: STALE_TIME,
  });

  // Redirect users without access (after hooks to satisfy rules-of-hooks)
  if (actorRole && !ALLOWED_ROLES.has(actorRole)) {
    navigate('/404', { replace: true });
    return null;
  }

  async function handleRoleChange(userId: string, currentRole: string, newRole: string) {
    if (newRole === currentRole) return;
    if (currentRole === 'workspace_administrator' && adminCount <= 1) {
      toast.error('Cannot change role: this is the last workspace administrator.');
      return;
    }
    setChangingRoleFor(userId);
    try {
      await assignMemberRole(workspace_id!, userId, newRole);
      await queryClient.invalidateQueries({ queryKey: ['workspace-members', workspace_id] });
      toast.success('Role updated.');
    } catch {
      toast.error('Failed to update role.');
    } finally {
      setChangingRoleFor(null);
    }
  }

  async function handleRemove(userId: string, currentRole: string) {
    if (currentRole === 'workspace_administrator' && adminCount <= 1) {
      toast.error('Cannot remove: this is the last workspace administrator.');
      return;
    }
    if (!window.confirm('Remove this member from the workspace?')) return;
    setRemovingUserId(userId);
    try {
      await revokeMemberRole(workspace_id!, userId);
      await queryClient.invalidateQueries({ queryKey: ['workspace-members', workspace_id] });
      toast.success('Member removed.');
    } catch {
      toast.error('Failed to remove member.');
    } finally {
      setRemovingUserId(null);
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* ── Header ────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Users className="w-6 h-6 text-indigo-400" />
          <div>
            <h1 className="text-xl font-semibold text-white">Workspace Members</h1>
            <p className="text-sm text-gray-400">
              Manage who has access to this workspace and their roles.
            </p>
          </div>
        </div>

        {canEdit && (
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            <UserPlus className="w-4 h-4" />
            Add Member
          </button>
        )}
      </div>

      {/* ── Loading / Error states ─────────────────────────────────── */}
      {isLoading && (
        <div className="text-gray-400 text-sm">Loading members…</div>
      )}

      {isError && (
        <div className="rounded-lg border border-red-700 bg-red-900/20 p-4 text-red-300 text-sm">
          Failed to load workspace members. Please try again.
        </div>
      )}

      {/* ── Member table ───────────────────────────────────────────── */}
      {!isLoading && !isError && (
        <div className="rounded-xl border border-gray-700 overflow-hidden">
          {members.length === 0 ? (
            <div className="p-8 text-center text-gray-500 text-sm">
              No members found for this workspace.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-800 border-b border-gray-700">
                <tr>
                  <th className="px-4 py-3 text-left text-gray-400 font-medium">User</th>
                  <th className="px-4 py-3 text-left text-gray-400 font-medium">Role</th>
                  <th className="px-4 py-3 text-left text-gray-400 font-medium">Added</th>
                  {canEdit && (
                    <th className="px-4 py-3 text-right text-gray-400 font-medium">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700/50">
                {members.map(member => (
                  <tr key={member.user_id} className="bg-gray-900 hover:bg-gray-800/60 transition-colors">
                    {/* User */}
                    <td className="px-4 py-3">
                      <div className="font-medium text-white">{member.display_name}</div>
                      <div className="text-xs text-gray-500">{member.email}</div>
                    </td>

                    {/* Role */}
                    <td className="px-4 py-3">
                      {canEdit ? (
                        <div className="relative inline-flex items-center">
                          <select
                            value={member.role_name}
                            disabled={changingRoleFor === member.user_id}
                            onChange={e =>
                              handleRoleChange(
                                member.user_id,
                                member.role_name,
                                e.target.value,
                              )
                            }
                            className="appearance-none pl-3 pr-8 py-1 rounded-full text-xs font-medium border cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-gray-800 text-gray-200 border-gray-600"
                          >
                            <optgroup label="Built-in roles">
                              {ALL_ROLE_NAMES.map(r => (
                                <option key={r} value={r}>
                                  {ROLE_DISPLAY_NAMES[r]}
                                </option>
                              ))}
                            </optgroup>
                            {customRoles.length > 0 && (
                              <optgroup label="Custom roles">
                                {customRoles.map(r => (
                                  <option key={r.id} value={r.name}>
                                    {r.display_name}
                                  </option>
                                ))}
                              </optgroup>
                            )}
                          </select>
                          <ChevronDown className="absolute right-2 w-3 h-3 text-gray-400 pointer-events-none" />
                        </div>
                      ) : (
                        <span
                          className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            ROLE_BADGE_CLASSES[member.role_name] ?? 'bg-gray-700 text-gray-300 border border-gray-600'
                          }`}
                        >
                          {ROLE_DISPLAY_NAMES[member.role_name as WorkspaceRoleName] ?? member.role_name}
                        </span>
                      )}
                    </td>

                    {/* Added date */}
                    <td className="px-4 py-3 text-gray-400">
                      {new Date(member.granted_at).toLocaleDateString(undefined, {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                      })}
                    </td>

                    {/* Actions */}
                    {canEdit && (
                      <td className="px-4 py-3 text-right">
                        <button
                          disabled={removingUserId === member.user_id}
                          onClick={() => handleRemove(member.user_id, member.role_name)}
                          className="text-xs text-red-400 hover:text-red-300 disabled:opacity-40 transition-colors"
                        >
                          {removingUserId === member.user_id ? 'Removing…' : 'Remove'}
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── Add Member Modal ───────────────────────────────────────── */}
      {showAddModal && workspace_id && (
        <AddMemberModal
          workspaceId={workspace_id}
          onClose={() => setShowAddModal(false)}
          onAdded={() => {
            queryClient.invalidateQueries({ queryKey: ['workspace-members', workspace_id] });
            setShowAddModal(false);
          }}
        />
      )}
    </div>
  );
}
