import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Bell } from 'lucide-react';
import { getNotificationEventSummary } from '../services/alertsService';

interface NotificationBellProps {
  workspaceId: string | null;
}

/**
 * Top-bar bell showing count of pending + retrying notification events
 * for the current workspace. Polls every 30s. Links to the alerts page.
 */
export default function NotificationBell({ workspaceId }: NotificationBellProps) {
  const { data } = useQuery({
    queryKey: ['notification-event-summary', workspaceId],
    queryFn: () => getNotificationEventSummary(workspaceId!),
    enabled: !!workspaceId,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    staleTime: 15_000,
    retry: 1,
  });

  const pending = (data?.pending ?? 0) + (data?.retrying ?? 0);
  const failed = data?.failed ?? 0;
  const showBadge = pending > 0 || failed > 0;
  const badgeCount = pending > 0 ? pending : failed;
  const badgeColor = pending > 0 ? 'bg-blue-500' : 'bg-red-500';

  if (!workspaceId) {
    return (
      <div className="relative inline-flex h-9 w-9 items-center justify-center rounded text-gray-500" aria-hidden>
        <Bell className="h-5 w-5" />
      </div>
    );
  }

  return (
    <Link
      to={`/hub/ws/${workspaceId}/alerts`}
      title={
        showBadge
          ? `${pending} pending · ${failed} failed notifications`
          : 'No pending notifications'
      }
      aria-label="Notifications"
      data-testid="notification-bell"
      className="relative inline-flex h-9 w-9 items-center justify-center rounded text-gray-400 hover:bg-gray-700 hover:text-white transition-colors"
    >
      <Bell className="h-5 w-5" />
      {showBadge && (
        <span
          className={`absolute -top-0.5 -right-0.5 inline-flex min-w-[1.1rem] items-center justify-center rounded-full px-1 text-[10px] font-semibold text-white ${badgeColor}`}
        >
          {badgeCount > 99 ? '99+' : badgeCount}
        </span>
      )}
    </Link>
  );
}
