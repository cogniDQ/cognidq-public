/**
 * WorkspaceTableRow — a single row in the Workspace list table.
 * Clicking the row navigates to the workspace detail page.
 */
import { useNavigate } from 'react-router-dom';
import { WorkspaceSummary } from '../../services/workspace';
import { getTenantId } from '../../utils/jwt';
import { wsPath } from '../../utils/paths';
import WorkspaceStatusBadge from './WorkspaceStatusBadge';

interface WorkspaceTableRowProps {
  workspace: WorkspaceSummary;
}

function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export default function WorkspaceTableRow({ workspace }: WorkspaceTableRowProps) {
  const navigate = useNavigate();
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const tenantId = getTenantId(token);
  const target = wsPath(tenantId, workspace.workspace_id, '/overview');
  return (
    <tr
      className="border-b border-dark-800/60 hover:bg-dark-800/30 transition-colors cursor-pointer"
      data-testid={`workspace-row-${workspace.workspace_id}`}
      onClick={() => navigate(target)}
      role="link"
      tabIndex={0}
      aria-label={`View workspace ${workspace.workspace_name}`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          navigate(target);
        }
      }}
    >
      {/* Name + slug */}
      <td className="px-4 py-3">
        <div className="font-medium text-white text-sm">{workspace.workspace_name}</div>
        <div className="text-xs text-gray-500 mt-0.5 font-mono">{workspace.workspace_slug}</div>
      </td>

      {/* Status */}
      <td className="px-4 py-3">
        <WorkspaceStatusBadge status={workspace.status} />
      </td>

      {/* Timezone */}
      <td className="px-4 py-3 text-sm text-gray-300">{workspace.default_timezone}</td>

      {/* Updated */}
      <td className="px-4 py-3 text-sm text-gray-400 tabular-nums">
        {formatDate(workspace.updated_at)}
      </td>

      {/* Created */}
      <td className="px-4 py-3 text-sm text-gray-400 tabular-nums">
        {formatDate(workspace.created_at)}
      </td>
    </tr>
  );
}
