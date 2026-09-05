/**
 * PlatformWelcome — landing page for platform operators after login.
 *
 * Replaces the bare tenants table as the post-login destination: offers
 * quick actions and direct entry points into workspaces so a first-time
 * admin can explore the product instead of facing a CRUD screen.
 */
import { Link } from 'react-router-dom';
import {
  Server,
  Activity,
  Building2,
  ArrowRight,
  ExternalLink,
  LayoutDashboard,
  Loader2,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../contexts/AuthContext';
import { listWorkspaces } from '../../services/workspace';
import { wsPath } from '../../utils/paths';

const quickActions = [
  {
    icon: Server,
    title: 'Tenants',
    description: 'Create, provision, and manage platform tenants.',
    to: '/admin/tenants',
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

  const { data, isLoading } = useQuery({
    queryKey: ['platform-welcome-workspaces'],
    queryFn: () => listWorkspaces({ page_size: 6, sort_by: 'updated_at', sort_dir: 'desc' }),
    staleTime: 30_000,
  });

  const workspaces = data?.data ?? [];
  const firstName = user?.full_name?.split(' ')[0] || 'there';

  return (
    <div className="mx-auto max-w-screen-xl px-6 py-10 space-y-10">
      <div>
        <h1 className="text-3xl font-bold text-white">Welcome, {firstName}</h1>
        <p className="mt-2 text-gray-400">
          You are signed in as a platform operator. Jump into a workspace to see
          data quality in action, or manage the platform below.
        </p>
      </div>

      {/* Workspace entry points */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <LayoutDashboard className="w-5 h-5 text-primary-400" />
            Explore a workspace
          </h2>
        </div>
        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="w-6 h-6 animate-spin text-gray-500" />
          </div>
        ) : workspaces.length === 0 ? (
          <div className="glass rounded-lg p-6 text-gray-400">
            No workspaces yet. Create a tenant, then provision a workspace —
            or run <code className="text-primary-400">make seed</code> to load the demo
            workspace.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {workspaces.map((ws) => (
              <Link
                key={ws.workspace_id}
                to={wsPath(ws.tenant_id ?? null, ws.workspace_id, '/overview')}
                className="glass p-5 rounded-lg hover:border-primary-500/50 transition-all group"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-lg text-gray-200 mb-1 truncate">
                      {ws.workspace_name}
                    </h3>
                    <p className="text-sm text-gray-500 truncate">
                      {ws.tenant_name ? `${ws.tenant_name} · ` : ''}
                      {ws.workspace_slug}
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
