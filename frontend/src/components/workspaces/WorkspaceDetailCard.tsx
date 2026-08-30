/**
 * WorkspaceDetailCard — renders all workspace metadata on the detail page.
 *
 * dataset_count and member_count are optional (may be null if the count
 * queries timed out or the linked registry is unavailable).  When null,
 * "N/A" is shown with a tooltip explaining the value is unavailable.
 *
 * status_reason is only shown when the workspace is archived.
 */
import WorkspaceStatusBadge from './WorkspaceStatusBadge';
import { WorkspaceDetailWithCounts } from '../../services/workspace';

interface FieldProps {
  label: string;
  value: React.ReactNode;
  testId?: string;
  span2?: boolean;
}

function Field({ label, value, testId, span2 }: FieldProps) {
  return (
    <div className={span2 ? 'sm:col-span-2' : undefined}>
      <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">{label}</dt>
      <dd className="mt-1 text-sm text-gray-200 break-all" data-testid={testId}>
        {value}
      </dd>
    </div>
  );
}

function CountCell({ value, label }: { value: number | null; label: string }) {
  if (value === null) {
    return (
      <span
        title={`${label} count is temporarily unavailable`}
        className="text-gray-500 cursor-help"
      >
        N/A
      </span>
    );
  }
  return <span>{value}</span>;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

interface WorkspaceDetailCardProps {
  workspace: WorkspaceDetailWithCounts;
}

export default function WorkspaceDetailCard({ workspace }: WorkspaceDetailCardProps) {
  return (
    <div
      className="rounded-2xl border border-dark-800/60 bg-dark-900/60 p-6 backdrop-blur-sm"
      data-testid="workspace-detail-card"
    >
      {/* Header row: name + status badge */}
      <div className="mb-5 flex items-center justify-between gap-3">
        <h2
          className="text-lg font-semibold text-white truncate"
          data-testid="workspace-detail-name"
        >
          {workspace.workspace_name}
        </h2>
        <WorkspaceStatusBadge status={workspace.status} />
      </div>

      <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field
          label="Workspace ID"
          value={<span className="font-mono text-xs">{workspace.workspace_id}</span>}
          testId="workspace-detail-id"
        />
        <Field
          label="Slug"
          value={<span className="font-mono">{workspace.workspace_slug}</span>}
          testId="workspace-detail-slug"
        />
        <Field
          label="Tenant ID"
          value={<span className="font-mono text-xs">{workspace.tenant_id}</span>}
          testId="workspace-detail-tenant-id"
        />
        <Field label="Timezone" value={workspace.default_timezone} />

        {workspace.description && (
          <Field label="Description" value={workspace.description} span2 />
        )}

        {workspace.status === 'archived' && workspace.status_reason && (
          <Field
            label="Archive Reason"
            value={workspace.status_reason}
            testId="workspace-detail-status-reason"
            span2
          />
        )}

        <Field
          label="Datasets"
          value={<CountCell value={workspace.dataset_count} label="Dataset" />}
        />
        <Field
          label="Members"
          value={<CountCell value={workspace.member_count} label="Member" />}
        />

        <Field label="Created" value={formatDate(workspace.created_at)} />
        <Field label="Updated" value={formatDate(workspace.updated_at)} />
      </dl>
    </div>
  );
}
