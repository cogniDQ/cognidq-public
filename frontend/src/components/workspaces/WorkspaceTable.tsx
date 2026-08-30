/**
 * WorkspaceTable — sortable column headers + body rows with loading skeleton.
 *
 * Columns: workspace_name / slug, status badge, default_timezone,
 * updated_at (sortable), created_at (sortable).
 */
import { WorkspaceSummary, SortBy, SortDir } from '../../services/workspace';
import WorkspaceTableRow from './WorkspaceTableRow';
import { ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react';

interface WorkspaceTableProps {
  workspaces: WorkspaceSummary[];
  isLoading: boolean;
  sortBy: SortBy;
  sortDir: SortDir;
  onSort: (field: SortBy) => void;
}

const SKELETON_ROWS = 5;

function SortIcon({ field, active, dir }: { field: SortBy; active: SortBy; dir: SortDir }) {
  if (field !== active) {
    return <ArrowUpDown className="w-3.5 h-3.5 text-gray-600" aria-hidden="true" />;
  }
  return dir === 'asc' ? (
    <ArrowUp className="w-3.5 h-3.5 text-primary-400" aria-hidden="true" />
  ) : (
    <ArrowDown className="w-3.5 h-3.5 text-primary-400" aria-hidden="true" />
  );
}

function SortableHeader({
  label,
  field,
  active,
  dir,
  onSort,
}: {
  label: string;
  field: SortBy;
  active: SortBy;
  dir: SortDir;
  onSort: (f: SortBy) => void;
}) {
  return (
    <th className="px-4 py-3 text-left">
      <button
        onClick={() => onSort(field)}
        className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400 hover:text-white transition-colors"
        aria-sort={field === active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
        data-testid={`sort-${field}`}
      >
        {label}
        <SortIcon field={field} active={active} dir={dir} />
      </button>
    </th>
  );
}

export default function WorkspaceTable({
  workspaces,
  isLoading,
  sortBy,
  sortDir,
  onSort,
}: WorkspaceTableProps) {
  return (
    <div
      className="overflow-x-auto rounded-xl border border-dark-800/60"
      data-testid="workspace-table"
    >
      <table className="w-full text-sm" aria-label="Workspace list">
        <thead className="bg-dark-800/50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
              Name / Slug
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
              Status
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
              Timezone
            </th>
            <SortableHeader
              label="Updated"
              field="updated_at"
              active={sortBy}
              dir={sortDir}
              onSort={onSort}
            />
            <SortableHeader
              label="Created"
              field="created_at"
              active={sortBy}
              dir={sortDir}
              onSort={onSort}
            />
          </tr>
        </thead>

        <tbody>
          {isLoading
            ? Array.from({ length: SKELETON_ROWS }).map((_, i) => (
                <tr key={i} className="border-b border-dark-800/60" aria-hidden="true">
                  {Array.from({ length: 5 }).map((_, j) => (
                    <td key={j} className="px-4 py-3">
                      <div className="h-4 bg-dark-700/60 rounded animate-pulse" />
                    </td>
                  ))}
                </tr>
              ))
            : workspaces.map((workspace) => (
                <WorkspaceTableRow
                  key={workspace.workspace_id}
                  workspace={workspace}
                />
              ))}
        </tbody>
      </table>
    </div>
  );
}
