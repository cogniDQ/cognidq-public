import type { LastTestStatus } from '../../types/dataSource';

interface Props {
  status: LastTestStatus;
}

const STATUS_STYLES: Record<LastTestStatus, string> = {
  untested: 'bg-gray-500/20 text-gray-400 border border-gray-500/30',
  reachable: 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30',
  unreachable: 'bg-red-500/20 text-red-400 border border-red-500/30',
  test_failed: 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/30',
};

const STATUS_LABELS: Record<LastTestStatus, string> = {
  untested: 'UNTESTED',
  reachable: 'REACHABLE',
  unreachable: 'UNREACHABLE',
  test_failed: 'TEST FAILED',
};

export default function TestStatusBadge({ status }: Props) {
  return (
    <span
      data-testid="test-status-badge"
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium uppercase tracking-wide ${STATUS_STYLES[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}
