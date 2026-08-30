/**
 * TenantOperationalSection — displays plan, region, service_start_date, tenant_notes.
 * Read-only; part of the Tenant Detail page (Packet 12).
 */
import { TenantDetailRecord } from '../../../../services/tenant';

interface Props {
  tenant: TenantDetailRecord;
}

const PLAN_LABELS: Record<string, string> = {
  starter: 'Starter',
  growth: 'Growth',
  enterprise: 'Enterprise',
};

const REGION_LABELS: Record<string, string> = {
  'eu-west': 'EU West',
  'eu-central': 'EU Central',
  'us-east': 'US East',
  'us-west': 'US West',
};

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—';
  try {
    return new Intl.DateTimeFormat('en-GB', {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      timeZone: 'UTC',
    }).format(new Date(dateStr));
  } catch {
    return dateStr;
  }
}

export default function TenantOperationalSection({ tenant }: Props) {
  return (
    <section aria-labelledby="operational-heading" data-testid="section-operational">
      <h2 id="operational-heading" className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
        Operational
      </h2>
      <dl className="grid grid-cols-1 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <dt className="text-xs text-gray-500 mb-0.5">Plan</dt>
          <dd className="text-sm text-gray-100 font-medium" data-testid="detail-plan">
            {PLAN_LABELS[tenant.plan] ?? tenant.plan}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500 mb-0.5">Region</dt>
          <dd className="text-sm text-gray-300" data-testid="detail-region">
            {REGION_LABELS[tenant.region] ?? tenant.region}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500 mb-0.5">Service Start Date</dt>
          <dd className="text-sm text-gray-300" data-testid="detail-service-start-date">
            {formatDate(tenant.service_start_date)}
          </dd>
        </div>
        {tenant.tenant_notes ? (
          <div className="sm:col-span-2 lg:col-span-3">
            <dt className="text-xs text-gray-500 mb-0.5">Notes</dt>
            <dd className="text-sm text-gray-300 whitespace-pre-wrap" data-testid="detail-tenant-notes">
              {tenant.tenant_notes}
            </dd>
          </div>
        ) : (
          <div>
            <dt className="text-xs text-gray-500 mb-0.5">Notes</dt>
            <dd className="text-sm text-gray-500 italic" data-testid="detail-tenant-notes">None</dd>
          </div>
        )}
      </dl>
    </section>
  );
}
