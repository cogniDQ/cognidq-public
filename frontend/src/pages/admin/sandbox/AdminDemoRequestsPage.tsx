/**
 * F134 P11 — Admin Demo Requests Queue Page
 *
 * Lists pending/reviewed demo requests with approve/reject actions.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle, Loader2, XCircle } from 'lucide-react';
import {
  approveAdminDemoRequest,
  listAdminDemoRequests,
  rejectAdminDemoRequest,
  type AdminDemoRequest,
} from '../../../services/adminSandboxService';

const STATUS_OPTIONS = ['pending', 'approved', 'rejected', 'all'] as const;
type StatusFilter = (typeof STATUS_OPTIONS)[number];

const BADGE: Record<string, string> = {
  pending: 'bg-yellow-500/20 text-yellow-300 border border-yellow-600/40',
  approved: 'bg-green-500/20 text-green-300 border border-green-600/40',
  rejected: 'bg-red-500/20 text-red-300 border border-red-600/40',
};

export default function AdminDemoRequestsPage() {
  const [filter, setFilter] = useState<StatusFilter>('pending');
  const [items, setItems] = useState<AdminDemoRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listAdminDemoRequests({
        status: filter === 'all' ? undefined : filter,
        page_size: 50,
      });
      setItems(resp.items);
    } catch {
      setError('Failed to load demo requests.');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const handleApprove = async (id: string) => {
    setActionLoading(id);
    try {
      await approveAdminDemoRequest(id);
      await load();
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (id: string) => {
    const reason = window.prompt('Rejection reason:');
    if (!reason) return;
    setActionLoading(id);
    try {
      await rejectAdminDemoRequest(id, reason);
      await load();
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Demo Requests</h1>
        <div className="flex space-x-2">
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold capitalize transition-colors ${
                filter === s
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

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
        <div className="text-center py-16 text-gray-500">No demo requests found.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-500 uppercase border-b border-gray-800">
                <th className="pb-2 text-left font-medium">Name</th>
                <th className="pb-2 text-left font-medium">Email</th>
                <th className="pb-2 text-left font-medium">Company</th>
                <th className="pb-2 text-left font-medium">Status</th>
                <th className="pb-2 text-left font-medium">Requested</th>
                <th className="pb-2 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {items.map((req) => (
                <tr key={req.id} className="hover:bg-gray-900/50 transition-colors">
                  <td className="py-3 text-white font-medium">
                    {req.first_name} {req.last_name}
                  </td>
                  <td className="py-3 text-gray-300">{req.email}</td>
                  <td className="py-3 text-gray-300">{req.company}</td>
                  <td className="py-3">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-semibold ${
                        BADGE[req.status] ?? 'bg-gray-700 text-gray-300'
                      }`}
                    >
                      {req.status}
                    </span>
                  </td>
                  <td className="py-3 text-gray-400">
                    {new Date(req.created_at).toLocaleDateString()}
                  </td>
                  <td className="py-3 text-right">
                    {req.status === 'pending' && (
                      <div className="flex justify-end space-x-2">
                        <button
                          onClick={() => handleApprove(req.id)}
                          disabled={actionLoading === req.id}
                          className="flex items-center space-x-1 px-2 py-1 rounded bg-green-700/40 hover:bg-green-700/70 text-green-300 text-xs transition-colors disabled:opacity-50"
                          title="Approve"
                        >
                          {actionLoading === req.id ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <CheckCircle className="w-3 h-3" />
                          )}
                          <span>Approve</span>
                        </button>
                        <button
                          onClick={() => handleReject(req.id)}
                          disabled={actionLoading === req.id}
                          className="flex items-center space-x-1 px-2 py-1 rounded bg-red-700/40 hover:bg-red-700/70 text-red-300 text-xs transition-colors disabled:opacity-50"
                          title="Reject"
                        >
                          <XCircle className="w-3 h-3" />
                          <span>Reject</span>
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
