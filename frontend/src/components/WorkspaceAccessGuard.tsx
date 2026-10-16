/**
 * WorkspaceAccessGuard — workspace membership guard for workspace-scoped routes.
 *
 * Wraps all /hub/ws/:workspace_id/* child routes (F131 P03 / BUG: RBAC bypass).
 * Checks:
 *   1. workspace_id in URL is a valid UUID — if not, renders NotFoundPage.
 *   2. GET /api/v1/workspaces/{id} succeeds (200) — if 403/404, redirects to
 *      the appropriate page. Any other status is treated as forbidden.
 *
 * platform_admin gets no special bypass here: the backend now requires an
 * active tenant-admin-issued support access grant for cross-tenant reads,
 * so a platform_admin without one sees the same 403 as anyone else — just
 * with guidance pointing at the support-access console instead of a bare
 * "forbidden" page.
 *
 * Renders <Outlet /> when access is granted.
 */
import { useEffect, useState } from 'react';
import { Outlet, useParams, Navigate, Link } from 'react-router-dom';
import { getWorkspace } from '../services/workspace';
import { getActorRole } from '../utils/jwt';
import { useWorkspace } from '../contexts/WorkspaceContext';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type AccessState = 'loading' | 'granted' | 'forbidden' | 'not_found' | 'needs_grant';

export default function WorkspaceAccessGuard() {
  const { workspace_id } = useParams<{ workspace_id: string }>();
  const [access, setAccess] = useState<AccessState>('loading');
  const { setCurrentWorkspaceDetail } = useWorkspace();

  useEffect(() => {
    // Invalid UUID → 404 immediately, no network call needed.
    if (!workspace_id || !UUID_RE.test(workspace_id)) {
      setAccess('not_found');
      return;
    }

    getWorkspace(workspace_id)
      .then((resp) => {
        setCurrentWorkspaceDetail(resp.data);
        setAccess('granted');
      })
      .catch((err: any) => {
        const status = err?.response?.status;
        const token = localStorage.getItem('access_token');
        const role = getActorRole(token);
        if (status === 403 && role === 'platform_admin') {
          setAccess('needs_grant');
        } else if (status === 404) {
          setAccess('not_found');
        } else {
          setAccess('forbidden');
        }
      });
  }, [workspace_id, setCurrentWorkspaceDetail]);

  if (access === 'loading') {
    return (
      <div className="min-h-screen bg-dark-950 flex items-center justify-center">
        <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-solid border-primary-500 border-r-transparent" />
      </div>
    );
  }

  if (access === 'not_found') {
    return <Navigate to="/404" replace />;
  }

  if (access === 'needs_grant') {
    return (
      <div className="min-h-screen bg-dark-950 flex items-center justify-center px-4">
        <div className="max-w-md text-center space-y-4">
          <h1 className="text-xl font-semibold text-white">No active support access grant</h1>
          <p className="text-gray-400 text-sm">
            This workspace belongs to a client tenant. Ask the tenant admin to grant you
            temporary support access, or check your currently active grants.
          </p>
          <Link to="/admin" className="inline-block text-primary-400 hover:underline text-sm">
            Go to the admin console →
          </Link>
        </div>
      </div>
    );
  }

  if (access === 'forbidden') {
    return <Navigate to="/forbidden" replace />;
  }

  return <Outlet />;
}
