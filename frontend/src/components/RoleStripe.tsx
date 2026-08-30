/**
 * RoleStripe — thin colored bar at the very top of the screen, themed by role.
 * Acts as a constant visual reminder of which role is currently connected.
 */
import React from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useWorkspacePermissions } from '../hooks/useWorkspacePermissions';
import { getActorId } from '../utils/jwt';
import { getEffectiveRole, getRoleTheme } from '../utils/roleTheme';

interface RoleStripeProps {
  workspaceId?: string;
}

const RoleStripe: React.FC<RoleStripeProps> = ({ workspaceId }) => {
  const { user } = useAuth();
  const platformRole = user?.platform_role ?? null;
  const actorId = getActorId(localStorage.getItem('access_token')) ?? undefined;
  const isPlatformOp =
    platformRole === 'platform_admin' || platformRole === 'platform_viewer';
  // Fallback to persisted selected workspace so the stripe colors reflect the
  // user's role outside the DQHub shell (landing page, etc.).
  const effectiveWorkspaceId =
    workspaceId ?? localStorage.getItem('selected_workspace_id') ?? undefined;
  const { roleName: wsRoleName } = useWorkspacePermissions(
    isPlatformOp ? undefined : effectiveWorkspaceId,
    isPlatformOp ? undefined : actorId,
  );

  const role = getEffectiveRole(platformRole, wsRoleName);
  const theme = getRoleTheme(role);

  return (
    <div
      className={`h-1 w-full ${theme.stripeBg}`}
      data-testid="role-stripe"
      data-role={role}
    />
  );
};

export default RoleStripe;
