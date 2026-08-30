/**
 * WorkspaceAccessGuard — workspace membership guard for workspace-scoped routes.
 *
 * Wraps all /hub/ws/:workspace_id/* child routes (F131 P03 / BUG: RBAC bypass).
 * Checks:
 *   1. workspace_id in URL is a valid UUID — if not, renders NotFoundPage.
 *   2. User is a platform_admin (JWT actor_role) — if so, bypass membership check.
 *   3. GET /api/v1/workspaces/{id} succeeds (200) — if 403/404, redirects to
 *      the appropriate page. Any other status is treated as forbidden.
 *
 * Renders <Outlet /> when access is granted.
 */
import React, { useEffect, useState } from 'react';
import { Outlet, useParams, Navigate } from 'react-router-dom';
import { getWorkspace } from '../services/workspace';
import { getActorRole } from '../utils/jwt';
import { useWorkspace } from '../contexts/WorkspaceContext';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type AccessState = 'loading' | 'granted' | 'forbidden' | 'not_found';

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

    // Fetch workspace detail for all roles:
    // - For regular users: verifies membership (403/404 → forbidden/not_found)
    // - For platform admins: fetches cross-tenant detail (backend now allows this)
    //   and syncs the workspace context so Connections/Glossary use the right tenant.
    getWorkspace(workspace_id)
      .then((resp) => {
        setCurrentWorkspaceDetail(resp.data);
        setAccess('granted');
      })
      .catch((err: any) => {
        const status = err?.response?.status;
        const token = localStorage.getItem('access_token');
        const role = getActorRole(token);
        if (role === 'platform_admin') {
          // Platform admin: grant access even if detail fetch fails
          setAccess('granted');
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

  if (access === 'forbidden') {
    return <Navigate to="/forbidden" replace />;
  }

  return <Outlet />;
}
