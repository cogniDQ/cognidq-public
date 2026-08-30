/**
 * Canonical URL builders for the DQ Hub.
 *
 * All workspace-scoped pages should use the tenant-prefixed form
 * `/hub/t/{tenant_id}/ws/{workspace_id}/...`. The legacy flat form
 * `/hub/ws/{workspace_id}/...` remains mounted as an alias and is used
 * as a fallback when the tenant_id is unknown at build time.
 */

export function wsPath(
  tenantId: string | null | undefined,
  workspaceId: string,
  suffix = '',
): string {
  if (tenantId) return `/hub/t/${tenantId}/ws/${workspaceId}${suffix}`;
  return `/hub/ws/${workspaceId}${suffix}`;
}

export function tenantPath(
  tenantId: string | null | undefined,
  suffix = '',
): string {
  if (tenantId) return `/hub/t/${tenantId}${suffix}`;
  return `/hub${suffix}`;
}
