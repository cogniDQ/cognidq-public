/**
 * TenantAdminRedirect — redirects legacy /tenant-admin* paths to the unified
 * /hub/t/:tenantId* hierarchy. Pulls tenant_id from the JWT.
 *
 * If the caller has no tenant_id (e.g. platform_admin who hasn't picked a
 * tenant yet), routes to /admin/tenants instead.
 */
import React from 'react';
import { Navigate } from 'react-router-dom';
import { getTenantId, getActorRole } from '../../utils/jwt';

export default function TenantAdminRedirect({ suffix = '' }: { suffix?: string }) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const tenantId = getTenantId(token);
  const role = getActorRole(token);

  if (!tenantId) {
    if (role === 'platform_admin' || role === 'platform_viewer') {
      return <Navigate to="/admin/tenants" replace />;
    }
    return <Navigate to="/forbidden" replace />;
  }

  return <Navigate to={`/hub/t/${tenantId}${suffix}`} replace />;
}
