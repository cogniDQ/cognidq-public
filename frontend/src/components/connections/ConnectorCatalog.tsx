/**
 * F-CONN-UX — Connector Catalog grid
 *
 * Renders the available connectors grouped by customer-facing buckets
 * (Start fast / Database / Warehouse / Lakehouse) with status &
 * capability badges and a click handler. Driven entirely by the
 * `/api/v1/connectors` registry payload — no per-connector branches.
 *
 * Spec §3, §5, §6, §11 — internal labels (P0/P1, raw status, Local /
 * Cloud chips, "local-testable only" filter) are hidden by default and
 * only re-surfaced when `adminMode` is set.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Cloud,
  Database,
  FileText,
  HardDrive,
  Layers,
  Server,
  Warehouse,
} from 'lucide-react';
import {
  CUSTOMER_STATUS_BADGE_CLASS,
  CUSTOMER_STATUS_LABEL,
  CustomerGroup,
  CUSTOMER_GROUP_LABEL,
  CUSTOMER_GROUP_DESCRIPTION,
  ConnectorCategory,
  ConnectorSpec,
  STATUS_LABELS,
  STATUS_BADGE_CLASS,
  customerCapabilitiesFor,
  customerGroupFor,
  customerStatusFor,
  groupConnectorsForCustomers,
  isConnectorLocalOnly,
  listConnectors,
} from '../../services/connectorCatalogService';

interface ConnectorCatalogProps {
  onSelect: (spec: ConnectorSpec) => void;
  selectedType?: string;
  /** When true, deferred connectors are shown but not selectable. Default true. */
  showDeferred?: boolean;
  /**
   * Surface engineering metadata (P0/P1, raw status, Local/Cloud chips,
   * the local-only filter). Defaults to false so customer-facing surfaces
   * stay clean — admin/dev mode can opt in.
   */
  adminMode?: boolean;
  /** Pre-filter to a single customer group (driven by RecommendedPaths). */
  groupFilter?: CustomerGroup | null;
  /**
   * Notify the parent of which customer groups are present in the
   * registry payload so the recommended-paths strip can render only
   * cards that actually map to data.
   */
  onGroupsAvailable?: (groups: CustomerGroup[]) => void;
}

// Customer-facing status filter values.
type StatusFilter = '' | 'available' | 'beta' | 'coming_soon';

function iconForCategory(category: ConnectorCategory) {
  switch (category) {
    case 'database':
      return Database;
    case 'warehouse':
      return Warehouse;
    case 'lakehouse':
      return Layers;
    case 'file':
      return FileText;
    case 'object_storage':
      return Cloud;
    case 'query_engine':
      return Server;
    default:
      return HardDrive;
  }
}

export default function ConnectorCatalog({
  onSelect,
  selectedType,
  showDeferred = true,
  adminMode = false,
  groupFilter = null,
  onGroupsAvailable,
}: ConnectorCatalogProps) {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('');
  const [localOnly, setLocalOnly] = useState(false);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['connectors', 'catalog'],
    queryFn: () => listConnectors(),
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    const term = search.trim().toLowerCase();
    return data.items.filter((spec) => {
      if (!showDeferred && spec.status === 'deferred') return false;
      if (statusFilter && customerStatusFor(spec) !== statusFilter) return false;
      if (adminMode && localOnly && !isConnectorLocalOnly(spec)) return false;
      if (
        term &&
        !spec.display_name.toLowerCase().includes(term) &&
        !spec.type.toLowerCase().includes(term) &&
        !spec.description.toLowerCase().includes(term)
      ) {
        return false;
      }
      return true;
    });
  }, [data, search, statusFilter, localOnly, showDeferred, adminMode]);

  const groups = useMemo(() => {
    const all = groupConnectorsForCustomers(filtered);
    if (!groupFilter) return all;
    return all.filter((g) => g.group === groupFilter);
  }, [filtered, groupFilter]);

  // Inform parent of *all* groups present in the registry (independent
  // of local filters) so the recommended-paths strip shows stable choices.
  const availableGroups = useMemo<CustomerGroup[]>(() => {
    if (!data) return [];
    const set = new Set<CustomerGroup>();
    for (const item of data.items) {
      if (!showDeferred && item.status === 'deferred') continue;
      set.add(customerGroupFor(item));
    }
    return Array.from(set);
  }, [data, showDeferred]);

  const lastNotifiedKey = useRef<string>('');
  useEffect(() => {
    if (!onGroupsAvailable) return;
    const key = availableGroups.join(',');
    if (key === lastNotifiedKey.current) return;
    lastNotifiedKey.current = key;
    onGroupsAvailable(availableGroups);
  }, [availableGroups, onGroupsAvailable]);

  if (isLoading) {
    return (
      <div data-testid="catalog-loading" className="p-6 flex items-center gap-2 text-gray-400 text-sm">
        <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/></svg>
        Loading connector catalog…
      </div>
    );
  }
  if (isError) {
    return (
      <div data-testid="catalog-error" className="p-4 m-4 rounded-lg bg-red-900/20 border border-red-800 text-red-400 text-sm">
        Failed to load catalog: {(error as Error)?.message ?? 'unknown error'}
      </div>
    );
  }

  return (
    <div data-testid="connector-catalog" data-admin-mode={adminMode}>
      <div className="flex flex-wrap items-center gap-2 p-4 border-b border-dark-700">
        <input
          type="search"
          placeholder="Search connectors…"
          aria-label="Search connectors"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input flex-1 min-w-[200px]"
          data-testid="catalog-search"
        />
        <select
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(e) =>
            setStatusFilter((e.target.value || '') as StatusFilter)
          }
          className="input w-auto"
          data-testid="catalog-status-filter"
        >
          <option value="">All statuses</option>
          <option value="available">Available</option>
          <option value="beta">Beta</option>
          <option value="coming_soon">Coming soon</option>
        </select>
        {adminMode && (
          <label className="flex items-center gap-1.5 text-sm text-gray-400">
            <input
              type="checkbox"
              checked={localOnly}
              onChange={(e) => setLocalOnly(e.target.checked)}
              className="h-4 w-4 rounded border-dark-600 bg-dark-800 text-primary-600 focus:ring-primary-500"
              data-testid="catalog-local-only"
            />
            Local-testable only
          </label>
        )}
      </div>

      {groupFilter && (
        <div
          data-testid="catalog-group-banner"
          className="px-4 pt-3 text-xs flex flex-wrap items-center gap-2"
        >
          <span className="font-semibold text-gray-200">
            {CUSTOMER_GROUP_LABEL[groupFilter]}
          </span>
          <span className="text-gray-400">
            {CUSTOMER_GROUP_DESCRIPTION[groupFilter]}
          </span>
        </div>
      )}

      {groups.length === 0 ? (
        <div data-testid="catalog-empty" className="p-6 text-sm text-gray-400">
          <p className="font-medium text-gray-300 mb-1">No connectors found</p>
          <p>Try changing your filters or search term.</p>
        </div>
      ) : (
        <div className="p-4 space-y-6">
          {groups.map((group) => (
            <section
              key={group.group}
              data-testid={`catalog-group-${group.group}`}
            >
              <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-3">
                {group.label}
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {group.items.map((spec) => (
                  <ConnectorCard
                    key={spec.type}
                    spec={spec}
                    selected={spec.type === selectedType}
                    onSelect={onSelect}
                    adminMode={adminMode}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

interface ConnectorCardProps {
  spec: ConnectorSpec;
  selected: boolean;
  onSelect: (spec: ConnectorSpec) => void;
  adminMode: boolean;
}

function ConnectorCard({
  spec,
  selected,
  onSelect,
  adminMode,
}: ConnectorCardProps) {
  const customerStatus = customerStatusFor(spec);
  const disabled = customerStatus === 'coming_soon';
  const Icon = iconForCategory(spec.category);
  const capabilities = customerCapabilitiesFor(spec);

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onSelect(spec)}
      data-testid={`connector-card-${spec.type}`}
      data-status={spec.status}
      data-customer-status={customerStatus}
      className={[
        'text-left p-4 rounded-lg border transition-all flex flex-col gap-2',
        selected
          ? 'border-primary-500 ring-2 ring-primary-500/20 bg-dark-800'
          : 'border-dark-700 bg-dark-800',
        disabled
          ? 'opacity-60 cursor-not-allowed'
          : 'hover:border-dark-600 hover:bg-dark-700 cursor-pointer',
      ].join(' ')}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className="inline-flex items-center justify-center w-8 h-8 rounded bg-dark-700 text-gray-400 flex-shrink-0"
          >
            <Icon size={16} />
          </span>
          <div className="font-medium text-gray-100">{spec.display_name}</div>
        </div>
        <span
          data-testid={`connector-card-status-${spec.type}`}
          className={`text-[10px] uppercase tracking-wide border px-1.5 py-0.5 rounded flex-shrink-0 ${CUSTOMER_STATUS_BADGE_CLASS[customerStatus]}`}
        >
          {CUSTOMER_STATUS_LABEL[customerStatus]}
        </span>
      </div>
      <p className="text-xs text-gray-400 line-clamp-2">{spec.description}</p>
      {capabilities.length > 0 && (
        <ul
          className="flex flex-wrap items-center gap-1 text-[10px] text-gray-400"
          data-testid={`connector-card-capabilities-${spec.type}`}
        >
          {capabilities.slice(0, 3).map((cap) => (
            <li
              key={cap.key}
              className="px-1.5 py-0.5 bg-dark-700 rounded border border-dark-600"
            >
              {cap.label}
            </li>
          ))}
        </ul>
      )}
      {disabled && spec.deferred_reason && (
        <p className="text-[10px] text-gray-500 italic">
          {spec.deferred_reason}
        </p>
      )}
      {adminMode && (
        <p
          className="text-[10px] text-gray-400 mt-1"
          data-testid={`connector-card-admin-${spec.type}`}
        >
          {spec.priority} ·{' '}
          <span className={STATUS_BADGE_CLASS[spec.status]}>
            {STATUS_LABELS[spec.status]}
          </span>
          {isConnectorLocalOnly(spec) ? ' · Local' : ''}
          {spec.capabilities.requires_external_credentials ? ' · Cloud' : ''}
        </p>
      )}
    </button>
  );
}
