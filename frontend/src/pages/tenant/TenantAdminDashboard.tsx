/**
 * TenantAdminDashboard — home page for the first-class `tenant_admin` role.
 *
 * A tenant admin owns a single tenant. From here they can:
 *   • See all workspaces in their tenant (including archived)
 *   • Create new workspaces
 *   • Jump into any workspace to manage members and roles
 *   • (Future) invite new users to the tenant
 *
 * This page intentionally reuses `listWorkspaces` which the backend scopes to
 * the JWT's tenant claim — a tenant admin sees every workspace in their
 * tenant (bypasses the member-only filter applied to workspace members).
 */
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Plus, Building2, Users, ArrowRight, AlertCircle, Loader2, Archive, RotateCcw, Shield } from 'lucide-react';
import { listWorkspaces, archiveWorkspace, restoreWorkspace, WorkspaceSummary } from '../../services/workspace';
import { useAuth } from '../../contexts/AuthContext';
import { getTenantId } from '../../utils/jwt';

export default function TenantAdminDashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const params = useParams<{ tenant_id?: string }>();
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const tenantId = params.tenant_id ?? getTenantId(token) ?? '';
  const tenantBase = tenantId ? `/hub/t/${tenantId}` : '/hub';
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [archiving, setArchiving] = useState<WorkspaceSummary | null>(null);
  const [archiveReason, setArchiveReason] = useState('');
  const [archiveConfirmLast, setArchiveConfirmLast] = useState(false);
  const [archiveSubmitting, setArchiveSubmitting] = useState(false);
  const [restoringId, setRestoringId] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      const resp = await listWorkspaces({ page_size: 100, include_archived: true });
      setWorkspaces(resp.data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load workspaces');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await listWorkspaces({ page_size: 100, include_archived: true });
        if (!cancelled) setWorkspaces(resp.data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load workspaces');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  async function submitArchive() {
    if (!archiving) return;
    if (!archiveReason.trim()) {
      toast.error('Please provide a reason.');
      return;
    }
    setArchiveSubmitting(true);
    try {
      await archiveWorkspace(archiving.workspace_id, {
        status_reason: archiveReason.trim(),
        ...(archiveConfirmLast ? { confirm_last_workspace: true as const } : {}),
      });
      toast.success('Workspace archived.');
      setArchiving(null);
      setArchiveReason('');
      setArchiveConfirmLast(false);
      await refresh();
    } catch (err) {
      const anyErr = err as { response?: { status?: number; data?: { detail?: { code?: string; message?: string } | string } } };
      const status = anyErr.response?.status;
      const detail = anyErr.response?.data?.detail;
      const code = typeof detail === 'object' ? detail?.code : undefined;
      if (status === 409 && code === 'LAST_ACTIVE_WORKSPACE') {
        setArchiveConfirmLast(true);
        toast('This is the tenant\u2019s last active workspace. Confirm to archive it anyway.', { icon: '\u26A0\uFE0F' });
      } else {
        const msg = typeof detail === 'object' && detail?.message
          ? detail.message
          : typeof detail === 'string'
            ? detail
            : err instanceof Error ? err.message : 'Archive failed';
        toast.error(msg);
      }
    } finally {
      setArchiveSubmitting(false);
    }
  }

  async function handleRestore(ws: WorkspaceSummary) {
    setRestoringId(ws.workspace_id);
    try {
      await restoreWorkspace(ws.workspace_id);
      toast.success('Workspace restored.');
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Restore failed');
    } finally {
      setRestoringId(null);
    }
  }

  const activeCount = workspaces.filter((w) => w.status === 'active').length;
  const archivedCount = workspaces.length - activeCount;

  return (
    <div className="space-y-6" data-testid="tenant-admin-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold gradient-text mb-1">Tenant Administration</h1>
          <p className="text-gray-400 text-sm">
            Manage workspaces, invite members, and assign roles for your tenant
            {user?.email ? <> — signed in as <span className="text-gray-200">{user.email}</span></> : null}.
          </p>
        </div>
        <button
          onClick={() => navigate('/hub/workspaces/new')}
          className="btn-primary flex items-center gap-2"
          data-testid="tenant-admin-create-ws"
        >
          <Plus className="w-4 h-4" />
          New Workspace
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="glass p-4 rounded-lg">
          <div className="flex items-center gap-3">
            <Building2 className="w-8 h-8 text-teal-400" />
            <div>
              <div className="text-2xl font-semibold text-gray-100">{activeCount}</div>
              <div className="text-xs text-gray-400 uppercase tracking-wider">Active Workspaces</div>
            </div>
          </div>
        </div>
        <div className="glass p-4 rounded-lg">
          <div className="flex items-center gap-3">
            <Building2 className="w-8 h-8 text-gray-500" />
            <div>
              <div className="text-2xl font-semibold text-gray-100">{archivedCount}</div>
              <div className="text-xs text-gray-400 uppercase tracking-wider">Archived</div>
            </div>
          </div>
        </div>
        <div className="glass p-4 rounded-lg">
          <div className="flex items-center gap-3">
            <Users className="w-8 h-8 text-teal-400" />
            <div className="flex-1">
              <div className="text-sm text-gray-200">Members &amp; Invitations</div>
              <div className="text-xs text-gray-400 mt-0.5">
                Invite new users to your tenant.
              </div>
              <button
                onClick={() => navigate(`${tenantBase}/members`)}
                className="mt-2 inline-flex items-center gap-1 text-xs text-teal-400 hover:text-teal-300"
                data-testid="tenant-admin-manage-members"
              >
                Manage members <ArrowRight className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>
        <div className="glass p-4 rounded-lg">
          <div className="flex items-center gap-3">
            <Shield className="w-8 h-8 text-teal-400" />
            <div className="flex-1">
              <div className="text-sm text-gray-200">Workspace Roles</div>
              <div className="text-xs text-gray-400 mt-0.5">
                Assign users to workspaces, including workspace administrators.
              </div>
              <button
                onClick={() => navigate(`${tenantBase}/assignments`)}
                className="mt-2 inline-flex items-center gap-1 text-xs text-teal-400 hover:text-teal-300"
                data-testid="tenant-admin-manage-roles"
              >
                Manage roles <ArrowRight className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Workspace list */}
      <div>
        <h2 className="text-lg font-semibold text-gray-200 mb-3">Your Workspaces</h2>

        {loading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="w-6 h-6 animate-spin text-teal-400" />
          </div>
        ) : error ? (
          <div className="glass p-4 rounded-lg flex items-center gap-2 text-amber-300">
            <AlertCircle className="w-4 h-4" />
            <span className="text-sm">{error}</span>
          </div>
        ) : workspaces.length === 0 ? (
          <div className="glass p-8 rounded-lg text-center">
            <Building2 className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-400 mb-4">Your tenant has no workspaces yet.</p>
            <button
              onClick={() => navigate('/hub/workspaces/new')}
              className="btn-primary inline-flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Create First Workspace
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {workspaces.map((ws) => (
              <div
                key={ws.workspace_id}
                className="glass p-5 rounded-lg hover:border-teal-500/50 transition-all"
                data-testid="tenant-admin-ws-card"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-lg text-gray-200 mb-1 truncate">
                      {ws.workspace_name}
                    </h3>
                    <p className="text-xs text-gray-500">{ws.workspace_slug}</p>
                    {ws.status !== 'active' && (
                      <span className="inline-block mt-2 px-2 py-0.5 bg-gray-700 text-gray-300 text-xs rounded">
                        {ws.status}
                      </span>
                    )}
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <button
                    onClick={() => navigate(`${tenantBase}/ws/${ws.workspace_id}/overview`)}
                    className="text-sm text-teal-400 hover:text-teal-300 flex items-center gap-1"
                  >
                    Open <ArrowRight className="w-3 h-3" />
                  </button>
                  <button
                    onClick={() => navigate(`${tenantBase}/ws/${ws.workspace_id}/members`)}
                    className="text-sm text-gray-400 hover:text-gray-200 flex items-center gap-1"
                  >
                    <Users className="w-3 h-3" /> Members
                  </button>
                  <button
                    onClick={() => navigate(`${tenantBase}/ws/${ws.workspace_id}/settings`)}
                    className="text-sm text-gray-400 hover:text-gray-200"
                  >
                    Settings
                  </button>
                  {ws.status === 'active' ? (
                    <button
                      onClick={() => {
                        setArchiving(ws);
                        setArchiveReason('');
                        setArchiveConfirmLast(false);
                      }}
                      className="text-sm text-amber-400 hover:text-amber-300 flex items-center gap-1 ml-auto"
                      data-testid="tenant-admin-archive-btn"
                    >
                      <Archive className="w-3 h-3" /> Archive
                    </button>
                  ) : (
                    <button
                      onClick={() => handleRestore(ws)}
                      disabled={restoringId === ws.workspace_id}
                      className="text-sm text-teal-400 hover:text-teal-300 flex items-center gap-1 ml-auto disabled:opacity-50"
                      data-testid="tenant-admin-restore-btn"
                    >
                      <RotateCcw className="w-3 h-3" />
                      {restoringId === ws.workspace_id ? 'Restoring\u2026' : 'Restore'}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {archiving && (
        <div
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
          data-testid="archive-modal"
        >
          <div className="glass rounded-lg border border-gray-700 p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold text-gray-100 mb-2">
              Archive “{archiving.workspace_name}”
            </h3>
            <p className="text-sm text-gray-400 mb-4">
              Archiving hides the workspace from daily operations. You can restore it later.
            </p>
            <label className="block text-xs text-gray-400 mb-1">Reason</label>
            <textarea
              value={archiveReason}
              onChange={(e) => setArchiveReason(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 bg-dark-800/50 border border-dark-700 rounded text-sm text-white"
              placeholder="Why are you archiving this workspace?"
              data-testid="archive-reason-input"
            />
            {archiveConfirmLast && (
              <div className="mt-3 p-2 rounded bg-amber-900/30 border border-amber-600/40 text-amber-200 text-xs">
                This is your tenant’s last active workspace. Confirming will leave the tenant with
                no active workspaces.
              </div>
            )}
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => {
                  setArchiving(null);
                  setArchiveReason('');
                  setArchiveConfirmLast(false);
                }}
                className="px-3 py-2 text-sm text-gray-300 hover:text-white"
                disabled={archiveSubmitting}
              >
                Cancel
              </button>
              <button
                onClick={submitArchive}
                disabled={archiveSubmitting}
                className="px-3 py-2 text-sm bg-amber-600 hover:bg-amber-500 text-white rounded disabled:opacity-50"
                data-testid="archive-confirm-btn"
              >
                {archiveSubmitting ? 'Archiving\u2026' : archiveConfirmLast ? 'Confirm archive' : 'Archive'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
