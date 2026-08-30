/**
 * WorkspaceDetailPage — workspace detail/edit/archive/restore page (F002 P11).
 *
 * Route: /workspaces/:workspace_id
 *
 * Access control (UI level — backend enforces authoritatively):
 *   - workspace_administrator: sees full detail + Edit form + Archive/Restore buttons
 *   - data_engineer / platform_viewer: read-only detail, no action buttons
 *
 * Data flow:
 *   - React Query fetches GET /workspaces/{id} on mount.
 *   - After edit/archive/restore success, the query is invalidated → refetch.
 *   - Archive and Restore open modal dialogs.
 */
import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, ArrowLeft, Settings } from 'lucide-react';

import { getWorkspace } from '../../services/workspace';
import { getActorRole } from '../../utils/jwt';
import WorkspaceDetailCard from '../../components/workspaces/WorkspaceDetailCard';
import EditWorkspaceForm from '../../components/workspaces/edit/EditWorkspaceForm';
import ArchiveWorkspaceModal from '../../components/workspaces/edit/ArchiveWorkspaceModal';
import RestoreWorkspaceModal from '../../components/workspaces/edit/RestoreWorkspaceModal';
import AuditLogPanel from '../../components/workspaces/AuditLogPanel';

const STALE_TIME = 30_000;

export default function WorkspaceDetailPage() {
  const { workspace_id } = useParams<{ workspace_id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [showArchiveModal, setShowArchiveModal] = useState(false);
  const [showRestoreModal, setShowRestoreModal] = useState(false);

  // Actor role from JWT (client-side hint only; backend enforces authoritatively)
  const token = localStorage.getItem('access_token');
  const isWorkspaceAdmin = getActorRole(token) === 'workspace_administrator';

  const queryKey = ['workspace', workspace_id];

  const { data, isLoading, isError } = useQuery({
    queryKey,
    queryFn: () => getWorkspace(workspace_id!),
    staleTime: STALE_TIME,
    enabled: !!workspace_id,
  });

  const workspace = data?.data;

  const handleMutationSuccess = () => {
    queryClient.invalidateQueries({ queryKey });
  };

  // --- Loading skeleton ---
  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse" data-testid="workspace-detail-loading">
        <div className="h-8 w-64 rounded-lg bg-dark-800" />
        <div className="h-48 rounded-2xl bg-dark-800/60" />
        <div className="h-64 rounded-2xl bg-dark-800/60" />
      </div>
    );
  }

  // --- Error state ---
  if (isError || !workspace) {
    return (
      <div data-testid="workspace-detail-error">
        <button
          type="button"
          onClick={() => navigate('/workspaces')}
          className="mb-4 flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to workspaces
        </button>
        <div
          role="alert"
          className="flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400"
        >
          <AlertCircle className="w-5 h-5 shrink-0" aria-hidden="true" />
          <span>Failed to load workspace. It may not exist or you may not have access.</span>
        </div>
      </div>
    );
  }

  const isArchived = workspace.status === 'archived';

  return (
    <div className="space-y-6" data-testid="workspace-detail-page">
      {/* Page header */}
      <div className="flex items-center justify-between gap-4">
        <button
          type="button"
          onClick={() => navigate('/workspaces')}
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors"
          data-testid="back-to-workspaces-btn"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to workspaces
        </button>

        {/* Archive / Restore action buttons + Settings link (workspace_administrator only) */}
        {isWorkspaceAdmin && (
          <div className="flex gap-2">
            <Link
              to={`/workspaces/${workspace.workspace_id}/settings`}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-dark-600 text-gray-300 hover:text-white text-sm font-medium transition-colors"
              data-testid="workspace-settings-link"
            >
              <Settings className="w-4 h-4" />
              Settings
            </Link>
            {isArchived ? (
              <button
                type="button"
                onClick={() => setShowRestoreModal(true)}
                className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium transition-colors"
                data-testid="restore-workspace-btn"
              >
                Restore
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setShowArchiveModal(true)}
                className="px-3 py-1.5 rounded-lg bg-red-600/80 hover:bg-red-500 text-white text-sm font-medium transition-colors"
                data-testid="archive-workspace-btn"
              >
                Archive
              </button>
            )}
          </div>
        )}
      </div>

      {/* Workspace metadata card */}
      <WorkspaceDetailCard workspace={workspace} />

      {/* Quick links */}
      <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-5">
        <h3 className="text-sm font-medium text-gray-300 mb-3">Quick Links</h3>
        <Link
          to={`/workspaces/${workspace.workspace_id}/data-sources`}
          className="flex items-center gap-2 text-sm text-purple-400 hover:text-purple-300 transition-colors"
        >
          → Data Sources
        </Link>
        <Link
          to={`/workspaces/${workspace.workspace_id}/datasets`}
          className="flex items-center gap-2 text-sm text-purple-400 hover:text-purple-300 transition-colors"
          data-testid="datasets-quick-link"
        >
          → Datasets
        </Link>
        <Link
          to={`/workspaces/${workspace.workspace_id}/issues`}
          className="flex items-center gap-2 text-sm text-purple-400 hover:text-purple-300 transition-colors"
          data-testid="issues-quick-link"
        >
          → Issues
        </Link>
      </div>

      {/* Edit form (workspace_administrator + active workspace only) */}
      {isWorkspaceAdmin && !isArchived && (
        <EditWorkspaceForm
          workspace={workspace}
          onSuccess={handleMutationSuccess}
        />
      )}

      {/* Audit log link */}
      <AuditLogPanel workspaceId={workspace.workspace_id} />

      {/* Archive modal */}
      {showArchiveModal && (
        <ArchiveWorkspaceModal
          workspaceId={workspace.workspace_id}
          workspaceName={workspace.workspace_name}
          onSuccess={handleMutationSuccess}
          onClose={() => setShowArchiveModal(false)}
        />
      )}

      {/* Restore modal */}
      {showRestoreModal && (
        <RestoreWorkspaceModal
          workspaceId={workspace.workspace_id}
          workspaceName={workspace.workspace_name}
          onSuccess={handleMutationSuccess}
          onClose={() => setShowRestoreModal(false)}
        />
      )}
    </div>
  );
}
