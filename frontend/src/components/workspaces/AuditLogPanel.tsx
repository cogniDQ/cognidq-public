/**
 * AuditLogPanel — links to the workspace's audit log (MVP: link only).
 */
import { FileText } from 'lucide-react';

interface AuditLogPanelProps {
  workspaceId: string;
}

export default function AuditLogPanel({ workspaceId }: AuditLogPanelProps) {
  return (
    <div
      className="rounded-2xl border border-dark-800/60 bg-dark-900/60 p-4 backdrop-blur-sm"
      data-testid="audit-log-panel"
    >
      <div className="flex items-center gap-2 mb-1">
        <FileText className="w-4 h-4 text-gray-400" aria-hidden="true" />
        <span className="text-sm font-medium text-gray-300">Audit Log</span>
      </div>
      <p className="text-xs text-gray-500">
        View all changes made to this workspace.{' '}
        <a
          href={`/workspaces/${workspaceId}/audit`}
          className="text-brand-400 hover:text-brand-300 underline"
          data-testid="audit-log-link"
        >
          View audit log
        </a>
      </p>
    </div>
  );
}
