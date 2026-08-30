/**
 * TenantListHeader — page heading and Create Tenant CTA.
 *
 * Provisioning is handled per-tenant (row action / detail page) and is no
 * longer surfaced as a top-level button. The Create button is absent
 * entirely (not just disabled) for Platform Viewer.
 */
import { Link } from 'react-router-dom';
import { Plus } from 'lucide-react';

interface TenantListHeaderProps {
  isPlatformAdmin: boolean;
}

export default function TenantListHeader({ isPlatformAdmin }: TenantListHeaderProps) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-bold text-white">Tenants</h1>
        <p className="mt-1 text-sm text-gray-400">
          Manage platform tenants, lifecycle, and access.
        </p>
      </div>
      {isPlatformAdmin && (
        <div className="flex items-center gap-3">
          <Link
            to="/admin/tenants/new"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium transition-colors"
            data-testid="create-tenant-btn"
          >
            <Plus className="w-4 h-4" aria-hidden="true" />
            Create Tenant
          </Link>
        </div>
      )}
    </div>
  );
}
