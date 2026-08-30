/**
 * PaginationControl — previous / next page navigation synchronized to URL
 * query params by the parent (TenantListPage).
 */
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginationControlProps {
  page: number;
  pageSize: number;
  total: number;
  hasNext: boolean;
  onPageChange: (page: number) => void;
}

export default function PaginationControl({
  page,
  pageSize,
  total,
  hasNext,
  onPageChange,
}: PaginationControlProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const firstItem = Math.min((page - 1) * pageSize + 1, total);
  const lastItem = Math.min(page * pageSize, total);

  return (
    <div className="flex items-center justify-between px-1 py-3 text-sm text-gray-400">
      {/* Record range */}
      <span>
        {total === 0 ? '0 results' : `${firstItem}–${lastItem} of ${total}`}
      </span>

      {/* Navigation */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-dark-800/60 border border-dark-700/60 text-gray-300 hover:text-white hover:border-primary-500/50 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          aria-label="Previous page"
          data-testid="pagination-prev"
        >
          <ChevronLeft className="w-4 h-4" aria-hidden="true" />
          Prev
        </button>

        <span className="px-3 py-1.5 text-gray-300">
          Page {page} of {totalPages}
        </span>

        <button
          onClick={() => onPageChange(page + 1)}
          disabled={!hasNext}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-dark-800/60 border border-dark-700/60 text-gray-300 hover:text-white hover:border-primary-500/50 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          aria-label="Next page"
          data-testid="pagination-next"
        >
          Next
          <ChevronRight className="w-4 h-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
