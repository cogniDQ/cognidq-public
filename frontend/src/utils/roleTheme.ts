/**
 * roleTheme — Visual identity per role.
 *
 * Each role has a distinctive color so the operator can immediately recognize
 * which role they are connected as. Used by the layout headers (top stripe +
 * RoleBadge) in both the platform admin shell and the DQ Hub shell.
 *
 * Tailwind classes are returned as strings (must be present in source so the
 * Tailwind JIT can pick them up — do not build them dynamically).
 */

export type AnyRole =
  | 'platform_admin'
  | 'platform_viewer'
  | 'tenant_admin'
  | 'workspace_administrator'
  | 'data_engineer'
  | 'data_steward'
  | 'business_analyst'
  | 'governance_viewer'
  | 'sandbox_admin'
  | 'unknown';

export interface RoleTheme {
  /** Short display label (3 chars max in compact mode). */
  label: string;
  /** Long human label. */
  longLabel: string;
  /** Tailwind background class for the badge. */
  badgeBg: string;
  /** Tailwind text color class for the badge. */
  badgeText: string;
  /** Tailwind background class for the thin top stripe. */
  stripeBg: string;
  /** Hex color (for non-Tailwind contexts e.g. inline style). */
  hex: string;
  /** Short tooltip / description. */
  description: string;
}

const THEMES: Record<AnyRole, RoleTheme> = {
  platform_admin: {
    label: 'Platform Admin',
    longLabel: 'Platform Administrator',
    badgeBg: 'bg-rose-600/20 border-rose-500',
    badgeText: 'text-rose-300',
    stripeBg: 'bg-rose-500',
    hex: '#f43f5e',
    description: 'Full platform control — tenants, provisioning, all workspaces.',
  },
  platform_viewer: {
    label: 'Platform Viewer',
    longLabel: 'Platform Viewer',
    badgeBg: 'bg-pink-600/20 border-pink-500',
    badgeText: 'text-pink-300',
    stripeBg: 'bg-pink-500',
    hex: '#ec4899',
    description: 'Read-only access across the platform.',
  },
  tenant_admin: {
    label: 'Tenant Admin',
    longLabel: 'Tenant Administrator',
    badgeBg: 'bg-teal-600/20 border-teal-500',
    badgeText: 'text-teal-300',
    stripeBg: 'bg-teal-500',
    hex: '#14b8a6',
    description: 'Owns a tenant — creates workspaces and assigns workspace roles to members.',
  },
  workspace_administrator: {
    label: 'Workspace Admin',
    longLabel: 'Workspace Administrator',
    badgeBg: 'bg-amber-600/20 border-amber-500',
    badgeText: 'text-amber-300',
    stripeBg: 'bg-amber-500',
    hex: '#f59e0b',
    description: 'Full control over a single workspace.',
  },
  data_engineer: {
    label: 'Data Engineer',
    longLabel: 'Data Engineer',
    badgeBg: 'bg-sky-600/20 border-sky-500',
    badgeText: 'text-sky-300',
    stripeBg: 'bg-sky-500',
    hex: '#0ea5e9',
    description: 'Builds connections, datasets, rules and runs flows.',
  },
  data_steward: {
    label: 'Data Steward',
    longLabel: 'Data Steward',
    badgeBg: 'bg-emerald-600/20 border-emerald-500',
    badgeText: 'text-emerald-300',
    stripeBg: 'bg-emerald-500',
    hex: '#10b981',
    description: 'Owns data quality rules and triages issues.',
  },
  business_analyst: {
    label: 'Business Analyst',
    longLabel: 'Business Analyst',
    badgeBg: 'bg-violet-600/20 border-violet-500',
    badgeText: 'text-violet-300',
    stripeBg: 'bg-violet-500',
    hex: '#8b5cf6',
    description: 'Read-only analytical access to datasets and reports.',
  },
  governance_viewer: {
    label: 'Governance Viewer',
    longLabel: 'Governance Viewer',
    badgeBg: 'bg-slate-600/30 border-slate-500',
    badgeText: 'text-slate-300',
    stripeBg: 'bg-slate-500',
    hex: '#64748b',
    description: 'Read-only audit/oversight role.',
  },
  sandbox_admin: {
    label: 'Sandbox Admin',
    longLabel: 'Sandbox Administrator',
    badgeBg: 'bg-fuchsia-600/20 border-fuchsia-500',
    badgeText: 'text-fuchsia-300',
    stripeBg: 'bg-fuchsia-500',
    hex: '#d946ef',
    description: 'Trial / sandbox tenant administrator.',
  },
  unknown: {
    label: 'No Role',
    longLabel: 'No Role Assigned',
    badgeBg: 'bg-gray-600/20 border-gray-500',
    badgeText: 'text-gray-300',
    stripeBg: 'bg-gray-600',
    hex: '#4b5563',
    description: 'Authenticated user without an assigned role.',
  },
};

/**
 * Resolve the effective role for theming:
 * platform role takes precedence over workspace role.
 */
export function getEffectiveRole(
  platformRole?: string | null,
  workspaceRole?: string | null,
): AnyRole {
  const r = (platformRole || workspaceRole || '').toLowerCase();
  if (r in THEMES) return r as AnyRole;
  return 'unknown';
}

export function getRoleTheme(role: AnyRole | string | null | undefined): RoleTheme {
  const key = (role || 'unknown') as AnyRole;
  return THEMES[key] ?? THEMES.unknown;
}
