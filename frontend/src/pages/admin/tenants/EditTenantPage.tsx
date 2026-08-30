/**
 * EditTenantPage — /admin/tenants/:tenant_id/edit
 *
 * Platform Admin only (guarded by AdminGuard in App.tsx).
 * Fetches the current tenant data (warm cache or fresh), then renders
 * EditTenantForm which handles change-set detection, validation, and PATCH.
 *
 * Loading → spinner
 * 404     → not-found message
 * Other error → error banner
 *
 * Implemented in Packet 13.
 */
import { Link } from 'react-router-dom';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { AlertCircle, SearchX, ChevronLeft } from 'lucide-react';

import { getTenantDetail } from '../../../services/tenant';
import EditTenantForm from '../../../components/admin/tenants/edit/EditTenantForm';

const STALE_TIME = 30_000;

export default function EditTenantPage() {
  const { tenant_id } = useParams<{ tenant_id: string }>();

  const { data, isLoading, error } = useQuery({
    queryKey: ['tenant', tenant_id],
    queryFn: () => getTenantDetail(tenant_id!),
    staleTime: STALE_TIME,
    enabled: !!tenant_id,
    retry: false,
  });

  // ── Loading ──────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div
        className="flex flex-col items-center justify-center py-24"
        role="status"
        aria-label="Loading tenant details"
        data-testid="edit-loading"
      >
        <div className="inline-block h-10 w-10 animate-spin rounded-full border-4 border-solid border-primary-500 border-r-transparent mb-4" />
        <p className="text-sm text-gray-400">Loading tenant…</p>
      </div>
    );
  }

  // ── Not found ────────────────────────────────────────────────────────────
  if (error && isAxiosError(error) && error.response?.status === 404) {
    return (
      <div
        className="flex flex-col items-center justify-center py-24 text-center"
        data-testid="edit-not-found"
      >
        <SearchX className="w-12 h-12 text-gray-500 mb-4" aria-hidden="true" />
        <p className="text-xl font-semibold text-gray-300 mb-2">Tenant Not Found</p>
        <p className="text-sm text-gray-500 mb-6">
          No tenant with ID{' '}
          <span className="font-mono text-gray-400">{tenant_id}</span> exists.
        </p>
        <Link
          to="/admin/tenants"
          className="inline-flex items-center gap-2 text-sm text-primary-400 hover:text-primary-300 transition-colors"
        >
          <ChevronLeft className="w-4 h-4" />
          Back to Tenant List
        </Link>
      </div>
    );
  }

  // ── Generic error ────────────────────────────────────────────────────────
  if (error || !data) {
    return (
      <div
        className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 flex gap-3"
        role="alert"
        data-testid="edit-error"
      >
        <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
        <div>
          <p className="text-sm font-medium text-red-300">Failed to load tenant details.</p>
          <p className="text-sm text-red-400/80 mt-1">
            Please refresh the page or try again later.
          </p>
        </div>
      </div>
    );
  }

  const tenant = data.data;

  return (
    <div data-testid="edit-tenant-page">
      {/* ── Back link + page title ─────────────────────────────────────── */}
      <div className="mb-6">
        <Link
          to={`/admin/tenants/${tenant.tenant_id}`}
          className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors mb-4"
          data-testid="back-to-detail"
        >
          <ChevronLeft className="w-4 h-4" aria-hidden="true" />
          {tenant.tenant_name}
        </Link>
        <h1 className="text-2xl font-bold text-white" data-testid="edit-page-title">
          Edit Tenant
        </h1>
        <p className="text-sm text-gray-500 font-mono mt-1">{tenant.tenant_slug}</p>
      </div>

      {/* ── Form card ─────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-dark-700/60 bg-dark-800/60 px-6 py-6 max-w-2xl">
        <EditTenantForm initialData={tenant} />
      </div>
    </div>
  );
}
