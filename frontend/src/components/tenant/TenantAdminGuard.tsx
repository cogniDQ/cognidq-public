/**
 * TenantAdminGuard — allows only authenticated users whose JWT actor_role is
 * `tenant_admin`. Redirects others to /forbidden (or /auth/login if not
 * authenticated). Mirrors AdminGuard but for the first-class Tenant Admin
 * role introduced to match customer ownership boundaries.
 */
import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { getActorRole } from '../../utils/jwt';
import ForbiddenPage from '../../pages/admin/ForbiddenPage';

export default function TenantAdminGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-950 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-solid border-primary-500 border-r-transparent" />
          <p className="mt-4 text-gray-400">Loading</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    const returnTo = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/auth/login?returnTo=${returnTo}`} replace />;
  }

  const token = localStorage.getItem('access_token');
  const role = getActorRole(token);
  // platform_admin also permitted so the full platform operator can preview
  // tenant admin pages while assisting customers.
  if (role !== 'tenant_admin' && role !== 'platform_admin') {
    return <ForbiddenPage />;
  }

  return <>{children}</>;
}
