/**
 * EmptyState — shown when the tenant list query returns zero results.
 */
import { SearchX } from 'lucide-react';

export default function EmptyState() {
  return (
    <div
      className="flex flex-col items-center justify-center py-20 text-center"
      data-testid="empty-state"
    >
      <SearchX className="w-12 h-12 text-gray-600 mb-4" aria-hidden="true" />
      <p className="text-lg font-medium text-gray-300 mb-1">
        No tenants match your filters
      </p>
      <p className="text-sm text-gray-500">
        Try adjusting the search or filter criteria.
      </p>
    </div>
  );
}
