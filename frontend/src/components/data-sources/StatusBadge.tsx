import type { DataSourceStatus } from '../../types/dataSource';

interface Props {
  status: DataSourceStatus;
}

const STATUS_STYLES: Record<DataSourceStatus, string> = {
  active: 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30',
  archived: 'bg-gray-500/20 text-gray-400 border border-gray-500/30',
};

export default function StatusBadge({ status }: Props) {
  return (
    <span
      data-testid="data-source-status-badge"
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium uppercase tracking-wide ${STATUS_STYLES[status]}`}
    >
      {status}
    </span>
  );
}
