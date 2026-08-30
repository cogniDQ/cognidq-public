/**
 * TenantListPage — main admin page for browsing and filtering tenants.
 *
 * URL state (via useSearchParams) drives all filters, sort, and pagination so
 * the current view is shareable and browser-history-aware.
 */
import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle } from 'lucide-react';

import { listTenants, SortBy, SortDir } from '../../../services/tenant';
import { getActorRole } from '../../../utils/jwt';
import TenantListHeader from '../../../components/admin/tenants/TenantListHeader';
import TenantFilterBar from '../../../components/admin/tenants/TenantFilterBar';
import TenantTable from '../../../components/admin/tenants/TenantTable';
import PaginationControl from '../../../components/admin/tenants/PaginationControl';
import EmptyState from '../../../components/admin/tenants/EmptyState';

const DEFAULT_PAGE_SIZE = 20;
const STALE_TIME = 30_000; // 30 s

function getSearchParam(params: URLSearchParams, key: string): string {
  return params.get(key) ?? '';
}

function getNumParam(params: URLSearchParams, key: string, fallback: number): number {
  const v = params.get(key);
  const n = v !== null ? parseInt(v, 10) : NaN;
  return isNaN(n) ? fallback : n;
}

export default function TenantListPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Read URL state ----------------------------------------------------------------
  const q = getSearchParam(searchParams, 'q');
  const status = getSearchParam(searchParams, 'status');
  const region = getSearchParam(searchParams, 'region');
  const plan = getSearchParam(searchParams, 'plan');
  const sortBy = (getSearchParam(searchParams, 'sort_by') || 'created_at') as SortBy;
  const sortDir = (getSearchParam(searchParams, 'sort_dir') || 'desc') as SortDir;
  const page = getNumParam(searchParams, 'page', 1);
  const pageSize = getNumParam(searchParams, 'page_size', DEFAULT_PAGE_SIZE);

  // Derive admin role from JWT.
  const isPlatformAdmin =
    getActorRole(localStorage.getItem('access_token')) === 'platform_admin';

  // Build query params (stripped of empty values inside listTenants) ----------
  const queryParams = {
    q: q || undefined,
    status: status || undefined,
    region: region || undefined,
    plan: plan || undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
    page,
    page_size: pageSize,
    include_archived: isPlatformAdmin ? true : undefined,
  };

  const { data, isLoading, isError } = useQuery({
    queryKey: ['tenants', queryParams],
    queryFn: () => listTenants(queryParams),
    staleTime: STALE_TIME,
  });

  // URL state helpers ------------------------------------------------------------
  const updateParams = useCallback(
    (updates: Record<string, string | undefined>, resetPage = false) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(updates)) {
          if (v === undefined || v === '') {
            next.delete(k);
          } else {
            next.set(k, v);
          }
        }
        if (resetPage) next.delete('page');
        return next;
      });
    },
    [setSearchParams],
  );

  const handleSearchChange = useCallback(
    (value: string) => updateParams({ q: value || undefined }, true),
    [updateParams],
  );

  const handleStatusChange = useCallback(
    (value: string) => updateParams({ status: value || undefined }, true),
    [updateParams],
  );

  const handleRegionChange = useCallback(
    (value: string) => updateParams({ region: value || undefined }, true),
    [updateParams],
  );

  const handlePlanChange = useCallback(
    (value: string) => updateParams({ plan: value || undefined }, true),
    [updateParams],
  );

  const handleSort = useCallback(
    (field: SortBy) => {
      if (field === sortBy) {
        // Toggle direction
        updateParams({ sort_by: field, sort_dir: sortDir === 'asc' ? 'desc' : 'asc' }, true);
      } else {
        updateParams({ sort_by: field, sort_dir: 'desc' }, true);
      }
    },
    [sortBy, sortDir, updateParams],
  );

  const handlePageChange = useCallback(
    (newPage: number) => updateParams({ page: String(newPage) }),
    [updateParams],
  );

  // Render -----------------------------------------------------------------------
  const tenants = data?.data ?? [];
  const meta = data?.meta;
  const isEmpty = !isLoading && !isError && tenants.length === 0;

  return (
    <div className="space-y-6" data-testid="tenant-list-page">
      <TenantListHeader isPlatformAdmin={isPlatformAdmin} />

      <TenantFilterBar
        q={q}
        status={status}
        region={region}
        plan={plan}
        onSearchChange={handleSearchChange}
        onStatusChange={handleStatusChange}
        onRegionChange={handleRegionChange}
        onPlanChange={handlePlanChange}
      />

      {isError && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400"
        >
          <AlertCircle className="w-5 h-5 shrink-0" aria-hidden="true" />
          <span>Failed to load tenants. Please try again.</span>
        </div>
      )}

      {isEmpty ? (
        <EmptyState />
      ) : (
        <>
          <TenantTable
            tenants={tenants}
            isPlatformAdmin={isPlatformAdmin}
            isLoading={isLoading}
            sortBy={sortBy}
            sortDir={sortDir}
            onSort={handleSort}
          />

          {meta && (
            <PaginationControl
              page={meta.page}
              pageSize={meta.page_size}
              total={meta.total}
              hasNext={meta.has_next}
              onPageChange={handlePageChange}
            />
          )}
        </>
      )}
    </div>
  );
}
