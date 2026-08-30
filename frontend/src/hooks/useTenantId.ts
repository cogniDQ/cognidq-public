/**
 * F130 — useTenantId hook
 *
 * Returns the effective tenant_id for the current context:
 * - When inside a workspace context (e.g. platform admin browsing another
 *   tenant's workspace), returns that workspace's tenant_id.
 * - Otherwise falls back to the tenant_id claim from the JWT.
 * Returns empty string when not authenticated.
 */
import { getTenantId } from '../utils/jwt';
import { useWorkspace } from '../contexts/WorkspaceContext';

export function useTenantId(): string {
  const { currentTenantId } = useWorkspace();
  if (currentTenantId) return currentTenantId;
  const token = localStorage.getItem('access_token');
  return getTenantId(token) ?? '';
}
