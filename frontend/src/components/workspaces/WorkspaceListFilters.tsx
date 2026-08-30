/**
 * WorkspaceListFilters — filter controls for the Workspace List page.
 *
 * Controls:
 *   - `include_archived` toggle: shows archived workspaces when active
 *   - `q` search input with debounce (350 ms)
 *   - `sort_by` selector: created_at | updated_at
 *   - `sort_dir` selector: asc | desc
 *
 * All values are controlled from the parent via URL-state props.
 */
import { useEffect, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { SortBy, SortDir } from '../../services/workspace';

const SORT_BY_OPTIONS: { value: SortBy; label: string }[] = [
  { value: 'created_at', label: 'Created date' },
  { value: 'updated_at', label: 'Updated date' },
];

const SORT_DIR_OPTIONS: { value: SortDir; label: string }[] = [
  { value: 'desc', label: 'Newest first' },
  { value: 'asc', label: 'Oldest first' },
];

const DEBOUNCE_MS = 350;

interface WorkspaceListFiltersProps {
  q: string;
  includeArchived: boolean;
  sortBy: SortBy;
  sortDir: SortDir;
  onSearchChange: (value: string) => void;
  onIncludeArchivedChange: (value: boolean) => void;
  onSortByChange: (value: SortBy) => void;
  onSortDirChange: (value: SortDir) => void;
}

export default function WorkspaceListFilters({
  q,
  includeArchived,
  sortBy,
  sortDir,
  onSearchChange,
  onIncludeArchivedChange,
  onSortByChange,
  onSortDirChange,
}: WorkspaceListFiltersProps) {
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
      aria-label="Filter workspaces"
      data-testid="workspace-filters"
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

      {/* Sort by */}
      <select
        aria-label="Sort by"
        value={sortBy}
        onChange={(e) => onSortByChange(e.target.value as SortBy)}
        className="px-3 py-2 rounded-lg bg-dark-800 border border-dark-700 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500"
        data-testid="filter-sort-by"
      >
        {SORT_BY_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      {/* Sort direction */}
      <select
        aria-label="Sort direction"
        value={sortDir}
        onChange={(e) => onSortDirChange(e.target.value as SortDir)}
        className="px-3 py-2 rounded-lg bg-dark-800 border border-dark-700 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500"
        data-testid="filter-sort-dir"
      >
        {SORT_DIR_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      {/* Include archived toggle */}
      <label
        className="inline-flex items-center gap-2 cursor-pointer select-none text-sm text-gray-300"
        data-testid="filter-include-archived-label"
      >
        <button
          role="switch"
          aria-checked={includeArchived}
          aria-label="Include archived workspaces"
          onClick={() => onIncludeArchivedChange(!includeArchived)}
          className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500/50 ${
            includeArchived ? 'bg-primary-600' : 'bg-dark-700'
          }`}
          data-testid="filter-include-archived"
        >
          <span
            className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
              includeArchived ? 'translate-x-4' : 'translate-x-0.5'
            }`}
          />
        </button>
        Include archived
      </label>
    </div>
  );
}
