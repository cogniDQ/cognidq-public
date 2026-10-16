/**
 * PlatformWelcome — landing page for platform operators after login.
 *
 * Platform admin has no standing access to client workspaces — this page
 * is the management console only. Any workspace access happens through an
 * active, tenant-admin-issued support access grant (see /admin/support-access).
 */
import { Link } from 'react-router-dom';
import {
  Server,
  Activity,
  Building2,
  ArrowRight,
  ExternalLink,
  ShieldCheck,
  Loader2,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../contexts/AuthContext';
import { listActiveGrantsForAdmin } from '../../services/supportAccessService';
import { wsPath, tenantPath } from '../../utils/paths';

const quickActions = [
  {
    icon: Server,
    title: 'Tenants',
    description: 'Create, provision, and manage platform tenants.',
    to: '/admin/tenants',
  },
  {
    icon: ShieldCheck,
    title: 'Support Access',
    description: 'See every tenant where you currently have temporary access.',
    to: '/admin/support-access',
  },
  {
    icon: Building2,
    title: 'Demo Requests & Sandboxes',
    description: 'Review demo requests and manage sandbox environments.',
    to: '/admin/demo-requests',
  },
  {
    icon: Activity,
    title: 'Celery / Tasks',
    description: 'Monitor background workers, queues, and scheduled tasks.',
    to: '/admin/celery',
  },
];

export default function PlatformWelcome() {
  const { user } = useAuth();

  const { data: activeGrants, isLoading } = useQuery({
    queryKey: ['support-access-grants', 'active'],
    queryFn: listActiveGrantsForAdmin,
    staleTime: 30_000,
  });

  const grants = activeGrants ?? [];
  const firstName = user?.full_name?.split(' ')[0] || 'there';

  return (
    <div className="mx-auto max-w-screen-xl px-6 py-10 space-y-10">
      <div>
        <h1 className="text-3xl font-bold text-white">Welcome, {firstName}</h1>
        <p className="mt-2 text-gray-400">
          You are signed in as a platform operator. This is the management console —
          client workspaces are only reachable with an active support access grant.
        </p>
      </div>

      {/* Active support access */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-primary-400" />
            Active support access
          </h2>
          <Link to="/admin/support-access" className="text-sm text-primary-400 hover:text-primary-300">
            View all →
          </Link>
        </div>
        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="w-6 h-6 animate-spin text-gray-500" />
          </div>
        ) : grants.length === 0 ? (
          <div className="glass rounded-lg p-6 text-gray-400">
            No active grants. A tenant admin can grant you temporary access from their
            tenant's Support Access page when they need help troubleshooting.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {grants.map((g) => (
              <Link
                key={g.id}
                to={
                  g.workspace_id
                    ? wsPath(g.tenant_id, g.workspace_id, '/overview')
                    : tenantPath(g.tenant_id)
                }
                className="glass p-5 rounded-lg hover:border-primary-500/50 transition-all group"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-lg text-gray-200 mb-1 truncate">
                      {g.tenant_name ?? g.tenant_id}
                    </h3>
                    <p className="text-sm text-gray-500 truncate">
                      {g.workspace_name ?? 'Whole tenant'} · expires{' '}
                      {new Date(g.expires_at).toLocaleTimeString()}
                    </p>
                  </div>
                  <ArrowRight className="w-5 h-5 text-gray-600 group-hover:text-primary-400 group-hover:translate-x-1 transition-all flex-shrink-0" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* Platform management */}
      <section>
        <h2 className="text-xl font-semibold text-white mb-4">Manage the platform</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {quickActions.map((action) => (
            <Link
              key={action.title}
              to={action.to}
              className="glass p-5 rounded-lg hover:border-primary-500/50 transition-all group"
            >
              <action.icon className="w-6 h-6 text-primary-400 mb-3" />
              <h3 className="font-semibold text-gray-200 mb-1">{action.title}</h3>
              <p className="text-sm text-gray-500">{action.description}</p>
            </Link>
          ))}
        </div>
      </section>

      {/* Docs */}
      <section className="glass rounded-lg p-6 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-gray-200">New to CogniDQ?</h3>
          <p className="text-sm text-gray-500">
            Browse the interactive API documentation or the getting-started guide.
          </p>
        </div>
        <a
          href="http://localhost:8000/api/docs"
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1.5 text-sm text-primary-400 hover:text-primary-300 transition-colors"
        >
          API Docs <ExternalLink className="w-4 h-4" />
        </a>
      </section>
    </div>
  );
}
