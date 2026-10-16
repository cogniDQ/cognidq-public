/**
 * TenantSupportAccessPage — tenant_admin self-service for granting CogniDQ's
 * platform operators time-limited, audited troubleshooting access.
 *
 * Route: /hub/t/:tenant_id/support-access
 *
 * Platform admin has no standing access to this tenant's workspaces — a
 * grant here is the only way to let them in, and it expires on its own.
 * Gated by TenantAdminGuard at the route level.
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ArrowLeft, Loader2, ShieldCheck, Trash2 } from 'lucide-react';

import { useAuth } from '../../contexts/AuthContext';
import { getTenantId } from '../../utils/jwt';
import {
  createSupportAccessGrant,
  listSupportAccessGrants,
  revokeSupportAccessGrant,
  type SupportAccessGrant,
} from '../../services/supportAccessService';
import { listWorkspaces, type WorkspaceSummary } from '../../services/workspace';

const DURATION_OPTIONS = [
  { label: '30 minutes', minutes: 30 },
  { label: '1 hour', minutes: 60 },
  { label: '4 hours', minutes: 240 },
  { label: '24 hours', minutes: 1440 },
];

function isActive(g: SupportAccessGrant): boolean {
  return !g.revoked_at && new Date(g.expires_at).getTime() > Date.now();
}

export default function TenantSupportAccessPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const params = useParams<{ tenant_id?: string }>();
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const tenantId = params.tenant_id ?? user?.tenant_id ?? getTenantId(token) ?? null;
  const tenantBase = tenantId ? `/hub/t/${tenantId}` : '/hub';

  const [grants, setGrants] = useState<SupportAccessGrant[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const [workspaceId, setWorkspaceId] = useState<string>('');
  const [durationMinutes, setDurationMinutes] = useState(60);
  const [reason, setReason] = useState('');

  const refresh = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    try {
      setGrants(await listSupportAccessGrants(tenantId));
    } catch {
      toast.error('Failed to load support access grants.');
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void refresh();
    if (tenantId) {
      listWorkspaces({ tenant_id: tenantId, page_size: 100 })
        .then((res) => setWorkspaces(res.data ?? []))
        .catch(() => {});
    }
  }, [refresh, tenantId]);

  async function handleGrant(e: React.FormEvent) {
    e.preventDefault();
    if (!tenantId) return;
    setSubmitting(true);
    try {
      await createSupportAccessGrant(tenantId, {
        workspace_id: workspaceId || undefined,
        duration_minutes: durationMinutes,
        reason: reason || undefined,
      });
      toast.success('Support access granted.');
      setReason('');
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to grant support access.');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRevoke(grant: SupportAccessGrant) {
    if (!tenantId) return;
    if (!window.confirm('Revoke this support access grant now?')) return;
    try {
      await revokeSupportAccessGrant(tenantId, grant.id);
      toast.success('Grant revoked.');
      await refresh();
    } catch {
      toast.error('Failed to revoke grant.');
    }
  }

  if (!tenantId) {
    return <div className="p-6 text-amber-300">No tenant is associated with your account.</div>;
  }

  const activeGrants = grants.filter(isActive);
  const pastGrants = grants.filter((g) => !isActive(g));

  return (
    <div className="space-y-6" data-testid="tenant-support-access-page">
      <div>
        <button
          onClick={() => navigate(tenantBase)}
          className="text-sm text-gray-400 hover:text-gray-200 flex items-center gap-1 mb-2"
        >
          <ArrowLeft className="w-3 h-3" /> Back to Tenant Administration
        </button>
        <h1 className="text-2xl font-bold gradient-text mb-1">Support Access</h1>
        <p className="text-gray-400 text-sm max-w-2xl">
          CogniDQ's platform operators have no standing access to your workspaces. Grant
          time-limited access below if you need help troubleshooting — it expires
          automatically, and every grant and revoke is written to your audit log.
        </p>
      </div>

      <form onSubmit={handleGrant} className="glass p-4 rounded-xl space-y-4 max-w-xl">
        <h2 className="text-sm font-semibold text-gray-200">Grant temporary access</h2>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Scope</label>
          <select
            value={workspaceId}
            onChange={(e) => setWorkspaceId(e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm"
          >
            <option value="">Whole tenant</option>
            {workspaces.map((ws) => (
              <option key={ws.workspace_id} value={ws.workspace_id}>
                {ws.workspace_name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Duration</label>
          <select
            value={durationMinutes}
            onChange={(e) => setDurationMinutes(Number(e.target.value))}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm"
          >
            {DURATION_OPTIONS.map((opt) => (
              <option key={opt.minutes} value={opt.minutes}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Reason (optional)</label>
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. help investigating a failed rule run"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm"
          />
        </div>
        <button type="submit" disabled={submitting} className="btn-primary flex items-center gap-2">
          {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
          Grant access
        </button>
      </form>

      <div>
        <h2 className="text-lg font-semibold text-gray-200 mb-3">Active grants</h2>
        {loading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="w-6 h-6 animate-spin text-teal-400" />
          </div>
        ) : activeGrants.length === 0 ? (
          <div className="glass p-6 rounded-lg text-center text-gray-400 text-sm">
            No active support access grants.
          </div>
        ) : (
          <div className="rounded-xl border border-gray-700 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-800 border-b border-gray-700">
                <tr>
                  <th className="px-4 py-3 text-left text-gray-400 font-medium">Scope</th>
                  <th className="px-4 py-3 text-left text-gray-400 font-medium">Reason</th>
                  <th className="px-4 py-3 text-left text-gray-400 font-medium">Expires</th>
                  <th className="px-4 py-3 text-right text-gray-400 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700/50">
                {activeGrants.map((g) => (
                  <tr key={g.id} className="bg-gray-900 hover:bg-gray-800/60">
                    <td className="px-4 py-3 text-white">
                      {g.workspace_id
                        ? workspaces.find((w) => w.workspace_id === g.workspace_id)?.workspace_name ?? g.workspace_id
                        : 'Whole tenant'}
                    </td>
                    <td className="px-4 py-3 text-gray-300">{g.reason ?? '—'}</td>
                    <td className="px-4 py-3 text-gray-400">{new Date(g.expires_at).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleRevoke(g)}
                        className="text-xs text-red-400 hover:text-red-300 inline-flex items-center gap-1"
                      >
                        <Trash2 className="w-3 h-3" /> Revoke
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {pastGrants.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-gray-200 mb-3">Past grants</h2>
          <div className="rounded-xl border border-gray-700 overflow-hidden opacity-70">
            <table className="w-full text-sm">
              <thead className="bg-gray-800 border-b border-gray-700">
                <tr>
                  <th className="px-4 py-3 text-left text-gray-400 font-medium">Scope</th>
                  <th className="px-4 py-3 text-left text-gray-400 font-medium">Reason</th>
                  <th className="px-4 py-3 text-left text-gray-400 font-medium">Ended</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700/50">
                {pastGrants.map((g) => (
                  <tr key={g.id} className="bg-gray-900">
                    <td className="px-4 py-3 text-gray-300">
                      {g.workspace_id
                        ? workspaces.find((w) => w.workspace_id === g.workspace_id)?.workspace_name ?? g.workspace_id
                        : 'Whole tenant'}
                    </td>
                    <td className="px-4 py-3 text-gray-400">{g.reason ?? '—'}</td>
                    <td className="px-4 py-3 text-gray-500">
                      {g.revoked_at ? `Revoked ${new Date(g.revoked_at).toLocaleString()}` : 'Expired'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
