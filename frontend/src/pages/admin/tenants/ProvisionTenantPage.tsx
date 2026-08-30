/**
 * ProvisionTenantPage — Platform Admin only page at
 * /admin/tenants/:tenant_id/provision.
 *
 * Provisions the default workspace + tenant admin against an already
 * created tenant (the tenant row is loaded by tenant_id from the URL).
 *
 * Route is guarded by AdminGuard requireAdmin in App.tsx.
 */
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { AlertCircle, ChevronLeft, SearchX } from 'lucide-react';

import { getTenantDetail } from '../../../services/tenant';
import ProvisionExistingTenantForm from '../../../components/admin/tenants/provision/ProvisionExistingTenantForm';

const STALE_TIME = 30_000;

export default function ProvisionTenantPage() {
  const { tenant_id } = useParams<{ tenant_id: string }>();

  const { data, isLoading, error } = useQuery({
    queryKey: ['tenant', tenant_id],
    queryFn: () => getTenantDetail(tenant_id!),
    staleTime: STALE_TIME,
    enabled: !!tenant_id,
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24" role="status">
        <div className="inline-block h-10 w-10 animate-spin rounded-full border-4 border-solid border-primary-500 border-r-transparent mb-4" />
        <p className="text-sm text-gray-400">Loading tenant…</p>
      </div>
    );
  }

  if (error && isAxiosError(error) && error.response?.status === 404) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <SearchX className="w-12 h-12 text-gray-500 mb-4" aria-hidden="true" />
        <p className="text-xl font-semibold text-gray-300 mb-2">Tenant Not Found</p>
        <Link to="/admin/tenants" className="inline-flex items-center gap-2 text-sm text-primary-400 hover:text-primary-300">
          <ChevronLeft className="w-4 h-4" />
          Back to Tenant List
        </Link>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 flex gap-3" role="alert">
        <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
        <div>
          <p className="text-sm font-medium text-red-300">Failed to load tenant.</p>
          <p className="text-sm text-red-400/80 mt-1">Please refresh the page or try again later.</p>
        </div>
      </div>
    );
  }

  const tenant = data.data;

  return (
    <div className="max-w-3xl" data-testid="provision-tenant-page">
      <div className="mb-4">
        <Link
          to={`/admin/tenants/${tenant.tenant_id}`}
          className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <ChevronLeft className="w-4 h-4" aria-hidden="true" />
          Back to tenant
        </Link>
      </div>

      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white tracking-tight">Provision Tenant</h1>
        <p className="mt-1 text-sm text-gray-400">
          Set up the default workspace and an admin account for this tenant.
          Fields marked with <span className="text-red-400">*</span> are required.
        </p>
      </div>

      <div className="rounded-2xl border border-dark-800/60 bg-dark-900/60 p-6 backdrop-blur-sm">
        <ProvisionExistingTenantForm tenant={tenant} />
      </div>
    </div>
  );
}
