/**
 * FormActions — Cancel and Save buttons for the Create Tenant form.
 *
 * Cancel navigates back to the tenant list.
 * Save triggers form submission.
 */
import { Link } from 'react-router-dom';
import { Loader2, Plus } from 'lucide-react';

interface FormActionsProps {
  isSubmitting: boolean;
}

export default function FormActions({ isSubmitting }: FormActionsProps) {
  return (
    <div className="flex items-center justify-end gap-3 pt-2">
      <Link
        to="/admin/tenants"
        className="px-4 py-2 text-sm font-medium text-gray-400 hover:text-white rounded-lg border border-dark-700/60 bg-dark-800/40 hover:bg-dark-700/60 transition-colors"
        data-testid="btn-cancel"
      >
        Cancel
      </Link>
      <button
        type="submit"
        disabled={isSubmitting}
        className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-primary-600 hover:bg-primary-500 text-white disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
        data-testid="btn-save"
      >
        {isSubmitting ? (
          <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
        ) : (
          <Plus className="w-4 h-4" aria-hidden="true" />
        )}
        {isSubmitting ? 'Creating…' : 'Create Tenant'}
      </button>
    </div>
  );
}
