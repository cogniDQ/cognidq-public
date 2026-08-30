/**
 * TenantMembersPage — tenant-level member management for `tenant_admin`.
 *
 * Route: /tenant-admin/members
 *
 * Responsibilities:
 *   • Invite new users into the tenant via
 *     POST /api/v1/tenants/{tenant_id}/invitations
 *   • List pending invitations and allow revocation
 *   • Direct the admin to individual workspaces to assign roles (per the
 *     user's requirement: "members adding should be tenant level and
 *     members assignement to workspace should be workspace level").
 *
 * Gated by TenantAdminGuard at the route level.
 */
import { useEffect, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Loader2, Mail, Plus, RefreshCw, Trash2, ArrowLeft } from 'lucide-react';

import { useAuth } from '../../contexts/AuthContext';
import { getTenantId } from '../../utils/jwt';
import {
  createTenantInvitation,
  listTenantInvitations,
  revokeTenantInvitation,
  TenantInvitation,
  TenantInvitationRole,
} from '../../services/tenantInvitations';
import { listWorkspaces, WorkspaceSummary } from '../../services/workspace';

const ROLE_OPTIONS: { value: TenantInvitationRole; label: string }[] = [
  { value: 'workspace_administrator', label: 'Workspace Administrator' },
  { value: 'data_engineer', label: 'Data Engineer' },
  { value: 'data_steward', label: 'Data Steward' },
  { value: 'business_analyst', label: 'Business Analyst' },
  { value: 'governance_viewer', label: 'Governance Viewer' },
];

export default function TenantMembersPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const params = useParams<{ tenant_id?: string }>();
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const tenantId = params.tenant_id ?? user?.tenant_id ?? getTenantId(token) ?? null;
  const tenantBase = tenantId ? `/hub/t/${tenantId}` : '/hub';

  const [invitations, setInvitations] = useState<TenantInvitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showInvite, setShowInvite] = useState(false);

  const refresh = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    setError(null);
    try {
      setInvitations(await listTenantInvitations(tenantId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load invitations');
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleRevoke(inv: TenantInvitation) {
    if (!tenantId) return;
    if (!window.confirm(`Revoke invitation for ${inv.email}?`)) return;
    try {
      await revokeTenantInvitation(tenantId, inv.invitation_id);
      toast.success('Invitation revoked.');
      await refresh();
    } catch {
      toast.error('Failed to revoke invitation.');
    }
  }

  if (!tenantId) {
    return (
      <div className="p-6 text-amber-300">
        No tenant is associated with your account.
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="tenant-members-page">
      <div className="flex items-center justify-between">
        <div>
          <button
            onClick={() => navigate(tenantBase)}
            className="text-sm text-gray-400 hover:text-gray-200 flex items-center gap-1 mb-2"
          >
            <ArrowLeft className="w-3 h-3" /> Back to Tenant Administration
          </button>
          <h1 className="text-2xl font-bold gradient-text mb-1">Tenant Members</h1>
          <p className="text-gray-400 text-sm">
            Invite new users into your tenant. Once accepted, open a workspace to
            assign them a workspace-specific role.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => void refresh()}
            className="px-3 py-2 text-sm text-gray-300 hover:text-white flex items-center gap-1"
            aria-label="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => setShowInvite(true)}
            className="btn-primary flex items-center gap-2"
            data-testid="tenant-members-invite-btn"
          >
            <Plus className="w-4 h-4" /> Invite Member
          </button>
        </div>
      </div>

      <div>
        <h2 className="text-lg font-semibold text-gray-200 mb-3">Pending Invitations</h2>
        {loading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="w-6 h-6 animate-spin text-teal-400" />
          </div>
        ) : error ? (
          <div className="glass p-4 rounded-lg text-amber-300 text-sm">{error}</div>
        ) : invitations.length === 0 ? (
          <div className="glass p-8 rounded-lg text-center text-gray-400">
            <Mail className="w-10 h-10 mx-auto mb-3 text-gray-600" />
            <p className="text-sm">No pending invitations.</p>
          </div>
        ) : (
          <div className="rounded-xl border border-gray-700 overflow-hidden">
            <table className="w-full text-sm" data-testid="tenant-invitations-table">
              <thead className="bg-gray-800 border-b border-gray-700">
                <tr>
                  <th className="px-4 py-3 text-left text-gray-400 font-medium">Email</th>
                  <th className="px-4 py-3 text-left text-gray-400 font-medium">Role</th>
                  <th className="px-4 py-3 text-left text-gray-400 font-medium">Status</th>
                  <th className="px-4 py-3 text-left text-gray-400 font-medium">Expires</th>
                  <th className="px-4 py-3 text-right text-gray-400 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700/50">
                {invitations.map((inv) => (
                  <tr key={inv.invitation_id} className="bg-gray-900 hover:bg-gray-800/60">
                    <td className="px-4 py-3 text-white">{inv.email}</td>
                    <td className="px-4 py-3 text-gray-300">{inv.role ?? '—'}</td>
                    <td className="px-4 py-3 text-gray-300">{inv.status}</td>
                    <td className="px-4 py-3 text-gray-400">
                      {inv.expires_at ? new Date(inv.expires_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {inv.status === 'pending' && (
                        <button
                          onClick={() => handleRevoke(inv)}
                          className="text-xs text-red-400 hover:text-red-300 inline-flex items-center gap-1"
                        >
                          <Trash2 className="w-3 h-3" /> Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showInvite && (
        <InviteModal
          tenantId={tenantId}
          onClose={() => setShowInvite(false)}
          onCreated={() => {
            setShowInvite(false);
            void refresh();
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Invite modal
// ---------------------------------------------------------------------------

interface InviteModalProps {
  tenantId: string;
  onClose: () => void;
  onCreated: (inv: TenantInvitation) => void;
}

function InviteModal({ tenantId, onClose, onCreated }: InviteModalProps) {
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [role, setRole] = useState<TenantInvitationRole | ''>('');
  const [workspaceId, setWorkspaceId] = useState<string>('');
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [tokenUrl, setTokenUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await listWorkspaces({ tenant_id: tenantId, page_size: 100 });
        if (!cancelled) {
          const list = res.data ?? [];
          setWorkspaces(list);
          if (list.length === 1) setWorkspaceId(list[0].workspace_id);
        }
      } catch {
        // Non-fatal: user can still invite tenant-only.
      }
    })();
    return () => { cancelled = true; };
  }, [tenantId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email) return;
    if (role && !workspaceId) {
      toast.error('Pick a workspace to assign the role to.');
      return;
    }
    setSubmitting(true);
    try {
      const inv = await createTenantInvitation(tenantId, {
        email,
        full_name: fullName || undefined,
        role_name: role || undefined,
        workspace_id: role ? workspaceId : undefined,
      });
      if (inv.acceptance_url) {
        setTokenUrl(inv.acceptance_url);
        toast.success('Invitation created. Share the acceptance URL with the invitee.');
      } else {
        toast.success('Invitation created.');
        onCreated(inv);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to create invitation';
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-md bg-gray-900 border border-gray-700 rounded-2xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Invite to Tenant</h2>

        {tokenUrl ? (
          <div className="space-y-3">
            <p className="text-sm text-gray-300">
              Invitation created. Share this URL with the invitee — it is shown only once.
            </p>
            <textarea
              readOnly
              value={tokenUrl}
              className="w-full h-24 text-xs bg-gray-800 border border-gray-700 text-gray-200 rounded p-2"
              data-testid="invitation-url"
            />
            <div className="flex justify-end">
              <button
                onClick={() => onCreated({ invitation_id: '', tenant_id: null, workspace_id: null, email: '', role: null, status: 'pending', expires_at: null, created_at: null, accepted_at: null })}
                className="btn-primary"
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm"
                data-testid="invite-email-input"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Full name (optional)</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Default workspace role (optional)
              </label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as TenantInvitationRole | '')}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm"
                data-testid="invite-role-select"
              >
                <option value="">No default role — tenant only</option>
                {ROLE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <p className="text-xs text-gray-500 mt-1">
                Leave empty to invite to the tenant without a workspace assignment.
                You can assign workspace roles later from each workspace&apos;s Members page.
              </p>
            </div>
            {role && (
              <div>
                <label className="block text-sm text-gray-400 mb-1">Workspace</label>
                <select
                  value={workspaceId}
                  onChange={(e) => setWorkspaceId(e.target.value)}
                  required
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm"
                  data-testid="invite-workspace-select"
                >
                  <option value="">Select a workspace…</option>
                  {workspaces.map((w) => (
                    <option key={w.workspace_id} value={w.workspace_id}>
                      {w.workspace_name}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  The role above will be granted to the invitee in this workspace on acceptance.
                </p>
              </div>
            )}
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="btn-primary flex items-center gap-2 disabled:opacity-40"
                data-testid="invite-submit-btn"
              >
                {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
                {submitting ? 'Creating…' : 'Create Invitation'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
