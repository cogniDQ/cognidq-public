/**
 * TenantTable — sortable column headers + body rows, loading skeleton, and
 * inline error state.
 */
import { Tenant, SortBy, SortDir } from '../../../services/tenant';
import TenantTableRow from './TenantTableRow';
import { ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react';

interface TenantTableProps {
  tenants: Tenant[];
  isPlatformAdmin: boolean;
  isLoading: boolean;
  sortBy: SortBy;
  sortDir: SortDir;
  onSort: (field: SortBy) => void;
}

const SKELETON_ROWS = 6;

function SortIcon({
  field,
  active,
  dir,
}: {
  field: SortBy;
  active: SortBy;
  dir: SortDir;
}) {
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
        aria-sort={
          field === active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'
        }
        data-testid={`sort-${field}`}
      >
        {label}
        <SortIcon field={field} active={active} dir={dir} />
      </button>
    </th>
  );
}

export default function TenantTable({
  tenants,
  isPlatformAdmin,
  isLoading,
  sortBy,
  sortDir,
  onSort,
}: TenantTableProps) {
  return (
    <div className="overflow-x-auto rounded-xl border border-dark-800/60">
      <table className="w-full text-sm" aria-label="Tenant list">
        <thead className="bg-dark-800/50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
              Name / Slug
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
              Status
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
              Region
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
              Plan
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
            <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-400">
              Actions
            </th>
          </tr>
        </thead>

        <tbody>
          {isLoading
            ? Array.from({ length: SKELETON_ROWS }).map((_, i) => (
                <tr key={i} className="border-b border-dark-800/60">
                  {Array.from({ length: 7 }).map((_, j) => (
                    <td key={j} className="px-4 py-3">
                      <div className="h-4 bg-dark-700/60 rounded animate-pulse" />
                    </td>
                  ))}
                </tr>
              ))
            : tenants.map((tenant) => (
                <TenantTableRow
                  key={tenant.tenant_id}
                  tenant={tenant}
                  isPlatformAdmin={isPlatformAdmin}
                />
              ))}
        </tbody>
      </table>
    </div>
  );
}
