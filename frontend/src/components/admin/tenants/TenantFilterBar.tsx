/**
 * TenantFilterBar — status, region, plan dropdowns and a debounced search
 * input.  All values are controlled from the parent via props (URL state).
 */
import { useEffect, useRef, useState } from 'react';
import { Search } from 'lucide-react';

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'draft', label: 'Draft' },
  { value: 'active', label: 'Active' },
  { value: 'suspended', label: 'Suspended' },
  { value: 'archived', label: 'Archived' },
];

const REGION_OPTIONS = [
  { value: '', label: 'All regions' },
  { value: 'eu-west', label: 'EU West' },
  { value: 'eu-central', label: 'EU Central' },
  { value: 'us-east', label: 'US East' },
  { value: 'us-west', label: 'US West' },
];

const PLAN_OPTIONS = [
  { value: '', label: 'All plans' },
  { value: 'starter', label: 'Starter' },
  { value: 'growth', label: 'Growth' },
  { value: 'enterprise', label: 'Enterprise' },
];

interface TenantFilterBarProps {
  status: string;
  region: string;
  plan: string;
  q: string;
  onStatusChange: (value: string) => void;
  onRegionChange: (value: string) => void;
  onPlanChange: (value: string) => void;
  onSearchChange: (value: string) => void;
}

const DEBOUNCE_MS = 350;

export default function TenantFilterBar({
  status,
  region,
  plan,
  q,
  onStatusChange,
  onRegionChange,
  onPlanChange,
  onSearchChange,
}: TenantFilterBarProps) {
  const [localSearch, setLocalSearch] = useState(q);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keep local value in sync when URL changes externally (e.g. browser back)
  useEffect(() => {
    setLocalSearch(q);
  }, [q]);

  const handleSearchInput = (value: string) => {
    setLocalSearch(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      onSearchChange(value);
    }, DEBOUNCE_MS);
  };

  return (
    <div
      className="flex flex-wrap gap-3 items-center"
      role="search"
      aria-label="Filter tenants"
    >
      {/* Search */}
      <div className="relative flex-1 min-w-48">
        <Search
          className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none"
          aria-hidden="true"
        />
        <input
          type="search"
          aria-label="Search by name or slug"
          placeholder="Search name or slug…"
          value={localSearch}
          onChange={(e) => handleSearchInput(e.target.value)}
          className="w-full pl-9 pr-4 py-2 rounded-lg bg-dark-800 border border-dark-700 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500"
          data-testid="filter-search"
        />
      </div>

      {/* Status filter */}
      <select
        aria-label="Filter by status"
        value={status}
        onChange={(e) => onStatusChange(e.target.value)}
        className="px-3 py-2 rounded-lg bg-dark-800 border border-dark-700 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500"
        data-testid="filter-status"
      >
        {STATUS_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      {/* Region filter */}
      <select
        aria-label="Filter by region"
        value={region}
        onChange={(e) => onRegionChange(e.target.value)}
        className="px-3 py-2 rounded-lg bg-dark-800 border border-dark-700 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500"
        data-testid="filter-region"
      >
        {REGION_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      {/* Plan filter */}
      <select
        aria-label="Filter by plan"
        value={plan}
        onChange={(e) => onPlanChange(e.target.value)}
        className="px-3 py-2 rounded-lg bg-dark-800 border border-dark-700 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500"
        data-testid="filter-plan"
      >
        {PLAN_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
