/**
 * ArchiveWorkspaceModal — modal dialog for archiving a workspace (F002 P11).
 *
 * Reactive last-workspace model (TDD §6.4, §8.2):
 *   1. First submit: POST /workspaces/{id}/archive with { status_reason }.
 *   2. If 409 code=last_active_workspace: keep modal open, reveal warning
 *      banner and confirmation checkbox.
 *   3. Second submit (checkbox checked): POST again with
 *      { status_reason, confirm_last_workspace: true }.
 *   4. 200: success toast + close modal + onSuccess() callback.
 *
 * Other error handling:
 *   - 403: permission-denied banner inside modal.
 *   - 409 (non-last-workspace): concurrent-modification banner.
 *   - 422 status_reason field error: adjacent to field.
 *   - 422 entity error: banner.
 */
import { useState, useCallback, FormEvent } from 'react';
import { isAxiosError } from 'axios';
import toast from 'react-hot-toast';
import { AlertCircle, X } from 'lucide-react';

import { archiveWorkspace, ApiErrorBody } from '../../../services/workspace';

interface ArchiveWorkspaceModalProps {
  workspaceId: string;
  workspaceName: string;
  /** Called after successful archive — parent should refetch workspace data. */
  onSuccess: () => void;
  onClose: () => void;
}

export default function ArchiveWorkspaceModal({
  workspaceId,
  workspaceName,
  onSuccess,
  onClose,
}: ArchiveWorkspaceModalProps) {
  const [statusReason, setStatusReason] = useState('');
  const [statusReasonError, setStatusReasonError] = useState<string | undefined>();
  const [hasSubmitted, setHasSubmitted] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [bannerError, setBannerError] = useState<string | null>(null);

  // Reactive: revealed after 409 last_active_workspace
  const [showLastWorkspaceWarning, setShowLastWorkspaceWarning] = useState(false);
  const [confirmLastWorkspace, setConfirmLastWorkspace] = useState(false);

  const reasonTrimmed = statusReason.trim();
  const submitDisabled =
    isSubmitting ||
    (showLastWorkspaceWarning && !confirmLastWorkspace);

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setHasSubmitted(true);
      setBannerError(null);

      if (!reasonTrimmed) {
        setStatusReasonError('Archive reason is required.');
        return;
      }
      setStatusReasonError(undefined);

      setIsSubmitting(true);
      try {
        const body = showLastWorkspaceWarning
          ? { status_reason: reasonTrimmed, confirm_last_workspace: true as const }
          : { status_reason: reasonTrimmed };
        await archiveWorkspace(workspaceId, body);
        toast.success('Workspace archived successfully.');
        onSuccess();
        onClose();
      } catch (err) {
        if (isAxiosError(err)) {
          const status = err.response?.status;
          const errBody = err.response?.data as ApiErrorBody | undefined;

          if (status === 409 && errBody?.error?.code === 'last_active_workspace') {
            // Reactive: reveal the warning + checkbox; keep modal open
            setShowLastWorkspaceWarning(true);
          } else if (status === 409) {
            setBannerError(
              'This workspace was modified concurrently. Please refresh and try again.',
            );
          } else if (status === 403) {
            setBannerError('You do not have permission to archive this workspace.');
          } else if (status === 422 && errBody?.error?.fields?.length) {
            const f = errBody.error.fields.find((x) => x.field === 'status_reason');
            if (f) setStatusReasonError(f.reason);
            else setBannerError(errBody.error.message || 'Validation failed.');
          } else if (status === 422 && errBody?.error) {
            setBannerError(errBody.error.message || 'Validation failed.');
          } else {
            setBannerError('An unexpected error occurred. Please try again.');
          }
        } else {
          setBannerError('Network error. Please check your connection and try again.');
        }
      } finally {
        setIsSubmitting(false);
      }
    },
    [workspaceId, reasonTrimmed, showLastWorkspaceWarning, onSuccess, onClose],
  );

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="archive-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      data-testid="archive-workspace-modal"
    >
      <div className="relative w-full max-w-md rounded-2xl border border-dark-800/60 bg-dark-900 p-6 shadow-2xl">
        {/* Close button */}
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-500 hover:text-gray-300 transition-colors"
          aria-label="Close archive dialog"
          data-testid="archive-cancel-btn"
        >
          <X className="w-5 h-5" />
        </button>

        <h2 id="archive-modal-title" className="text-lg font-semibold text-white mb-1">
          Archive Workspace
        </h2>
        <p className="text-sm text-gray-400 mb-4">
          Archive{' '}
          <strong className="text-white">{workspaceName}</strong>? This will prevent all
          write operations on the workspace.
        </p>

        {/* Generic error banner */}
        {bannerError && (
          <div
            role="alert"
            className="mb-4 flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400 text-sm"
          >
            <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />
            <span>{bannerError}</span>
          </div>
        )}

        {/* Reactive last-workspace warning (revealed after 409) */}
        {showLastWorkspaceWarning && (
          <div
            role="alert"
            className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-amber-300 text-sm"
            data-testid="archive-last-workspace-warning"
          >
            <p className="font-medium mb-1">This is the last active workspace in the tenant.</p>
            <p className="text-amber-400/80">
              After archival the tenant will have no active workspaces. Operations that
              require an active workspace will be unavailable until one is restored.
            </p>
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate>
          {/* status_reason */}
          <div className="mb-4">
            <label
              htmlFor="archive-status-reason"
              className="block text-sm font-medium text-gray-300 mb-1"
            >
              Reason for archival <span className="text-red-400">*</span>
            </label>
            <textarea
              id="archive-status-reason"
              value={statusReason}
              onChange={(e) => {
                setStatusReason(e.target.value);
                if (hasSubmitted || statusReasonError) {
                  setStatusReasonError(
                    e.target.value.trim() ? undefined : 'Archive reason is required.',
                  );
                }
              }}
              rows={3}
              placeholder="Provide a reason for archiving this workspace…"
              className={`w-full rounded-lg border ${
                statusReasonError && (hasSubmitted || statusReasonError)
                  ? 'border-red-500/50 focus:ring-red-500/50 focus:border-red-500'
                  : 'border-dark-700 focus:ring-brand-500/50 focus:border-brand-500'
              } bg-dark-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2`}
              data-testid="archive-status-reason-input"
            />
            {statusReasonError && (
              <p
                role="alert"
                className="mt-1 text-xs text-red-400"
                data-testid="archive-status-reason-error"
              >
                {statusReasonError}
              </p>
            )}
          </div>

          {/* Confirmation checkbox (revealed after 409 last_active_workspace) */}
          {showLastWorkspaceWarning && (
            <div className="mb-4">
              <label className="flex items-start gap-2 cursor-pointer text-sm text-gray-300">
                <input
                  type="checkbox"
                  checked={confirmLastWorkspace}
                  onChange={(e) => setConfirmLastWorkspace(e.target.checked)}
                  className="mt-0.5 rounded border-dark-600 accent-brand-500"
                  data-testid="archive-confirm-last-workspace-checkbox"
                />
                <span>
                  I understand this will be the last active workspace in the tenant.
                </span>
              </label>
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
              type="submit"
              disabled={submitDisabled}
              className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              data-testid="archive-submit-btn"
            >
              {isSubmitting ? 'Archiving…' : 'Archive Workspace'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
