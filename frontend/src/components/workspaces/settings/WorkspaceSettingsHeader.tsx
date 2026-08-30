/**
 * WorkspaceSettingsHeader — breadcrumb + page title for the settings page.
 */
import { ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useTenantScopedPath } from '../../../hooks/useTenantScopedPath';

interface Props {
  workspaceId: string;
  workspaceName?: string;
}

export default function WorkspaceSettingsHeader({ workspaceId, workspaceName }: Props) {
  const navigate = useNavigate();
  const { wsPath } = useTenantScopedPath();

  return (
    <div data-testid="settings-header">
      <button
        type="button"
        onClick={() => navigate(wsPath(workspaceId))}
        className="mb-4 flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors"
        data-testid="back-to-workspace-btn"
      >
        <ArrowLeft className="w-4 h-4" />
        {workspaceName ? `Back to ${workspaceName}` : 'Back to workspace'}
      </button>

      <h1 className="text-2xl font-bold text-white" data-testid="settings-page-title">
        Workspace Settings
      </h1>
      {workspaceName && (
        <p className="mt-1 text-sm text-gray-400" data-testid="settings-workspace-name">
          {workspaceName}
        </p>
      )}
    </div>
  );
}
