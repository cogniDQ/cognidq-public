/**
 * StatusBadge — displays a tenant status with a text label and a colored dot.
 *
 * TDD §5.6 accessibility requirement: status must NOT be communicated by color
 * alone — a text label is always present alongside the visual indicator.
 * Uses role="status" so screen readers announce changes.
 */
import { TenantStatus } from '../../../services/tenant';

const STATUS_CONFIG: Record<
  TenantStatus,
  { label: string; dot: string; bg: string; text: string }
> = {
  draft: {
    label: 'Draft',
    dot: 'bg-gray-400',
    bg: 'bg-gray-500/10',
    text: 'text-gray-400',
  },
  active: {
    label: 'Active',
    dot: 'bg-emerald-400',
    bg: 'bg-emerald-500/10',
    text: 'text-emerald-400',
  },
  suspended: {
    label: 'Suspended',
    dot: 'bg-amber-400',
    bg: 'bg-amber-500/10',
    text: 'text-amber-400',
  },
  archived: {
    label: 'Archived',
    dot: 'bg-red-400',
    bg: 'bg-red-500/10',
    text: 'text-red-400',
  },
};

interface StatusBadgeProps {
  status: TenantStatus;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.draft;
  return (
    <span
      role="status"
      aria-label={`Status: ${config.label}`}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${config.bg} ${config.text}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${config.dot}`}
        aria-hidden="true"
      />
      {config.label}
    </span>
  );
}
