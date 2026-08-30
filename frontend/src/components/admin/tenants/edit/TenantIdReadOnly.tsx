/**
 * TenantIdReadOnly — displays the tenant UUID as a read-only field.
 *
 * The tenant_id is a system-generated immutable identifier. It is shown
 * for reference but cannot be edited.
 */

interface Props {
  value: string;
}

const ID = 'tenant-id-readonly';

export default function TenantIdReadOnly({ value }: Props) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={ID} className="block text-sm font-medium text-gray-300">
        Tenant ID
      </label>
      <input
        id={ID}
        type="text"
        value={value}
        readOnly
        disabled
        className="w-full rounded-lg bg-dark-900/40 border border-dark-700/40 px-3 py-2.5 text-sm text-gray-500 font-mono cursor-not-allowed"
        data-testid="field-tenant-id-readonly"
      />
    </div>
  );
}
