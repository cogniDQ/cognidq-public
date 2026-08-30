/**
 * RestoreWorkspaceModal — confirmation dialog for restoring an archived workspace.
 *
 * Error handling:
 *   - 422 code=tenant_not_active: error banner shown, modal stays open.
 *   - 403: permission-denied banner.
 *   - Other errors: generic banner.
 *   - Submit disabled while in-flight.
 */
import { useState, useCallback } from 'react';
import { isAxiosError } from 'axios';
import toast from 'react-hot-toast';
import { AlertCircle, X } from 'lucide-react';

import { restoreWorkspace, ApiErrorBody } from '../../../services/workspace';

interface RestoreWorkspaceModalProps {
  workspaceId: string;
  workspaceName: string;
  /** Called after successful restore — parent should refetch workspace data. */
  onSuccess: () => void;
  onClose: () => void;
}

export default function RestoreWorkspaceModal({
  workspaceId,
  workspaceName,
  onSuccess,
  onClose,
}: RestoreWorkspaceModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [bannerError, setBannerError] = useState<string | null>(null);

  const handleRestore = useCallback(async () => {
    setBannerError(null);
    setIsSubmitting(true);
    try {
      await restoreWorkspace(workspaceId);
      toast.success('Workspace restored successfully.');
      onSuccess();
      onClose();
    } catch (err) {
      if (isAxiosError(err)) {
        const status = err.response?.status;
        const errBody = err.response?.data as ApiErrorBody | undefined;
        if (status === 422 && errBody?.error?.code === 'tenant_not_active') {
          setBannerError('Cannot restore: the parent tenant is not active.');
        } else if (status === 422 && errBody?.error) {
          setBannerError(errBody.error.message || 'Validation failed.');
        } else if (status === 403) {
          setBannerError('You do not have permission to restore this workspace.');
        } else {
          setBannerError('An unexpected error occurred. Please try again.');
        }
      } else {
        setBannerError('Network error. Please check your connection and try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  }, [workspaceId, onSuccess, onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="restore-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      data-testid="restore-workspace-modal"
    >
      <div className="relative w-full max-w-md rounded-2xl border border-dark-800/60 bg-dark-900 p-6 shadow-2xl">
        {/* Close button */}
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-500 hover:text-gray-300 transition-colors"
          aria-label="Close restore dialog"
          data-testid="restore-cancel-btn"
        >
          <X className="w-5 h-5" />
        </button>

        <h2 id="restore-modal-title" className="text-lg font-semibold text-white mb-1">
          Restore Workspace
        </h2>
        <p className="text-sm text-gray-400 mb-5">
          Restore{' '}
          <strong className="text-white">{workspaceName}</strong> to active status?
          Members will regain access to the workspace immediately.
        </p>

        {/* Error banner */}
        {bannerError && (
          <div
            role="alert"
            className="mb-4 flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400 text-sm"
            data-testid="restore-tenant-error"
          >
            <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />
            <span>{bannerError}</span>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-dark-700 text-gray-300 text-sm font-medium hover:bg-dark-800 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleRestore}
            disabled={isSubmitting}
            className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            data-testid="restore-confirm-btn"
          >
            {isSubmitting ? 'Restoring…' : 'Restore Workspace'}
          </button>
        </div>
      </div>
    </div>
  );
}
