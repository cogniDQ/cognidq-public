/**
 * SupportSessionBanner — shown in the Hub shell when a platform_admin is
 * viewing a tenant/workspace under an active tenant-admin-issued support
 * access grant. Revoking belongs to the tenant admin who granted it; "End
 * session" here just navigates back to the management console.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';
import { useActiveSupportGrant } from '../hooks/useActiveSupportGrant';

function formatRemaining(expiresAt: string): string {
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms <= 0) return 'expired';
  const totalMinutes = Math.floor(ms / 60000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}

interface Props {
  isPlatformOp: boolean;
  tenantId: string | null | undefined;
  workspaceId: string | null | undefined;
}

export default function SupportSessionBanner({ isPlatformOp, tenantId, workspaceId }: Props) {
  const navigate = useNavigate();
  const { matchingGrant } = useActiveSupportGrant(isPlatformOp, tenantId, workspaceId);
  const [, forceTick] = useState(0);

  useEffect(() => {
    if (!matchingGrant) return;
    const interval = setInterval(() => forceTick((n) => n + 1), 30_000);
    return () => clearInterval(interval);
  }, [matchingGrant]);

  if (!matchingGrant) return null;

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-warning/40 bg-warning-soft px-4 py-2 text-sm text-warning mb-4">
      <div className="flex items-center gap-2">
        <ShieldAlert className="h-4 w-4 flex-shrink-0" />
        <span>
          Support session for <strong>{matchingGrant.tenant_name ?? 'this tenant'}</strong>
          {matchingGrant.workspace_name ? <> / {matchingGrant.workspace_name}</> : null} — expires
          in {formatRemaining(matchingGrant.expires_at)}
        </span>
      </div>
      <button
        onClick={() => navigate('/admin')}
        className="flex-shrink-0 font-semibold hover:underline"
      >
        End session
      </button>
    </div>
  );
}
