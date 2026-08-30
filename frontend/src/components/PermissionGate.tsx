/**
 * PermissionGate — F129 P05
 *
 * Renders `children` when the current user has the required workspace permission.
 * Renders `fallback` (default: <ForbiddenPage />) when the permission is absent.
 *
 * Per TDD §6.6.
 *
 * Platform operators (platform_admin / platform_viewer) bypass workspace permission
 * checks and always see `children`.
 */
import type { ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import { getActorRole, getActorId } from '../utils/jwt';
import { FIXED_ROLE_PERMISSIONS, type WorkspaceRoleName } from '../services/workspaceRoles';
import { useWorkspacePermissions } from '../hooks/useWorkspacePermissions';
import ForbiddenPage from '../pages/admin/ForbiddenPage';

interface PermissionGateProps {
  /** Workspace-level permission string, e.g. 'view_audit_logs'. */
  permission: string;
  children: ReactNode;
  /** Rendered when permission is absent. Defaults to <ForbiddenPage />. */
  fallback?: ReactNode;
}

export default function PermissionGate({ permission, children, fallback }: PermissionGateProps) {
  const params = useParams<{ workspace_id?: string }>();
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const platformRole = getActorRole(token);
  const actorId = getActorId(token);
  const isPlatformOp = platformRole === 'platform_admin' || platformRole === 'platform_viewer';

  const { roleName, loading } = useWorkspacePermissions(
    isPlatformOp ? undefined : params.workspace_id,
    isPlatformOp ? undefined : (actorId ?? undefined),
  );

  // Platform operators bypass workspace permission checks
  if (isPlatformOp) return <>{children}</>;

  if (loading) return null;

  const permissions = roleName
    ? (FIXED_ROLE_PERMISSIONS[roleName as WorkspaceRoleName] ?? new Set<string>())
    : new Set<string>();

  if (!permissions.has(permission)) {
    return <>{fallback ?? <ForbiddenPage />}</>;
  }

  return <>{children}</>;
}
