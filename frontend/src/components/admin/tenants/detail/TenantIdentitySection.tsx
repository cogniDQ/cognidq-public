/**
 * TenantIdentitySection — displays tenant_id, tenant_name, tenant_slug.
 * Read-only; part of the Tenant Detail page (Packet 12).
 */
import { TenantDetailRecord } from '../../../../services/tenant';

interface Props {
  tenant: TenantDetailRecord;
}

export default function TenantIdentitySection({ tenant }: Props) {
  return (
    <section aria-labelledby="identity-heading" data-testid="section-identity">
      <h2 id="identity-heading" className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
        Identity
      </h2>
      <dl className="grid grid-cols-1 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <dt className="text-xs text-gray-500 mb-0.5">Tenant ID</dt>
          <dd className="text-sm font-mono text-gray-200 break-all" data-testid="detail-tenant-id">
            {tenant.tenant_id}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500 mb-0.5">Name</dt>
          <dd className="text-sm text-gray-100 font-medium" data-testid="detail-tenant-name">
            {tenant.tenant_name}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500 mb-0.5">Slug</dt>
          <dd className="text-sm font-mono text-gray-200" data-testid="detail-tenant-slug">
            {tenant.tenant_slug}
          </dd>
        </div>
      </dl>
    </section>
  );
}
