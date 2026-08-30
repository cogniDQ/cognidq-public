/**
 * EmptyWorkspaceState — displayed when the workspace list returns zero results.
 *
 * Two variants per P10 spec:
 *   - `active` filter: shows "no active workspaces" + prominent Create CTA.
 *   - `archived` filter active: shows "no archived workspaces" without CTA.
 */
import { FolderOpen, Archive } from 'lucide-react';
import { Link } from 'react-router-dom';

interface EmptyWorkspaceStateProps {
  /** Whether the "include_archived" filter is currently active. */
  includeArchived: boolean;
  /** Whether the actor can create workspaces in the current tenant. */
  canCreateWorkspace: boolean;
  /** When set, appended as ?tenant_id=... to the create link (platform_admin). */
  createTenantIdParam?: string;
}

export default function EmptyWorkspaceState({
  includeArchived,
  canCreateWorkspace,
  createTenantIdParam,
}: EmptyWorkspaceStateProps) {
  const createHref = createTenantIdParam
    ? `/hub/workspaces/new?tenant_id=${createTenantIdParam}`
    : '/hub/workspaces/new';
  if (includeArchived) {
    return (
      <div
        className="flex flex-col items-center justify-center py-20 text-center"
        data-testid="empty-state-archived"
      >
        <Archive className="w-12 h-12 text-gray-600 mb-4" aria-hidden="true" />
        <p className="text-lg font-medium text-gray-300 mb-1">
          No archived workspaces
        </p>
        <p className="text-sm text-gray-500">
          There are no archived workspaces in this tenant.
        </p>
      </div>
    );
  }

  return (
    <div
      className="flex flex-col items-center justify-center py-20 text-center"
      data-testid="empty-state-active"
    >
      <FolderOpen className="w-12 h-12 text-gray-600 mb-4" aria-hidden="true" />
      <p className="text-lg font-medium text-gray-300 mb-1">
        No active workspaces yet
      </p>
      <p className="text-sm text-gray-500 mb-6">
        Get started by creating your first workspace.
      </p>
      {canCreateWorkspace && (
        <Link
          to={createHref}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium transition-colors"
          data-testid="empty-state-create-btn"
        >
          Create Workspace
        </Link>
      )}
    </div>
  );
}
