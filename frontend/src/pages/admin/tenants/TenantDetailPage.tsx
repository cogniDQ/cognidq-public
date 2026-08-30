/**
 * TenantDetailPage — /admin/tenants/:tenant_id
 *
 * Fetches tenant data on mount and renders five read-only sections plus a
 * contextual TenantActionsPanel (Platform Admin only).
 *
 * Loading → spinner
 * 404     → not-found message
 * Other error → error banner
 *
 * Wires StatusChangeModal (Packet 13) to the action buttons.
 *
 * Implemented as part of F001 Packet 12 (detail) + Packet 13 (modal wiring).
 */
import { useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { AlertCircle, SearchX, ChevronLeft, LayoutDashboard } from 'lucide-react';

import { getTenantDetail, TenantStatus } from '../../../services/tenant';
import { getActorRole } from '../../../utils/jwt';
import TenantIdentitySection from '../../../components/admin/tenants/detail/TenantIdentitySection';
import TenantLifecycleSection from '../../../components/admin/tenants/detail/TenantLifecycleSection';
import TenantOperationalSection from '../../../components/admin/tenants/detail/TenantOperationalSection';
import TenantCountsSection from '../../../components/admin/tenants/detail/TenantCountsSection';
import AuditSummaryLink from '../../../components/admin/tenants/detail/AuditSummaryLink';
import TenantActionsPanel from '../../../components/admin/tenants/detail/TenantActionsPanel';
import StatusChangeModal from '../../../components/admin/tenants/StatusChangeModal';

const STALE_TIME = 30_000; // 30 s — matches TDD §5.5

export default function TenantDetailPage() {
  const { tenant_id } = useParams<{ tenant_id: string }>();

  // Role check — action panel is absent for Platform Viewer.
  const isPlatformAdmin =
    getActorRole(localStorage.getItem('access_token')) === 'platform_admin';

  // ── StatusChangeModal state ──────────────────────────────────────────────
  const [modalTarget, setModalTarget] = useState<TenantStatus | null>(null);
  const activateButtonRef = useRef<HTMLButtonElement>(null);
  const suspendButtonRef = useRef<HTMLButtonElement>(null);
  const archiveButtonRef = useRef<HTMLButtonElement>(null);

  function getTriggerRef(target: TenantStatus) {
    if (target === 'active') return activateButtonRef;
    if (target === 'suspended') return suspendButtonRef;
    return archiveButtonRef;
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ['tenant', tenant_id],
    queryFn: () => getTenantDetail(tenant_id!),
    staleTime: STALE_TIME,
    enabled: !!tenant_id,
    retry: false, // do not retry 404s
  });

  // ── Loading ─────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div
        className="flex flex-col items-center justify-center py-24"
        data-testid="detail-loading"
        role="status"
        aria-label="Loading tenant details"
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
        data-testid="detail-not-found"
      >
        <SearchX className="w-12 h-12 text-gray-500 mb-4" aria-hidden="true" />
        <p className="text-xl font-semibold text-gray-300 mb-2">Tenant Not Found</p>
        <p className="text-sm text-gray-500 mb-6">
          No tenant with ID <span className="font-mono text-gray-400">{tenant_id}</span> exists.
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
        data-testid="detail-error"
      >
        <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
        <div>
          <p className="text-sm font-medium text-red-300">Failed to load tenant details.</p>
          <p className="text-sm text-red-400/80 mt-1">Please refresh the page or try again later.</p>
        </div>
      </div>
    );
  }

  const tenant = data.data;

  return (
    <div data-testid="tenant-detail-page">
      {/* ── Back link + page title ─────────────────────────────────────── */}
      <div className="mb-6">
        <Link
          to="/admin/tenants"
          className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors mb-4"
          data-testid="back-to-list"
        >
          <ChevronLeft className="w-4 h-4" aria-hidden="true" />
          All Tenants
        </Link>
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white" data-testid="detail-page-title">
              {tenant.tenant_name}
            </h1>
            <p className="text-sm text-gray-500 font-mono mt-1">{tenant.tenant_slug}</p>
          </div>
          {isPlatformAdmin && (
            <Link
              to={`/hub/workspaces?tenant_id=${tenant.tenant_id}`}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-dark-600 text-gray-300 hover:text-white text-sm font-medium transition-colors"
              data-testid="view-workspaces-btn"
            >
              <LayoutDashboard className="w-4 h-4" aria-hidden="true" />
              View Workspaces
            </Link>
          )}
        </div>
      </div>

      {/* ── Main content card ─────────────────────────────────────────── */}
      <div className="rounded-2xl border border-dark-700/60 bg-dark-800/60 divide-y divide-dark-700/60">

        {/* Identity */}
        <div className="px-6 py-5">
          <TenantIdentitySection tenant={tenant} />
        </div>

        {/* Lifecycle */}
        <div className="px-6 py-5">
          <TenantLifecycleSection tenant={tenant} />
        </div>

        {/* Operational */}
        <div className="px-6 py-5">
          <TenantOperationalSection tenant={tenant} />
        </div>

        {/* Counts */}
        <div className="px-6 py-5">
          <TenantCountsSection tenant={tenant} />
        </div>

        {/* Audit link */}
        <div className="px-6 py-4">
          <AuditSummaryLink tenantId={tenant.tenant_id} />
        </div>

        {/* Actions — Platform Admin only */}
        {isPlatformAdmin && (
          <div className="px-6 py-5">
            <TenantActionsPanel
              tenantId={tenant.tenant_id}
              status={tenant.status}
              activateButtonRef={activateButtonRef}
              suspendButtonRef={suspendButtonRef}
              archiveButtonRef={archiveButtonRef}
              onActivate={() => setModalTarget('active')}
              onSuspend={() => setModalTarget('suspended')}
              onArchive={() => setModalTarget('archived')}
            />
          </div>
        )}
      </div>

      {/* StatusChangeModal — rendered outside the card to avoid stacking context issues */}
      {modalTarget && (
        <StatusChangeModal
          tenantId={tenant.tenant_id}
          currentStatus={tenant.status}
          targetStatus={modalTarget}
          triggerRef={getTriggerRef(modalTarget)}
          onClose={() => setModalTarget(null)}
        />
      )}
    </div>
  );
}
