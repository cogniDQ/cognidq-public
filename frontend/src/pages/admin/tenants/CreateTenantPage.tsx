/**
 * CreateTenantPage — Platform Admin only page at /admin/tenants/new.
 *
 * Route is already guarded by AdminGuard requireAdmin in App.tsx — Platform
 * Viewers are shown the 403 page before reaching this component.
 */
import CreateTenantForm from '../../../components/admin/tenants/create/CreateTenantForm';

export default function CreateTenantPage() {
  return (
    <div className="max-w-2xl" data-testid="create-tenant-page">
      {/* Page heading */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white tracking-tight">Create Tenant</h1>
        <p className="mt-1 text-sm text-gray-400">
          Add a new tenant to the platform. Fields marked with{' '}
          <span className="text-red-400">*</span> are required.
        </p>
      </div>

      <div className="rounded-2xl border border-dark-800/60 bg-dark-900/60 p-6 backdrop-blur-sm">
        <CreateTenantForm />
      </div>
    </div>
  );
}

