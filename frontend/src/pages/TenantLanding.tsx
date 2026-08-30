import { useNavigate } from 'react-router-dom';
import { Plus, Building2, ArrowRight } from 'lucide-react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { getTenantId } from '../utils/jwt';
import { wsPath } from '../utils/paths';

export default function TenantLanding() {
  const navigate = useNavigate();
  const { workspaces } = useWorkspace();
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const tenantId = getTenantId(token);

  if (workspaces.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <Building2 className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-gray-300 mb-2">No Workspaces</h2>
          <p className="text-gray-500 mb-6">Create a workspace to get started with data quality monitoring.</p>
          <button
            onClick={() => navigate('/hub/workspaces/new')}
            className="btn-primary flex items-center space-x-2 mx-auto"
          >
            <Plus className="w-4 h-4" />
            <span>Create Workspace</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold gradient-text mb-2">Your Workspaces</h1>
          <p className="text-gray-400">Select a workspace to open</p>
        </div>
        <button
          onClick={() => navigate('/hub/workspaces/new')}
          className="btn-primary flex items-center space-x-2"
        >
          <Plus className="w-4 h-4" />
          <span>New Workspace</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {workspaces.map((ws) => (
          <button
            key={ws.workspace_id}
            onClick={() => navigate(wsPath(tenantId, ws.workspace_id, '/overview'))}
            className="glass p-5 rounded-lg hover:border-primary-500/50 transition-all text-left group"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-lg text-gray-200 mb-1 truncate">
                  {ws.workspace_name}
                </h3>
                <p className="text-sm text-gray-500">{ws.workspace_slug}</p>
              </div>
              <ArrowRight className="w-5 h-5 text-gray-600 group-hover:text-primary-400 transition-colors flex-shrink-0 mt-1" />
            </div>
            <div className="mt-3 text-xs text-gray-600">
              Created {new Date(ws.created_at).toLocaleDateString()}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
