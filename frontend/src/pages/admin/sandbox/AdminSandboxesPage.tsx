/**
 * F134 P11 — Admin Sandboxes Page
 *
 * Lists all sandbox environments with lifecycle actions and usage drill-in.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Activity, Archive, Loader2, Pause, Trash2 } from 'lucide-react';
import {
  archiveSandbox,
  deleteSandbox,
  extendSandbox,
  getSandboxUsage,
  listAdminSandboxes,
  suspendSandbox,
  type SandboxEnvironment,
  type SandboxUsageSummary,
} from '../../../services/adminSandboxService';

const STATUS_BADGE: Record<string, string> = {
  active: 'bg-green-500/20 text-green-300 border border-green-600/40',
  provisioning: 'bg-blue-500/20 text-blue-300 border border-blue-600/40',
  suspended: 'bg-yellow-500/20 text-yellow-300 border border-yellow-600/40',
  expired: 'bg-orange-500/20 text-orange-300 border border-orange-600/40',
  archived: 'bg-gray-500/20 text-gray-400 border border-gray-600/40',
};

const ENGAGEMENT_BADGE: Record<string, string> = {
  high: 'text-green-400',
  medium: 'text-yellow-400',
  low: 'text-gray-400',
  unknown: 'text-gray-600',
};

interface UsageDrawer {
  sandboxId: string;
  data: SandboxUsageSummary | null;
  loading: boolean;
}

export default function AdminSandboxesPage() {
  const [items, setItems] = useState<SandboxEnvironment[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<UsageDrawer | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listAdminSandboxes({ limit: 100 });
      setItems(resp.items);
    } catch {
      setError('Failed to load sandboxes.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openUsage = async (id: string) => {
    setDrawer({ sandboxId: id, data: null, loading: true });
    try {
      const data = await getSandboxUsage(id);
      setDrawer({ sandboxId: id, data, loading: false });
    } catch {
      setDrawer((prev) => prev ? { ...prev, loading: false } : null);
    }
  };

  const handleExtend = async (id: string) => {
    const note = window.prompt('Extension note (min 10 chars):');
    if (!note) return;
    setActionLoading(id);
    try {
      await extendSandbox(id, { note });
      await load();
    } finally {
      setActionLoading(null);
    }
  };

  const handleSuspend = async (id: string) => {
    const reason = window.prompt('Suspension reason:');
    if (!reason) return;
    setActionLoading(id);
    try {
      await suspendSandbox(id, { reason });
      await load();
    } finally {
      setActionLoading(null);
    }
  };

  const handleArchive = async (id: string) => {
    if (!window.confirm('Archive this sandbox?')) return;
    setActionLoading(id);
    try {
      await archiveSandbox(id);
      await load();
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (id: string) => {
    const force = window.confirm('Force delete (even if not archived)?');
    setActionLoading(id);
    try {
      await deleteSandbox(id, force);
      await load();
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-bold text-white">Sandbox Environments</h1>

      {error && (
        <div className="rounded-md bg-red-900/40 border border-red-700 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-8 h-8 animate-spin text-primary-400" />
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 text-gray-500">No sandboxes found.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-500 uppercase border-b border-gray-800">
                <th className="pb-2 text-left font-medium">ID</th>
                <th className="pb-2 text-left font-medium">Status</th>
                <th className="pb-2 text-left font-medium">Engagement</th>
                <th className="pb-2 text-left font-medium">Expires</th>
                <th className="pb-2 text-left font-medium">Created</th>
                <th className="pb-2 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {items.map((sb) => (
                <tr key={sb.id} className="hover:bg-gray-900/50 transition-colors">
                  <td className="py-3 font-mono text-xs text-gray-400 truncate max-w-[160px]">
                    {sb.id}
                  </td>
                  <td className="py-3">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-semibold ${
                        STATUS_BADGE[sb.status] ?? 'bg-gray-700 text-gray-300'
                      }`}
                    >
                      {sb.status}
                    </span>
                  </td>
                  <td className={`py-3 text-xs font-semibold capitalize ${ENGAGEMENT_BADGE[sb.engagement_score ?? 'unknown']}`}>
                    {sb.engagement_score ?? 'unknown'}
                  </td>
                  <td className="py-3 text-gray-400 text-xs">
                    {sb.expires_at ? new Date(sb.expires_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="py-3 text-gray-400 text-xs">
                    {new Date(sb.created_at).toLocaleDateString()}
                  </td>
                  <td className="py-3">
                    <div className="flex justify-end space-x-1">
                      <button
                        onClick={() => openUsage(sb.id)}
                        title="View usage"
                        className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-blue-400 transition-colors"
                      >
                        <Activity className="w-3.5 h-3.5" />
                      </button>
                      {sb.status === 'active' && (
                        <>
                          <button
                            onClick={() => handleExtend(sb.id)}
                            disabled={actionLoading === sb.id}
                            title="Extend"
                            className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-green-400 transition-colors"
                          >
                            <span className="text-xs font-bold">+7d</span>
                          </button>
                          <button
                            onClick={() => handleSuspend(sb.id)}
                            disabled={actionLoading === sb.id}
                            title="Suspend"
                            className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-yellow-400 transition-colors"
                          >
                            <Pause className="w-3.5 h-3.5" />
                          </button>
                        </>
                      )}
                      {(sb.status === 'suspended' || sb.status === 'expired') && (
                        <button
                          onClick={() => handleArchive(sb.id)}
                          disabled={actionLoading === sb.id}
                          title="Archive"
                          className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-orange-400 transition-colors"
                        >
                          <Archive className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {sb.status === 'archived' && (
                        <button
                          onClick={() => handleDelete(sb.id)}
                          disabled={actionLoading === sb.id}
                          title="Delete"
                          className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-red-400 transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Usage Drawer */}
      {drawer && (
        <div className="fixed inset-y-0 right-0 w-96 bg-gray-900 border-l border-gray-700 shadow-2xl p-6 overflow-y-auto z-50">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold text-white">Usage Details</h2>
            <button
              onClick={() => setDrawer(null)}
              className="text-gray-500 hover:text-white"
            >
              ✕
            </button>
          </div>
          {drawer.loading ? (
            <div className="flex justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-primary-400" />
            </div>
          ) : drawer.data ? (
            <div className="space-y-6">
              <div className="card p-4 space-y-2">
                <p className="text-xs uppercase text-gray-500 font-medium">Summary</p>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Total events</span>
                  <span className="text-white font-bold">{drawer.data.summary.total_events}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Engagement</span>
                  <span
                    className={`font-bold capitalize ${ENGAGEMENT_BADGE[drawer.data.summary.engagement_score]}`}
                  >
                    {drawer.data.summary.engagement_score}
                  </span>
                </div>
              </div>

              {drawer.data.events_by_type.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs uppercase text-gray-500 font-medium">Events by type</p>
                  {drawer.data.events_by_type.map((e) => (
                    <div key={e.event_type} className="flex justify-between text-sm">
                      <span className="text-gray-400">{e.event_type}</span>
                      <span className="text-white">{e.count}</span>
                    </div>
                  ))}
                </div>
              )}

              {drawer.data.timeline.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs uppercase text-gray-500 font-medium">
                    Daily activity (last 14 days)
                  </p>
                  {drawer.data.timeline.map((t) => (
                    <div key={t.day} className="flex justify-between text-xs">
                      <span className="text-gray-500">{t.day}</span>
                      <span className="text-gray-300">{t.count}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="text-gray-500 text-sm">Failed to load usage data.</p>
          )}
        </div>
      )}
    </div>
  );
}
