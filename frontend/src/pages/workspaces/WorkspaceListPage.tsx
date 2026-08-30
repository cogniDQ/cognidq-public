/**
 * WorkspaceListPage — main page for browsing and filtering workspaces.
 *
 * Route: /workspaces
 *
 * URL state (via useSearchParams) drives all filters, sort, and pagination so
 * the current view is shareable and browser-history-aware.
 *
 * The "Create Workspace" button is only rendered for actors who hold the
 * `workspace_administrator` role (read from the JWT in localStorage).
 *
 * For platform_admin: the list is always scoped to a specific tenant via
 * ?tenant_id=<uuid> in the URL (navigated from the tenant detail page).
 * If no tenant_id is provided, they are redirected to the tenant list.
 */
import { useCallback, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle } from 'lucide-react';

import { listWorkspaces, SortBy, SortDir } from '../../services/workspace';
import { getActorRole } from '../../utils/jwt';
import WorkspaceListHeader from '../../components/workspaces/WorkspaceListHeader';
import WorkspaceListFilters from '../../components/workspaces/WorkspaceListFilters';
import WorkspaceTable from '../../components/workspaces/WorkspaceTable';
import EmptyWorkspaceState from '../../components/workspaces/EmptyWorkspaceState';
import PaginationControl from '../../components/admin/tenants/PaginationControl';

const DEFAULT_PAGE_SIZE = 25;
const STALE_TIME = 30_000; // 30 s

function getSearchParam(params: URLSearchParams, key: string): string {
  return params.get(key) ?? '';
}

function getNumParam(params: URLSearchParams, key: string, fallback: number): number {
  const v = params.get(key);
  const n = v !== null ? parseInt(v, 10) : NaN;
  return isNaN(n) ? fallback : n;
}

function getBoolParam(
  params: URLSearchParams,
  key: string,
  fallback: boolean,
): boolean {
  const v = params.get(key);
  if (v === null) return fallback;
  return v === 'true';
}

export default function WorkspaceListPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  // Determine actor role from JWT ------------------------------------------------
  const token = localStorage.getItem('access_token');
  const actorRole = getActorRole(token);
  const isPlatformAdmin = actorRole === 'platform_admin';
  const isWorkspaceAdmin = actorRole === 'workspace_administrator';
  const isTenantAdmin = actorRole === 'tenant_admin';
  // Anyone who can write a workspace into the current tenant: WA, tenant_admin,
  // or platform_admin (must have ?tenant_id= in the URL to know the target).
  const canCreateWorkspace = isWorkspaceAdmin || isTenantAdmin || isPlatformAdmin;

  // Platform admin must arrive here with a ?tenant_id param (from tenant detail).
  // Without it, redirect them to the tenant list to pick a tenant first.
  const tenantIdParam = searchParams.get('tenant_id') ?? undefined;
  useEffect(() => {
    if (isPlatformAdmin && !tenantIdParam) {
      navigate('/admin/tenants', { replace: true });
    }
  }, [isPlatformAdmin, tenantIdParam, navigate]);

  // Read URL state ---------------------------------------------------------------
  const q = getSearchParam(searchParams, 'q');
  const includeArchived = getBoolParam(searchParams, 'include_archived', false);
  const sortBy = (getSearchParam(searchParams, 'sort_by') || 'created_at') as SortBy;
  const sortDir = (getSearchParam(searchParams, 'sort_dir') || 'desc') as SortDir;
  const page = getNumParam(searchParams, 'page', 1);
  const pageSize = getNumParam(searchParams, 'page_size', DEFAULT_PAGE_SIZE);

  // Build query params -----------------------------------------------------------
  const queryParams = {
    q: q || undefined,
    include_archived: includeArchived || undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
    page,
    page_size: pageSize,
    // Pass tenant_id for platform operators so the backend scopes to that tenant.
    tenant_id: isPlatformAdmin ? tenantIdParam : undefined,
  };

  const { data, isLoading, isError } = useQuery({
    queryKey: ['workspaces', queryParams],
    queryFn: () => listWorkspaces(queryParams),
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

  const handleIncludeArchivedChange = useCallback(
    (value: boolean) =>
      updateParams({ include_archived: value ? 'true' : undefined }, true),
    [updateParams],
  );

  const handleSortByChange = useCallback(
    (field: SortBy) => updateParams({ sort_by: field }, true),
    [updateParams],
  );

  const handleSortDirChange = useCallback(
    (dir: SortDir) => updateParams({ sort_dir: dir }, true),
    [updateParams],
  );

  const handleSort = useCallback(
    (field: SortBy) => {
      if (field === sortBy && searchParams.has('sort_dir')) {
        // Column already active with an explicit direction → toggle it
        updateParams(
          { sort_by: field, sort_dir: sortDir === 'asc' ? 'desc' : 'asc' },
          true,
        );
      } else {
        // First click on this column (or direction not yet explicit) → default desc
        updateParams({ sort_by: field, sort_dir: 'desc' }, true);
      }
    },
    [sortBy, sortDir, searchParams, updateParams],
  );

  const handlePageChange = useCallback(
    (newPage: number) => updateParams({ page: String(newPage) }),
    [updateParams],
  );

  // Render -----------------------------------------------------------------------
  const workspaces = data?.data ?? [];
  const meta = data?.meta;
  const isEmpty = !isLoading && !isError && workspaces.length === 0;

  return (
    <div className="space-y-6" data-testid="workspace-list-page">
      <WorkspaceListHeader
        canCreateWorkspace={canCreateWorkspace}
        createTenantIdParam={isPlatformAdmin ? tenantIdParam : undefined}
      />

      <WorkspaceListFilters
        q={q}
        includeArchived={includeArchived}
        sortBy={sortBy}
        sortDir={sortDir}
        onSearchChange={handleSearchChange}
        onIncludeArchivedChange={handleIncludeArchivedChange}
        onSortByChange={handleSortByChange}
        onSortDirChange={handleSortDirChange}
      />

      {isError && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400"
        >
          <AlertCircle className="w-5 h-5 shrink-0" aria-hidden="true" />
          <span>Failed to load workspaces. Please try again.</span>
        </div>
      )}

      {isEmpty ? (
        <EmptyWorkspaceState
          includeArchived={includeArchived}
          canCreateWorkspace={canCreateWorkspace}
          createTenantIdParam={isPlatformAdmin ? tenantIdParam : undefined}
        />
      ) : (
        <>
          <WorkspaceTable
            workspaces={workspaces}
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
