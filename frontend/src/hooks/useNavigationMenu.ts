/**
 * useNavigationMenu — F129 P04
 *
 * Returns filtered, workspace-id-injected nav sections for the DQ Hub sidebar.
 *
 * Self-contained: reads platform role from JWT, workspace permissions internally.
 * workspaceId resolution order: argument → useParams().workspace_id → WorkspaceContext.
 *
 * Section visibility rules:
 *   - 'always'    — always shown (after item-level permission filtering)
 *   - 'workspace' — shown only when a workspace_id is active
 *   - 'platform'  — shown only for platform_admin / platform_viewer
 */
import { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { getRealActorRole, getActorId, getTenantId } from '../utils/jwt';
import { FIXED_ROLE_PERMISSIONS, type WorkspaceRoleName } from '../services/workspaceRoles';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { useWorkspacePermissions } from './useWorkspacePermissions';
import { NAV_SECTIONS, type NavSection } from '../config/navigationConfig';

interface UseNavigationMenuResult {
  sections: NavSection[];
  loading: boolean;
}

/**
 * @param workspaceId  Optional explicit workspace ID override.
 *                     Falls back to useParams().workspace_id then WorkspaceContext.
 */
export function useNavigationMenu(workspaceId?: string): UseNavigationMenuResult {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const platformRole = getRealActorRole(token);
  const actorId = getActorId(token);

  const isPlatformOp = platformRole === 'platform_admin' || platformRole === 'platform_viewer';
  // Tenant admins are super-users within their tenant: they should see every
  // workspace-scoped nav item (members, roles, connections, etc.) and the
  // tenant Workspaces link, even though they have no workspace_role row.
  const isTenantAdmin = platformRole === 'tenant_admin';

  // Workspace ID resolution: argument → URL params → context
  const params = useParams<{ workspace_id?: string; tenant_id?: string }>();
  const { currentWorkspace, currentTenantId } = useWorkspace();
  const effectiveWorkspaceId =
    workspaceId ?? params.workspace_id ?? currentWorkspace?.workspace_id;
  // Tenant ID resolution: URL params → workspace's own tenant → JWT claim
  const effectiveTenantId =
    params.tenant_id ?? currentTenantId ?? getTenantId(token) ?? '';

  // Resolve workspace permissions (skipped for platform operators — no workspace role)
  const { roleName: wsRoleName, loading: wsRoleLoading } = useWorkspacePermissions(
    isPlatformOp ? undefined : effectiveWorkspaceId,
    isPlatformOp ? undefined : (actorId ?? undefined),
  );

  const workspacePermissions: ReadonlySet<string> = useMemo(() => {
    if (!wsRoleName) return new Set<string>();
    return FIXED_ROLE_PERMISSIONS[wsRoleName as WorkspaceRoleName] ?? new Set<string>();
  }, [wsRoleName]);

  const sections: NavSection[] = useMemo(() => {
    const result: NavSection[] = [];

    for (const section of NAV_SECTIONS) {
      // Section visibility gate
      if (section.visibility === 'platform' && !isPlatformOp) continue;
      if (section.visibility === 'workspace' && !effectiveWorkspaceId) continue;
      // Tenant section: shown only for tenant_admin (and platform_admin preview).
      if (section.visibility === 'tenant' && !(isTenantAdmin || platformRole === 'platform_admin')) continue;

      // Filter items by permission
      const visibleItems = section.items.filter((item) => {
        // F132 — platform_admin should not see the Workspaces link (BUG-012)
        if (item.id === 'workspaces' && platformRole === 'platform_admin') return false;
        if (!item.requiredPermission && !item.requiredPlatformRole) return true;
        if (item.requiredPlatformRole) {
          return !!platformRole && item.requiredPlatformRole.includes(platformRole);
        }
        if (item.requiredPermission) {
          if (workspacePermissions.has(item.requiredPermission)) return true;
          // Platform operators can see all workspace-scoped items
          if (isPlatformOp) return true;
          // Tenant admins see all workspace-scoped items in their tenant
          if (isTenantAdmin) return true;
          return false;
        }
        return false;
      });

      if (visibleItems.length === 0) continue;

      // Inject workspace_id and tenant_id into paths.
      // When tenant_id is unknown, strip the `/t/:tenant_id` segment so the
      // legacy flat `/hub/ws/:workspace_id/...` route still resolves.
      const injectedItems = visibleItems.map((item) => {
        let path = item.path;
        if (effectiveWorkspaceId) path = path.replace(':workspace_id', effectiveWorkspaceId);
        if (effectiveTenantId) {
          path = path.replace(':tenant_id', effectiveTenantId);
        } else {
          path = path.replace('/t/:tenant_id', '');
        }
        return { ...item, path };
      });

      result.push({ ...section, items: injectedItems });
    }

    return result.sort((a, b) => a.order - b.order);
  }, [isPlatformOp, isTenantAdmin, platformRole, workspacePermissions, effectiveWorkspaceId, effectiveTenantId]);

  return { sections, loading: wsRoleLoading };
}
