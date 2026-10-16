/**
 * AdminLayout — shared shell for all admin pages.
 *
 * Provides a simple header with the product name and a link back to the
 * main app, plus a main content area for the page children.
 */
import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { LogOut, ChevronRight, LayoutDashboard } from 'lucide-react';
import Logo from '../Logo';
import { Toaster } from 'react-hot-toast';
import { useAuth } from '../../contexts/AuthContext';
import { getActorRole } from '../../utils/jwt';
import RoleBadge from '../RoleBadge';
import RoleStripe from '../RoleStripe';

interface AdminLayoutProps {
  children: React.ReactNode;
}

export default function AdminLayout({ children }: AdminLayoutProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const token = localStorage.getItem('access_token');
  const isPlatformAdmin = getActorRole(token) === 'platform_admin';

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-dark-950 text-gray-100">
      <RoleStripe />
      {/* Top navigation bar */}
      <header className="sticky top-0 z-50 border-b border-dark-800/60 bg-dark-950/90 backdrop-blur-sm">
        <div className="mx-auto max-w-screen-2xl px-6 h-14 flex items-center justify-between">
          {/* Brand + breadcrumb */}
          <div className="flex items-center space-x-3 text-sm text-gray-400">
            <Link to="/" className="flex items-center hover:opacity-90 transition-opacity">
              <Logo variant="light" className="h-7 w-auto" />
            </Link>
            <ChevronRight className="w-4 h-4" />
            <Link to="/admin" className="hover:text-white transition-colors">
              Admin
            </Link>
          </div>

          {/* Right side: DQ Hub link + user + logout */}
          <div className="flex items-center space-x-4">
            <RoleBadge />
            {!isPlatformAdmin && (
              <Link
                to="/hub"
                className="flex items-center space-x-1.5 text-sm text-gray-400 hover:text-white transition-colors"
                aria-label="Back to DQ Hub"
              >
                <LayoutDashboard className="w-4 h-4" />
                <span className="hidden sm:block">DQ Hub</span>
              </Link>
            )}
            {user && (
              <span className="text-sm text-gray-400 hidden sm:block">{user.email}</span>
            )}
            <button
              onClick={handleLogout}
              className="flex items-center space-x-1 text-sm text-gray-400 hover:text-white transition-colors"
              aria-label="Log out"
            >
              <LogOut className="w-4 h-4" />
              <span className="hidden sm:block">Logout</span>
            </button>
          </div>
        </div>
      </header>

      {/* Page content */}
      <main className="mx-auto max-w-screen-2xl px-6 py-8">
        {children}
      </main>

      {/* Toast notifications for admin actions */}
      <Toaster
        position="bottom-right"
        toastOptions={{
          duration: 4000,
          style: {
            background: '#1e293b',
            color: '#f1f5f9',
            border: '1px solid rgba(99,102,241,0.3)',
            borderRadius: '0.75rem',
          },
          success: {
            iconTheme: { primary: '#22c55e', secondary: '#1e293b' },
          },
          error: {
            iconTheme: { primary: '#ef4444', secondary: '#1e293b' },
          },
        }}
      />
    </div>
  );
}
