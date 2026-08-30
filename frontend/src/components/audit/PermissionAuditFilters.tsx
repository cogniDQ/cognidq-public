/**
 * F008 — Permission Audit Visibility
 * PermissionAuditFilters — filter bar for the Permission Audit page.
 *
 * Controlled component: the parent (PermissionAuditPage) owns filter state via
 * URL search params.  This component receives `filters` + an `onFiltersChange`
 * callback and renders inputs for every supported filter field.
 *
 * Behaviour:
 *   - Actor ID text input is debounced (300 ms) to avoid API calls on every stroke.
 *   - Action Type dropdown fires onFiltersChange immediately on change.
 *   - Date inputs fire immediately on change.
 *   - "Clear Filters" fires onFiltersChange({}) which causes the parent to
 *     replace all URL params (resetting to the default view).
 */

import { useEffect, useRef, useState } from 'react';
import type { AuditFilters } from '../../services/permissionAuditService';

const ACCESS_CONTROL_ACTION_TYPES: string[] = [
  'role_assigned',
  'role_revoked',
  'team_created',
  'team_deleted',
  'team_member_added',
  'team_member_removed',
  'team_member_updated',
  'team_updated',
  'user_password_changed',
  'user_profile_updated',
];

interface Props {
  filters: AuditFilters;
  onFiltersChange: (filters: AuditFilters) => void;
}

export default function PermissionAuditFilters({ filters, onFiltersChange }: Props) {
  const [actorInput, setActorInput] = useState(filters.actor_id ?? '');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync local actor input when the parent clears filters externally.
  useEffect(() => {
    setActorInput(filters.actor_id ?? '');
  }, [filters.actor_id]);

  const handleActorChange = (value: string) => {
    setActorInput(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      onFiltersChange({ ...filters, actor_id: value || undefined });
    }, 300);
  };

  const handleField = (key: keyof AuditFilters, value: string) => {
    onFiltersChange({ ...filters, [key]: value || undefined });
  };

  const handleClear = () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setActorInput('');
    onFiltersChange({});
  };

  return (
    <div
      className="flex flex-wrap gap-3 items-end rounded-xl border border-dark-700 bg-dark-900/60 p-4"
      data-testid="permission-audit-filters"
    >
      {/* Actor ID */}
      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-400" htmlFor="actor-id-input">
          Actor ID
        </label>
        <input
          id="actor-id-input"
          type="text"
          value={actorInput}
          onChange={(e) => handleActorChange(e.target.value)}
          placeholder="Filter by actor UUID"
          data-testid="actor-id-input"
          className="w-64 rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
      </div>

      {/* Action Type */}
      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-400" htmlFor="action-type-select">
          Action Type
        </label>
        <select
          id="action-type-select"
          value={filters.action_type ?? ''}
          onChange={(e) => handleField('action_type', e.target.value)}
          data-testid="action-type-select"
          className="rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">All action types</option>
          {ACCESS_CONTROL_ACTION_TYPES.map((t) => (
            <option key={t} value={t}>
              {t.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
      </div>

      {/* Target Entity ID */}
      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-400" htmlFor="target-entity-id-input">
          Target Entity ID
        </label>
        <input
          id="target-entity-id-input"
          type="text"
          value={filters.target_entity_id ?? ''}
          onChange={(e) => handleField('target_entity_id', e.target.value)}
          placeholder="Filter by target UUID"
          data-testid="target-entity-id-input"
          className="w-64 rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
      </div>

      {/* From date */}
      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-400" htmlFor="from-date-input">
          From
        </label>
        <input
          id="from-date-input"
          type="datetime-local"
          value={filters.from_date ?? ''}
          onChange={(e) => handleField('from_date', e.target.value)}
          data-testid="from-date-input"
          className="rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
      </div>

      {/* To date */}
      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-400" htmlFor="to-date-input">
          To
        </label>
        <input
          id="to-date-input"
          type="datetime-local"
          value={filters.to_date ?? ''}
          onChange={(e) => handleField('to_date', e.target.value)}
          data-testid="to-date-input"
          className="rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
      </div>

      {/* Clear */}
      <button
        type="button"
        onClick={handleClear}
        data-testid="clear-filters-btn"
        className="rounded-lg border border-dark-600 px-3 py-1.5 text-sm text-gray-400 hover:text-white transition-colors"
      >
        Clear Filters
      </button>
    </div>
  );
}
