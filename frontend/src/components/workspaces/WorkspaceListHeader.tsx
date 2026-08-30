/**
 * WorkspaceListHeader — page heading and "Create Workspace" CTA.
 *
 * The Create button is completely absent (not just disabled) for actors who
 * cannot create workspaces in the current tenant.
 */
import { Link, useLocation } from 'react-router-dom';
import { Plus, LayoutDashboard } from 'lucide-react';

interface WorkspaceListHeaderProps {
  /** Whether the actor can create workspaces in the current tenant. */
  canCreateWorkspace: boolean;
  /** When set, appended as ?tenant_id=... to the create link (platform_admin). */
  createTenantIdParam?: string;
}

export default function WorkspaceListHeader({
  canCreateWorkspace,
  createTenantIdParam,
}: WorkspaceListHeaderProps) {
  const location = useLocation();
  // Only show the DQ Hub shortcut when on the standalone /workspaces route
  // (not when already inside /hub/workspaces which has the sidebar)
  const isStandalone = !location.pathname.startsWith('/hub');

  const createHref = createTenantIdParam
    ? `/hub/workspaces/new?tenant_id=${createTenantIdParam}`
    : '/hub/workspaces/new';

  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-bold text-white">Workspaces</h1>
        <p className="mt-1 text-sm text-gray-400">
          Manage workspaces within your tenant.
        </p>
      </div>
      <div className="flex items-center gap-2">
        {isStandalone && (
          <Link
            to="/hub"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-dark-600 text-gray-300 hover:text-white text-sm font-medium transition-colors"
            data-testid="dq-hub-btn"
          >
            <LayoutDashboard className="w-4 h-4" aria-hidden="true" />
            DQ Hub
          </Link>
        )}
        {canCreateWorkspace && (
          <Link
            to={createHref}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium transition-colors"
            data-testid="create-workspace-btn"
          >
            <Plus className="w-4 h-4" aria-hidden="true" />
            Create Workspace
          </Link>
        )}
      </div>
    </div>
  );
}
