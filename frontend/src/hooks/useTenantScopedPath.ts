/**
 * useTenantScopedPath
 *
 * Single hook that resolves the active tenant_id from (in order):
 *   1. the current URL params (`:tenant_id`)
 *   2. the active workspace's tenant (WorkspaceContext.currentTenantId)
 *   3. the user's JWT `tenant_id` claim
 *
 * Returns helpers that build canonical workspace-scoped and tenant-scoped
 * paths under `/hub/t/{tenant_id}/...`. When the tenant_id cannot be
 * resolved (e.g. legacy contexts), the helpers fall back to the flat
 * `/hub/ws/...` and `/hub/...` forms so navigation still works.
 */
import { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { getTenantId } from '../utils/jwt';
import { wsPath, tenantPath } from '../utils/paths';

interface UseTenantScopedPathResult {
  tenantId: string | null;
  wsPath: (workspaceId: string, suffix?: string) => string;
  tenantPath: (suffix?: string) => string;
}

export function useTenantScopedPath(): UseTenantScopedPathResult {
  const params = useParams<{ tenant_id?: string }>();
  const { currentTenantId } = useWorkspace();
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const jwtTenantId = getTenantId(token);

  const tenantId = params.tenant_id ?? currentTenantId ?? jwtTenantId ?? null;

  return useMemo(
    () => ({
      tenantId,
      wsPath: (workspaceId: string, suffix = '') => wsPath(tenantId, workspaceId, suffix),
      tenantPath: (suffix = '') => tenantPath(tenantId, suffix),
    }),
    [tenantId],
  );
}
