/**
 * TenantSlugReadOnly — displays the tenant slug as a read-only field.
 *
 * The slug is immutable after creation (TDD §6.2). Shown with explanatory
 * text beneath to communicate that it cannot be changed (TDD §5.4).
 */

interface Props {
  value: string;
}

const ID = 'tenant-slug-readonly';

export default function TenantSlugReadOnly({ value }: Props) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={ID} className="block text-sm font-medium text-gray-300">
        Tenant Slug
      </label>
      <input
        id={ID}
        type="text"
        value={value}
        readOnly
        disabled
        className="w-full rounded-lg bg-dark-900/40 border border-dark-700/40 px-3 py-2.5 text-sm text-gray-500 font-mono cursor-not-allowed"
        aria-describedby={`${ID}-hint`}
        data-testid="field-tenant-slug-readonly"
      />
      <p id={`${ID}-hint`} className="text-xs text-gray-600">
        The slug is immutable and cannot be changed after creation.
      </p>
    </div>
  );
}
