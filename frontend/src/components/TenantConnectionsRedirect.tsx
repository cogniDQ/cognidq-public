import { Navigate, useParams, useLocation } from 'react-router-dom';
import { getTenantId } from '../utils/jwt';

interface Props {
  /** Optional fixed suffix appended after the connection id (e.g. "/new"). */
  suffix?: string;
}

/**
 * Redirects legacy connection URLs to the new tenant-scoped location:
 *   /hub/connections                          → /hub/t/:tid/connections
 *   /hub/connections/:connection_id           → /hub/t/:tid/connections/:connection_id
 *   /hub/connections/:connection_id/edit      → /hub/t/:tid/connections/:connection_id/edit
 *   /hub/connections/new                      → /hub/t/:tid/connections/new
 *   /hub/t/:tid/ws/:wid/connections[/...]     → /hub/t/:tid/connections[/...]
 *
 * The tenant id is taken from the URL path when available, otherwise from
 * the JWT `tenant_id` claim. If neither resolves, falls back to /hub.
 */
export default function TenantConnectionsRedirect({ suffix }: Props) {
  const params = useParams();
  const location = useLocation();

  const token =
    typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const tenantId = params.tenant_id ?? getTenantId(token);
  if (!tenantId) return <Navigate replace to="/hub" />;

  const connectionId = params.connection_id;
  let target = `/hub/t/${tenantId}/connections`;
  if (connectionId) target += `/${connectionId}`;
  // The remainder of the path after /connections (handles deep-link splats and /edit)
  const splat = (params['*'] as string | undefined) ?? '';
  if (splat) target += `/${splat}`;
  if (suffix) target += suffix;
  return <Navigate replace to={`${target}${location.search}`} />;
}
