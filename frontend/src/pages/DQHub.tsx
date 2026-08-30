/**
 * DQ Hub - Databricks-like interface with side navigation
 * F077: Dynamic role-based sidebar
 */
import React, { useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { ChevronLeft, ChevronRight, User, Settings, LogOut } from 'lucide-react';
import Logo from '../components/Logo';
import { useAuth } from '../contexts/AuthContext';
import { WorkspaceProvider, useWorkspace } from '../contexts/WorkspaceContext';
import { useNavigationMenu } from '../hooks/useNavigationMenu';
import ContextHeader from '../components/ContextHeader';
import RoleBadge from '../components/RoleBadge';
import RoleStripe from '../components/RoleStripe';
import NotificationBell from '../components/NotificationBell';
import ThemeToggle from '../theme/ThemeToggle';
import { useTheme } from '../theme/ThemeContext';
import { getActorRole } from '../utils/jwt';

/** Inner shell — must be inside WorkspaceProvider */
const DQHubInner: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { resolved } = useTheme();
  const isDark = resolved === 'dark';
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [showUserDropdown, setShowUserDropdown] = useState(false);

  const platformRole = getActorRole(localStorage.getItem('access_token'));
  const isPlatformAdmin = platformRole === 'platform_admin';
  const { currentWorkspace } = useWorkspace();
  const currentWorkspaceId = currentWorkspace?.workspace_id;

  // Self-contained: resolves workspace_id from URL params, permissions internally.
  const { sections } = useNavigationMenu();

  const isActive = (path: string) => {
    if (path === '/hub' && location.pathname === '/hub') return true;
    if (path !== '/hub' && location.pathname.startsWith(path)) return true;
    return false;
  };

  const handleLogout = async () => {
    await logout();
    navigate('/auth/login');
  };

  return (
    <div className="h-screen flex flex-col bg-surface text-content">
      <RoleStripe workspaceId={currentWorkspaceId} />
      <div className="flex-1 flex overflow-hidden">
      {/* Sidebar */}
      <div
        className={`${
          sidebarCollapsed ? 'w-16' : 'w-64'
        } bg-surface-raised border-r border-edge flex flex-col min-h-0 transition-all duration-300`}
      >
        {/* Logo/Brand */}
        <div className="h-16 flex items-center justify-between px-4 border-b border-edge">
          {!sidebarCollapsed && (
            <Link to="/" className="flex items-center">
              <Logo variant={isDark ? 'light' : 'full'} className="h-7 w-auto" />
            </Link>
          )}
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="p-2 hover:bg-surface-overlay rounded-lg transition-colors text-content-muted hover:text-content"
          >
            {sidebarCollapsed ? (
              <ChevronRight className="w-5 h-5" />
            ) : (
              <ChevronLeft className="w-5 h-5" />
            )}
          </button>
        </div>

        {/* Workspace Selector removed — users access workspaces via the Workspaces page. */}

        {/* Navigation Menu — dynamic per role */}
        {/* F1: min-h-0 lets flex-1 actually shrink so overflow-y-auto clips */}
        <nav className="flex-1 min-h-0 p-3 space-y-1 overflow-y-auto">
          {sections.map((section, sIdx) => (
            <React.Fragment key={section.id}>
              {/* Section divider + label */}
              {sIdx > 0 && <div className="my-2 border-t border-edge" />}
              {!sidebarCollapsed && section.label && (
                <div className="px-3 py-1 text-xs font-semibold text-content-subtle uppercase tracking-wider">
                  {section.label}
                </div>
              )}
              {section.items.map((item) => (
                <Link
                  key={item.id}
                  to={item.path}
                  className={`flex items-center space-x-3 px-3 py-2 rounded-lg transition-colors ${
                    isActive(item.path)
                      ? 'bg-gradient-to-r from-brand to-info text-white shadow-sm'
                      : 'text-content-muted hover:bg-surface-overlay hover:text-content'
                  } ${sidebarCollapsed ? 'justify-center' : ''}`}
                  title={sidebarCollapsed ? item.label : ''}
                >
                  <item.icon className="w-5 h-5 flex-shrink-0" />
                  {!sidebarCollapsed && <span className="text-sm font-medium">{item.label}</span>}
                </Link>
              ))}
            </React.Fragment>
          ))}
        </nav>

        {/* User Menu */}
        {user && (
          <div className="relative p-3 border-t border-edge">
            <button
              onClick={() => setShowUserDropdown(!showUserDropdown)}
              className={`w-full flex items-center space-x-3 p-2 hover:bg-surface-overlay rounded-lg transition-colors ${
                sidebarCollapsed ? 'justify-center' : ''
              }`}
            >
              <div className="w-8 h-8 bg-gradient-to-r from-brand to-info rounded-full flex items-center justify-center flex-shrink-0">
                <span className="text-white text-sm font-semibold">
                  {user.full_name?.[0]?.toUpperCase() || user.email[0].toUpperCase()}
                </span>
              </div>
              {!sidebarCollapsed && (
                <div className="flex-1 text-left overflow-hidden">
                  <div className="text-sm text-content truncate">{user.full_name || user.email}</div>
                  <div className="text-xs text-content-muted truncate">{user.email}</div>
                </div>
              )}
            </button>

            {showUserDropdown && !sidebarCollapsed && (
              <div className="absolute bottom-full left-3 right-3 mb-2 bg-surface-overlay rounded-lg shadow-lg border border-edge-strong z-50">
                <Link
                  to="/hub/profile"
                  className="flex items-center space-x-2 px-4 py-2 hover:bg-surface-raised rounded-t-lg text-content"
                  onClick={() => setShowUserDropdown(false)}
                >
                  <User className="w-4 h-4" />
                  <span className="text-sm">Profile</span>
                </Link>
                <Link
                  to="/hub/settings"
                  className="flex items-center space-x-2 px-4 py-2 hover:bg-surface-raised text-content"
                  onClick={() => setShowUserDropdown(false)}
                >
                  <Settings className="w-4 h-4" />
                  <span className="text-sm">Settings</span>
                </Link>
                <button
                  onClick={() => {
                    setShowUserDropdown(false);
                    handleLogout();
                  }}
                  className="w-full flex items-center space-x-2 px-4 py-2 hover:bg-surface-raised rounded-b-lg text-left text-danger"
                >
                  <LogOut className="w-4 h-4" />
                  <span className="text-sm">Logout</span>
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top Bar */}
        <div className="h-16 bg-surface-raised border-b border-edge flex items-center justify-between px-6">
          <div className="flex items-center space-x-4">
            <Link
              to={isPlatformAdmin ? '/admin/tenants' : '/'}
              className="text-sm text-content-muted hover:text-content transition-colors"
            >
              ← Back to Platform
            </Link>
          </div>

          {/* Context breadcrumb: tenant > workspace */}
          <div className="flex items-center gap-3">
            <ContextHeader />
            <ThemeToggle />
            <NotificationBell workspaceId={currentWorkspaceId} />
            <RoleBadge workspaceId={currentWorkspaceId} />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto bg-surface text-content">
          <div className="p-6">
            <Outlet />
          </div>
        </div>
        <Toaster position="top-right" toastOptions={{ duration: 4000 }} />
      </div>
      </div>
    </div>
  );
};

/** Outer wrapper that provides WorkspaceContext */
const DQHub: React.FC = () => (
  <WorkspaceProvider>
    <DQHubInner />
  </WorkspaceProvider>
);

export default DQHub;
