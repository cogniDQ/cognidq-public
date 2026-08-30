/**
 * F008 — Permission Audit Visibility
 * PermissionAuditTable — data table for permission audit entries.
 *
 * Features:
 *   - 5 columns: Occurred At (sortable), Action Type, Actor, Target, Actor Role.
 *   - System-actor badge rendered in Actor cell when actor_type === 'system'.
 *   - Loading skeleton (shimmer rows) while data is in flight.
 *   - Empty-state message when items array is empty and not loading.
 *   - Sortable "Occurred At" header: clicking fires onSortToggle().
 */

import { ChevronDown, ChevronUp } from 'lucide-react';
import type { PermissionAuditEntry } from '../../types/audit';

interface Props {
  items: PermissionAuditEntry[];
  sortDir: 'asc' | 'desc';
  onSortToggle: () => void;
  isLoading: boolean;
}

export default function PermissionAuditTable({
  items,
  sortDir,
  onSortToggle,
  isLoading,
}: Props) {
  if (isLoading) {
    return (
      <div className="animate-pulse space-y-2" data-testid="audit-table-loading">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-10 rounded-lg bg-dark-800" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div
        className="rounded-xl border border-dark-700 bg-dark-900/60 py-14 text-center text-sm text-gray-400"
        data-testid="audit-table-empty"
      >
        No access-change events found for the selected filters.
      </div>
    );
  }

  const SortIcon = sortDir === 'desc' ? ChevronDown : ChevronUp;

  return (
    <div className="overflow-x-auto rounded-xl border border-dark-700" data-testid="audit-table">
      <table className="w-full text-sm">
        <thead className="bg-dark-800/80">
          <tr>
            <th
              className="cursor-pointer select-none px-4 py-3 text-left text-xs font-medium text-gray-400 hover:text-white transition-colors"
              onClick={onSortToggle}
              data-testid="occurred-at-sort-btn"
            >
              <span className="flex items-center gap-1">
                Occurred At
                <SortIcon className="w-3 h-3" aria-hidden="true" />
              </span>
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">
              Action Type
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">
              Actor
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">
              Target
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">
              Actor Role
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-dark-700">
          {items.map((entry) => (
            <tr
              key={entry.log_id}
              className="bg-dark-900/40 hover:bg-dark-800/60 transition-colors"
              data-testid="audit-table-row"
            >
              <td className="px-4 py-2.5 text-gray-300 whitespace-nowrap">
                {new Date(entry.occurred_at).toLocaleString()}
              </td>
              <td className="px-4 py-2.5 text-gray-300">
                {entry.action_type.replace(/_/g, ' ')}
              </td>
              <td className="px-4 py-2.5 text-gray-300">
                {entry.actor_type === 'system' ? (
                  <span
                    className="inline-block rounded-full bg-slate-700 px-2 py-0.5 text-xs font-medium text-slate-300"
                    data-testid="system-actor-badge"
                  >
                    System
                  </span>
                ) : (
                  <span>{entry.actor_display_name ?? entry.actor_id ?? '—'}</span>
                )}
              </td>
              <td className="px-4 py-2.5 text-gray-300">
                {entry.target_display_name ?? entry.target_entity_id ?? '—'}
              </td>
              <td className="px-4 py-2.5 text-xs text-gray-400">
                {entry.actor_role}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
