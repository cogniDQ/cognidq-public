/**
 * AdminGuard — platform role guard for admin pages (F129 P05).
 *
 * All /admin/* routes require a platform role (platform_admin or platform_viewer).
 * The requireAdmin prop bypass has been removed per TDD §6.14.
 */
import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { getActorRole } from '../../utils/jwt';
import ForbiddenPage from '../../pages/admin/ForbiddenPage';

// F129 P05: `requireAdmin` prop removed. All /admin/* routes always require
// a platform role (platform_admin or platform_viewer).

export default function AdminGuard({ children }: { children: React.ReactNode }) {
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

  const role = getActorRole(localStorage.getItem('access_token'));
  if (!role || !['platform_admin', 'platform_viewer'].includes(role)) {
    return <ForbiddenPage />;
  }

  return <>{children}</>;
}
