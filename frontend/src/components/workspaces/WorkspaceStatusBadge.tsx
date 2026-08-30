/**
 * WorkspaceStatusBadge — renders a workspace status with a text label and a
 * colored dot.
 *
 * Accessibility constraint (P10 spec): status must NOT be communicated by
 * color alone — a text label is always present alongside the visual indicator.
 */
import { WorkspaceStatus } from '../../services/workspace';

const STATUS_CONFIG: Record<
  WorkspaceStatus,
  { label: string; dot: string; bg: string; text: string }
> = {
  active: {
    label: 'Active',
    dot: 'bg-emerald-400',
    bg: 'bg-emerald-500/10',
    text: 'text-emerald-400',
  },
  archived: {
    label: 'Archived',
    dot: 'bg-red-400',
    bg: 'bg-red-500/10',
    text: 'text-red-400',
  },
};

interface WorkspaceStatusBadgeProps {
  status: WorkspaceStatus;
}

export default function WorkspaceStatusBadge({ status }: WorkspaceStatusBadgeProps) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.active;
  return (
    <span
      role="status"
      aria-label={`Status: ${config.label}`}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${config.bg} ${config.text}`}
      data-testid={`workspace-status-badge-${status}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${config.dot}`}
        aria-hidden="true"
      />
      {config.label}
    </span>
  );
}
