/**
 * useActiveSupportGrant
 *
 * For a platform_admin/platform_viewer viewing a tenant/workspace, resolves
 * whether they currently hold an active tenant-admin-issued support access
 * grant covering it — the backend now requires one for any workspace or
 * tenant-content read/write. Used by useNavigationMenu (to hide client-side
 * nav without one) and SupportSessionBanner (to show the active session).
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listActiveGrantsForAdmin, type SupportAccessGrant } from '../services/supportAccessService';

export function useActiveSupportGrant(
  isPlatformOp: boolean,
  tenantId: string | null | undefined,
  workspaceId: string | null | undefined,
): { activeGrants: SupportAccessGrant[]; hasActiveGrantHere: boolean; matchingGrant: SupportAccessGrant | null } {
  const { data: activeGrants } = useQuery({
    queryKey: ['support-access-grants', 'active'],
    queryFn: listActiveGrantsForAdmin,
    enabled: isPlatformOp,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const matchingGrant = useMemo(() => {
    if (!isPlatformOp || !activeGrants || activeGrants.length === 0) return null;
    return (
      activeGrants.find(
        (g) =>
          g.tenant_id === tenantId && (!g.workspace_id || g.workspace_id === workspaceId),
      ) ?? null
    );
  }, [isPlatformOp, activeGrants, tenantId, workspaceId]);

  return {
    activeGrants: activeGrants ?? [],
    hasActiveGrantHere: matchingGrant !== null,
    matchingGrant,
  };
}
