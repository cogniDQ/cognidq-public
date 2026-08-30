/**
 * TenantTableRow — a single row in the Tenant table.
 */
import { Tenant } from '../../../services/tenant';
import StatusBadge from './StatusBadge';
import TenantRowActions from './TenantRowActions';

interface TenantTableRowProps {
  tenant: Tenant;
  isPlatformAdmin: boolean;
}

function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export default function TenantTableRow({ tenant, isPlatformAdmin }: TenantTableRowProps) {
  return (
    <tr className="border-b border-dark-800/60 hover:bg-dark-800/30 transition-colors">
      {/* Name + slug */}
      <td className="px-4 py-3">
        <div className="font-medium text-white text-sm">{tenant.tenant_name}</div>
        <div className="text-xs text-gray-500 mt-0.5">{tenant.tenant_slug}</div>
      </td>

      {/* Status */}
      <td className="px-4 py-3">
        <StatusBadge status={tenant.status} />
      </td>

      {/* Region */}
      <td className="px-4 py-3 text-sm text-gray-300">{tenant.region}</td>

      {/* Plan */}
      <td className="px-4 py-3">
        <span className="inline-block px-2.5 py-1 rounded-full text-xs font-medium bg-primary-500/10 text-primary-400 capitalize">
          {tenant.plan}
        </span>
      </td>

      {/* Updated */}
      <td className="px-4 py-3 text-sm text-gray-400 tabular-nums">
        {formatDate(tenant.updated_at)}
      </td>

      {/* Created */}
      <td className="px-4 py-3 text-sm text-gray-400 tabular-nums">
        {formatDate(tenant.created_at)}
      </td>

      {/* Actions */}
      <td className="px-4 py-3 text-right">
        <TenantRowActions
          tenantId={tenant.tenant_id}
          tenantName={tenant.tenant_name}
          tenantSlug={tenant.tenant_slug}
          isPlatformAdmin={isPlatformAdmin}
        />
      </td>
    </tr>
  );
}
