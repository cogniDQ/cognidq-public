import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { getDataSourceAuditLogs } from '../../services/datasource';
import type { AuditLogEntry } from '../../types/dataSource';

interface Props {
  workspaceId: string;
  dataSourceId: string;
}

function formatAction(action: string) {
  return action.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(value: string | null | undefined): string {
  if (!value) return 'Unknown date';
  const d = new Date(value);
  return isNaN(d.getTime()) ? value : d.toLocaleString();
}

function AuditRow({ entry }: { entry: AuditLogEntry }) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-gray-700/50 last:border-0">
      <div className="flex-1 min-w-0">
        <p className="text-sm text-white font-medium">{formatAction(entry.action_type)}</p>
        <p className="text-xs text-gray-400 mt-0.5">
          {formatDate(entry.occurred_at)} — actor: {entry.actor_id ?? 'system'}
        </p>
      </div>
    </div>
  );
}

export default function AuditLogPanel({ workspaceId, dataSourceId }: Props) {
  const [open, setOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['data-source-audit', workspaceId, dataSourceId],
    queryFn: () => getDataSourceAuditLogs(workspaceId, dataSourceId),
    enabled: open,
    staleTime: 30_000,
  });

  return (
    <div className="rounded-2xl border border-gray-700 bg-gray-800/60">
      <button
        type="button"
        data-testid="audit-log-panel-toggle"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-4 text-left"
      >
        <span className="text-sm font-medium text-white">Audit Log</span>
        {open ? (
          <ChevronUp className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        )}
      </button>

      {open && (
        <div className="px-5 pb-4" data-testid="audit-log-list">
          {isLoading && (
            <p className="text-sm text-gray-400 py-2">Loading audit log…</p>
          )}
          {!isLoading && (!data?.items || data.items.length === 0) && (
            <p className="text-sm text-gray-400 py-2">No audit entries found.</p>
          )}
          {data?.items?.map((entry) => (
            <AuditRow key={entry.log_id} entry={entry} />
          ))}
        </div>
      )}
    </div>
  );
}
