/**
 * RegionReadOnly — displays the tenant region as a read-only field.
 *
 * Region is immutable after creation (TDD §6.3). Shown with explanatory
 * text beneath to communicate that it cannot be changed (TDD §5.4).
 */

interface Props {
  value: string;
}

const ID = 'tenant-region-readonly';

export default function RegionReadOnly({ value }: Props) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={ID} className="block text-sm font-medium text-gray-300">
        Region
      </label>
      <input
        id={ID}
        type="text"
        value={value}
        readOnly
        disabled
        className="w-full rounded-lg bg-dark-900/40 border border-dark-700/40 px-3 py-2.5 text-sm text-gray-500 cursor-not-allowed"
        aria-describedby={`${ID}-hint`}
        data-testid="field-region-readonly"
      />
      <p id={`${ID}-hint`} className="text-xs text-gray-600">
        The region is immutable and cannot be changed after creation.
      </p>
    </div>
  );
}
