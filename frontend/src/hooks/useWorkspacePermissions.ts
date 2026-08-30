/**
 * useWorkspacePermissions — F007 P04
 *
 * A lightweight hook that exposes `can(action)` and `roleName` for the
 * authenticated actor in a specific workspace.
 *
 * Design:
 *   - Reads role from the fetched members list (no extra API call).
 *   - Permission evaluation is done client-side against FIXED_ROLE_PERMISSIONS.
 *   - Re-evaluates when workspaceId or the actor's userId changes.
 *
 * Usage:
 *   const { can, roleName } = useWorkspacePermissions(workspaceId, actorId);
 *   if (can('datasources:write')) { ... }
 */
import { useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getMemberRole,
  FIXED_ROLE_PERMISSIONS,
  WorkspaceRoleName,
} from '../services/workspaceRoles';
import { getActorRole } from '../utils/jwt';

/** Platform roles that never have workspace role assignments. */
const PLATFORM_ROLES = new Set(['platform_admin', 'platform_viewer']);

interface UseWorkspacePermissionsResult {
  /** Check whether the actor may perform *action* in this workspace. */
  can: (action: string) => boolean;
  /** The actor's current workspace role slug, or null when loading/no role. */
  roleName: WorkspaceRoleName | null;
  /** True while the role is being fetched. */
  loading: boolean;
}

/**
 * Returns workspace-level permission helpers for *actorId* in *workspaceId*.
 *
 * @param workspaceId  UUID of the workspace.
 * @param actorId      UUID of the authenticated actor (from JWT).
 */
export function useWorkspacePermissions(
  workspaceId: string | undefined,
  actorId: string | undefined,
): UseWorkspacePermissionsResult {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const platformRole = getActorRole(token);
  // Platform operators never have workspace role assignments — skip the API call.
  const isPlatformOperator = !!platformRole && PLATFORM_ROLES.has(platformRole);

  const { data: assignment, isLoading } = useQuery({
    queryKey: ['workspace-role', workspaceId, actorId],
    queryFn: () => getMemberRole(workspaceId!, actorId!),
    enabled:
      Boolean(workspaceId) &&
      Boolean(actorId) &&
      !isPlatformOperator,
    staleTime: 60_000,
    // 404 means "no role" — treat as null, don't throw
    retry: (failureCount, error: unknown) => {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 404) return false;
      return failureCount < 2;
    },
  });

  const roleName: WorkspaceRoleName | null =
    (assignment?.role_name as WorkspaceRoleName) ?? null;

  const permissionSet: ReadonlySet<string> = useMemo(() => {
    if (!roleName) return new Set<string>();
    return FIXED_ROLE_PERMISSIONS[roleName] ?? new Set<string>();
  }, [roleName]);

  const can = useCallback(
    (action: string): boolean => permissionSet.has(action),
    [permissionSet],
  );

  return { can, roleName, loading: isLoading };
}
