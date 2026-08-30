/**
 * navigationConfig.ts — F129 P04
 *
 * Section-based navigation config for the DQ Hub sidebar.
 * Three top-level sections: tenant (always), workspace (when ws active), platform (platform operators).
 * Workspace-section items use ':workspace_id' placeholder — injected by useNavigationMenu.
 */
import {
  LayoutDashboard,
  Boxes,
  Database,
  BookOpen,
  Table2,
  GitBranch,
  Wand2,
  Shield,
  BarChart3,
  PieChart,
  AlertTriangle,
  Flame,
  Bell,
  Mail,
  Users,
  Key,
  Settings2,
  History,
  FileSearch,
  Server,
  Activity,
  type LucideIcon,
} from 'lucide-react';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

/** Visibility rule for a section. */
export type NavSectionVisibility = 'always' | 'workspace' | 'platform' | 'tenant';

export interface NavItem {
  id: string;
  label: string;
  /** Path may contain ':workspace_id' — replaced at render time by useNavigationMenu. */
  path: string;
  icon: LucideIcon;
  /** Workspace-level permission required. */
  requiredPermission?: string;
  /** Platform role(s) that grant access (overrides workspace check). */
  requiredPlatformRole?: readonly string[];
}

export interface NavSection {
  id: string;
  label: string;
  order: number;
  visibility: NavSectionVisibility;
  items: NavItem[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Section definitions
// ─────────────────────────────────────────────────────────────────────────────

export const NAV_SECTIONS: readonly NavSection[] = [
  // ── Tenant — always visible ──────────────────────────────────────────────
  {
    id: 'tenant',
    label: 'Organization',
    order: 0,
    visibility: 'always',
    items: [
      { id: 'workspaces', label: 'Workspaces', path: '/hub/workspaces', icon: Boxes, requiredPermission: 'workspaces:read' },
    ],
  },

  // ── Tenant Admin — shown only for tenant_admin (or platform_admin preview) ─
  {
    id: 'tenant-admin',
    label: 'Tenant Administration',
    order: 1,
    visibility: 'tenant',
    items: [
      { id: 'tenant-dashboard',   label: 'Tenant Dashboard',     path: '/hub/t/:tenant_id',             icon: LayoutDashboard, requiredPlatformRole: ['tenant_admin', 'platform_admin'] },
      { id: 'tenant-members',     label: 'Tenant Members',       path: '/hub/t/:tenant_id/members',     icon: Users,           requiredPlatformRole: ['tenant_admin', 'platform_admin'] },
      { id: 'tenant-assignments', label: 'Workspace Assignments', path: '/hub/t/:tenant_id/assignments', icon: Key,             requiredPlatformRole: ['tenant_admin', 'platform_admin'] },
      { id: 'tenant-connections', label: 'Connections',           path: '/hub/t/:tenant_id/connections', icon: Database,        requiredPlatformRole: ['tenant_admin', 'platform_admin'] },
    ],
  },

  // ── Workspace — shown only when a workspace is active ────────────────────
  {
    id: 'workspace',
    label: 'Workspace',
    order: 2,
    visibility: 'workspace',
    items: [
      { id: 'overview',          label: 'Overview',          path: '/hub/t/:tenant_id/ws/:workspace_id/overview',          icon: LayoutDashboard },
      // Glossary is a tenant-scoped resource surfaced in workspace context.
      // Connections live under Tenant Administration (managed by tenant_admin only).
      { id: 'glossary',          label: 'Glossary',          path: '/hub/t/:tenant_id/ws/:workspace_id/glossary',          icon: BookOpen },
      { id: 'datasets',          label: 'Datasets',          path: '/hub/t/:tenant_id/ws/:workspace_id/datasets',          icon: Table2,      requiredPermission: 'datasets:read' },
      { id: 'flows',             label: 'Flows',             path: '/hub/t/:tenant_id/ws/:workspace_id/flows',             icon: GitBranch,   requiredPermission: 'executions:read' },
      { id: 'nl-rule-builder',   label: 'NL Rule Builder',   path: '/hub/t/:tenant_id/ws/:workspace_id/nl-rule-builder',   icon: Wand2,       requiredPermission: 'rules:write' },
      { id: 'rules',             label: 'Rules',             path: '/hub/t/:tenant_id/ws/:workspace_id/rules',             icon: Shield,      requiredPermission: 'rules:read' },
      { id: 'issues',            label: 'Issues',            path: '/hub/t/:tenant_id/ws/:workspace_id/issues',            icon: AlertTriangle, requiredPermission: 'issues:read' },
      { id: 'incidents',         label: 'Incidents',         path: '/hub/t/:tenant_id/ws/:workspace_id/incidents',         icon: Flame,       requiredPermission: 'incidents:read' },
      { id: 'alerts',            label: 'Alerts',            path: '/hub/t/:tenant_id/ws/:workspace_id/alerts',            icon: Bell,        requiredPermission: 'alerts:read' },
      { id: 'notification-log',  label: 'Notification Log',  path: '/hub/t/:tenant_id/ws/:workspace_id/notification-log',  icon: Mail,        requiredPermission: 'alerts:read' },
      { id: 'anomalies',         label: 'Anomalies',         path: '/hub/t/:tenant_id/ws/:workspace_id/anomalies',         icon: Activity,    requiredPermission: 'alerts:read' },
      { id: 'flow-reports',      label: 'Flow Reports',      path: '/hub/t/:tenant_id/ws/:workspace_id/flow-reports',      icon: BarChart3,   requiredPermission: 'reports:read' },
      { id: 'quality-reports',   label: 'Quality Reports',   path: '/hub/t/:tenant_id/ws/:workspace_id/quality-reports',   icon: PieChart,    requiredPermission: 'reports:read' },
      { id: 'members',           label: 'Members',           path: '/hub/t/:tenant_id/ws/:workspace_id/members',           icon: Users,       requiredPermission: 'members:read' },
      { id: 'roles',             label: 'Roles & Permissions', path: '/hub/t/:tenant_id/ws/:workspace_id/roles',           icon: Key,         requiredPermission: 'roles:assign' },
      { id: 'workspace-settings', label: 'Workspace Settings', path: '/hub/t/:tenant_id/ws/:workspace_id/settings',       icon: Settings2,   requiredPermission: 'settings:write' },
      { id: 'activity-log',      label: 'Activity Log',      path: '/hub/t/:tenant_id/ws/:workspace_id/activity-log',      icon: History,     requiredPermission: 'view_audit_logs' },
      { id: 'permission-audit',  label: 'Permission Audit',  path: '/hub/t/:tenant_id/ws/:workspace_id/permission-audit',  icon: FileSearch,  requiredPermission: 'view_audit_logs' },
    ],
  },

  // ── Platform — shown only for platform_admin / platform_viewer ───────────
  {
    id: 'platform',
    label: 'Platform',
    order: 3,
    visibility: 'platform',
    items: [
      { id: 'tenants', label: 'Tenants', path: '/admin/tenants', icon: Server, requiredPlatformRole: ['platform_admin', 'platform_viewer'] },
      { id: 'celery-observability', label: 'Celery / Tasks', path: '/admin/celery', icon: Activity, requiredPlatformRole: ['platform_admin', 'platform_viewer'] },
    ],
  },
];
