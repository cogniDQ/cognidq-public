import { Navigate } from 'react-router-dom';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { getActorRole, getTenantId } from '../utils/jwt';
import { wsPath } from '../utils/paths';
import TenantLanding from '../pages/TenantLanding';
import { Loader2 } from 'lucide-react';

export default function HubEntryResolver() {
  const { workspaces, loading } = useWorkspace();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
      </div>
    );
  }

  const token = localStorage.getItem('access_token');
  const role = getActorRole(token);

  if (role === 'platform_admin' || role === 'platform_viewer') {
    return <Navigate to="/admin" replace />;
  }

  if (role === 'tenant_admin') {
    const tenantId = getTenantId(token);
    return <Navigate to={tenantId ? `/hub/t/${tenantId}` : '/forbidden'} replace />;
  }

  if (workspaces.length === 1) {
    const tenantId = getTenantId(token);
    return <Navigate to={wsPath(tenantId, workspaces[0].workspace_id, '/overview')} replace />;
  }

  return <TenantLanding />;
}
