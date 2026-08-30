/**
 * TenantLifecycleSection — displays status (via StatusBadge), status_reason,
 * created_at, updated_at.
 * Read-only; part of the Tenant Detail page (Packet 12).
 */
import StatusBadge from '../StatusBadge';
import { TenantDetailRecord } from '../../../../services/tenant';

interface Props {
  tenant: TenantDetailRecord;
}

function formatDateTime(iso: string): string {
  try {
    return new Intl.DateTimeFormat('en-GB', {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'UTC',
      timeZoneName: 'short',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export default function TenantLifecycleSection({ tenant }: Props) {
  return (
    <section aria-labelledby="lifecycle-heading" data-testid="section-lifecycle">
      <h2 id="lifecycle-heading" className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
        Lifecycle
      </h2>
      <dl className="grid grid-cols-1 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <dt className="text-xs text-gray-500 mb-1">Status</dt>
          <dd data-testid="detail-status">
            <StatusBadge status={tenant.status} />
          </dd>
        </div>
        {tenant.status_reason && (
          <div className="sm:col-span-2">
            <dt className="text-xs text-gray-500 mb-0.5">Status Reason</dt>
            <dd className="text-sm text-gray-300" data-testid="detail-status-reason">
              {tenant.status_reason}
            </dd>
          </div>
        )}
        <div>
          <dt className="text-xs text-gray-500 mb-0.5">Created</dt>
          <dd className="text-sm text-gray-300" data-testid="detail-created-at">
            <time dateTime={tenant.created_at}>{formatDateTime(tenant.created_at)}</time>
          </dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500 mb-0.5">Last Updated</dt>
          <dd className="text-sm text-gray-300" data-testid="detail-updated-at">
            <time dateTime={tenant.updated_at}>{formatDateTime(tenant.updated_at)}</time>
          </dd>
        </div>
      </dl>
    </section>
  );
}
