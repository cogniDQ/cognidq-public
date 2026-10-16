/**
 * AdminSupportAccessPage — platform_admin's view of their own active support
 * access grants.
 *
 * Grants are created exclusively by tenant admins from their own tenant's
 * Support Access page — there is no "request access" action here, since the
 * client decides, not the admin. This is just where you see what you've
 * been given and jump straight in.
 */
import { Link } from 'react-router-dom';
import { ArrowRight, Loader2, ShieldCheck } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { listActiveGrantsForAdmin } from '../../services/supportAccessService';
import { wsPath, tenantPath } from '../../utils/paths';

export default function AdminSupportAccessPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['support-access-grants', 'active'],
    queryFn: listActiveGrantsForAdmin,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const grants = data ?? [];

  return (
    <div className="mx-auto max-w-screen-xl px-6 py-10 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white flex items-center gap-2">
          <ShieldCheck className="w-7 h-7 text-primary-400" />
          Support Access
        </h1>
        <p className="mt-2 text-gray-400 max-w-2xl">
          Grants are issued by a tenant admin from within their own tenant — there is
          nothing to request here. Every grant below is time-limited and audited; it
          disappears from this list automatically once it expires or is revoked.
        </p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-32">
          <Loader2 className="w-6 h-6 animate-spin text-gray-500" />
        </div>
      ) : grants.length === 0 ? (
        <div className="glass rounded-lg p-8 text-center text-gray-400">
          No active grants right now.
        </div>
      ) : (
        <div className="rounded-xl border border-gray-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-800 border-b border-gray-700">
              <tr>
                <th className="px-4 py-3 text-left text-gray-400 font-medium">Tenant</th>
                <th className="px-4 py-3 text-left text-gray-400 font-medium">Scope</th>
                <th className="px-4 py-3 text-left text-gray-400 font-medium">Reason</th>
                <th className="px-4 py-3 text-left text-gray-400 font-medium">Expires</th>
                <th className="px-4 py-3 text-right text-gray-400 font-medium">Open</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700/50">
              {grants.map((g) => (
                <tr key={g.id} className="bg-gray-900 hover:bg-gray-800/60">
                  <td className="px-4 py-3 text-white">{g.tenant_name ?? g.tenant_id}</td>
                  <td className="px-4 py-3 text-gray-300">{g.workspace_name ?? 'Whole tenant'}</td>
                  <td className="px-4 py-3 text-gray-300">{g.reason ?? '—'}</td>
                  <td className="px-4 py-3 text-gray-400">{new Date(g.expires_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      to={
                        g.workspace_id
                          ? wsPath(g.tenant_id, g.workspace_id, '/overview')
                          : tenantPath(g.tenant_id)
                      }
                      className="text-primary-400 hover:text-primary-300 inline-flex items-center gap-1"
                    >
                      Open <ArrowRight className="w-3 h-3" />
                    </Link>
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
