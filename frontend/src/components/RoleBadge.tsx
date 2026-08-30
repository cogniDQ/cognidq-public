/**
 * RoleBadge — small pill that surfaces the operator's effective role.
 *
 * Uses the platform role first (from /auth/me), then falls back to the
 * current workspace role (from useWorkspacePermissions).
 *
 * Designed to be placed in the header of every authenticated layout so the
 * operator can immediately tell which role they are connected as.
 */
import React from 'react';
import { ShieldCheck } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useWorkspacePermissions } from '../hooks/useWorkspacePermissions';
import { getActorId } from '../utils/jwt';
import { getEffectiveRole, getRoleTheme } from '../utils/roleTheme';

interface RoleBadgeProps {
  /** Optional workspace id override; defaults to undefined (no workspace lookup). */
  workspaceId?: string;
  /** Compact (just label) vs verbose (label + icon). Defaults to verbose. */
  compact?: boolean;
}

const RoleBadge: React.FC<RoleBadgeProps> = ({ workspaceId, compact = false }) => {
  const { user } = useAuth();
  const platformRole = user?.platform_role ?? null;
  const actorId = getActorId(localStorage.getItem('access_token')) ?? undefined;

  // Skip workspace lookup for platform operators — they have no WS role.
  const isPlatformOp =
    platformRole === 'platform_admin' || platformRole === 'platform_viewer';
  // Fallback: if no workspaceId prop, use the persisted selection so the badge
  // shows the correct role on pages outside DQHub (e.g. landing page).
  const effectiveWorkspaceId =
    workspaceId ?? localStorage.getItem('selected_workspace_id') ?? undefined;
  const { roleName: wsRoleName } = useWorkspacePermissions(
    isPlatformOp ? undefined : effectiveWorkspaceId,
    isPlatformOp ? undefined : actorId,
  );

  const role = getEffectiveRole(platformRole, wsRoleName);
  const theme = getRoleTheme(role);

  return (
    <span
      title={theme.description}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium ${theme.badgeBg} ${theme.badgeText}`}
      data-testid="role-badge"
      data-role={role}
    >
      {!compact && <ShieldCheck className="w-3.5 h-3.5" />}
      <span>{theme.longLabel}</span>
    </span>
  );
};

export default RoleBadge;
