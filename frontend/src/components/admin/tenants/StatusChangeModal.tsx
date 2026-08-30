/**
 * StatusChangeModal — modal dialog for tenant status transitions.
 *
 * Triggered by Activate / Suspend / Archive buttons in TenantActionsPanel.
 * Displays a plain-language summary of the transition, contextual impact
 * description, and (for suspend/archive only) a required reason input.
 *
 * Accessibility (TDD §5.6 + AC-13.6 / AC-13.7):
 * - Focus is trapped inside the modal while open.
 * - On close (Cancel or success), focus returns to the triggering button.
 * - Escape key closes the modal.
 *
 * On API success (AC-13.5):
 * - Modal closes, cache invalidated, success toast shown.
 *
 * On API error:
 * - Modal stays open, inline error shown, Confirm re-enabled.
 */
import { useEffect, useRef, useState, RefObject } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import toast from 'react-hot-toast';
import { X, AlertCircle } from 'lucide-react';

import {
  TenantStatus,
  ChangeTenantStatusRequest,
  changeTenantStatus,
} from '../../../services/tenant';
import { validateStatusReason } from '../../../utils/tenantValidation';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Props {
  tenantId: string;
  currentStatus: TenantStatus;
  targetStatus: TenantStatus;
  /** Ref to the button that opened this modal — focus is restored here on close. */
  triggerRef: RefObject<HTMLButtonElement>;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// Helpers — transition copy
// ---------------------------------------------------------------------------

function getTransitionLabel(status: TenantStatus): string {
  const labels: Record<TenantStatus, string> = {
    draft: 'Draft',
    active: 'Active',
    suspended: 'Suspended',
    archived: 'Archived',
  };
  return labels[status];
}

function getImpactItems(targetStatus: TenantStatus): string[] {
  switch (targetStatus) {
    case 'active':
      return [
        'The tenant will regain access to all platform services.',
        'Any existing session invalidation will be lifted.',
        'The status reason will be automatically cleared.',
      ];
    case 'suspended':
      return [
        'All active user sessions for this tenant will be invalidated.',
        'Tenant users will not be able to log in until the suspension is lifted.',
        'Existing data and configuration will be preserved.',
      ];
    case 'archived':
      return [
        'This action is irreversible — archived tenants cannot be restored.',
        'All user sessions will be immediately invalidated.',
        'The tenant record is retained for audit purposes but made inaccessible.',
      ];
    default:
      return [];
  }
}

/** Returns true when the target status requires a reason. */
function requiresReason(target: TenantStatus): boolean {
  return target === 'suspended' || target === 'archived';
}

// ---------------------------------------------------------------------------
// Focus trap
// ---------------------------------------------------------------------------

const FOCUSABLE_SELECTORS =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function trapFocus(container: HTMLElement, e: KeyboardEvent) {
  const elements = Array.from(
    container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTORS),
  ).filter((el) => !el.hasAttribute('disabled'));

  if (elements.length === 0) return;

  const first = elements[0];
  const last = elements[elements.length - 1];

  if (e.shiftKey) {
    if (document.activeElement === first) {
      e.preventDefault();
      last.focus();
    }
  } else {
    if (document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function StatusChangeModal({
  tenantId,
  currentStatus,
  targetStatus,
  triggerRef,
  onClose,
}: Props) {
  const queryClient = useQueryClient();
  const modalRef = useRef<HTMLDivElement>(null);

  const needsReason = requiresReason(targetStatus);
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState<string | undefined>();
  const [apiError, setApiError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // ── Focus first interactive element when modal opens ────────────────────
  useEffect(() => {
    const modal = modalRef.current;
    if (!modal) return;

    const firstFocusable = modal.querySelector<HTMLElement>(FOCUSABLE_SELECTORS);
    firstFocusable?.focus();
  }, []);

  // ── Focus trap + Escape key ──────────────────────────────────────────────
  useEffect(() => {
    const modal = modalRef.current;
    if (!modal) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        handleClose();
        return;
      }
      if (e.key === 'Tab') {
        trapFocus(modal!, e);
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
     
  }, []);

  // ── Close + focus restoration ────────────────────────────────────────────
  function handleClose() {
    onClose();
    // Restore focus to triggering button (AC-13.7)
    requestAnimationFrame(() => {
      triggerRef.current?.focus();
    });
  }

  // ── Confirm submit ───────────────────────────────────────────────────────
  async function handleConfirm() {
    setApiError(null);

    // Validate reason before submit
    const reasonErr = validateStatusReason(reason, needsReason);
    if (reasonErr) {
      setReasonError(reasonErr);
      return;
    }

    const body: ChangeTenantStatusRequest = { target_status: targetStatus };
    if (needsReason) {
      body.status_reason = reason.trim();
    }

    setIsSubmitting(true);
    try {
      await changeTenantStatus(tenantId, body);
      queryClient.invalidateQueries({ queryKey: ['tenant', tenantId] });
      toast.success(`Tenant ${getTransitionLabel(targetStatus).toLowerCase()} successfully.`);
      onClose();
      // Focus restoration happens separately in onClose handler in parent
      requestAnimationFrame(() => {
        triggerRef.current?.focus();
      });
    } catch (err) {
      if (isAxiosError(err)) {
        const body = err.response?.data as {
          error?: { message?: string };
        } | undefined;
        setApiError(body?.error?.message ?? 'An unexpected error occurred. Please try again.');
      } else {
        setApiError('An unexpected error occurred. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  // Confirm disabled when: submitting, or reason is shown but not valid
  const confirmDisabled =
    isSubmitting || (needsReason && reason.trim().length < 10);

  const impactItems = getImpactItems(targetStatus);

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      role="presentation"
      data-testid="status-modal-backdrop"
      onClick={(e) => {
        // close on backdrop click
        if (e.target === e.currentTarget) handleClose();
      }}
    >
      {/* Dialog */}
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="status-modal-title"
        aria-describedby="status-modal-desc"
        className="relative w-full max-w-md mx-4 rounded-2xl border border-dark-700/60 bg-dark-800 shadow-2xl"
        data-testid="status-change-modal"
      >
        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b border-dark-700/60">
          <div>
            <h2
              id="status-modal-title"
              className="text-base font-semibold text-white"
              data-testid="modal-title"
            >
              Confirm Status Change
            </h2>
            {/* TransitionSummary — AC-13.4 */}
            <p
              id="status-modal-desc"
              className="text-sm text-gray-400 mt-1"
              data-testid="modal-transition-summary"
            >
              Changing status from{' '}
              <span className="font-medium text-gray-200">
                {getTransitionLabel(currentStatus)}
              </span>{' '}
              to{' '}
              <span className="font-medium text-gray-200">
                {getTransitionLabel(targetStatus)}
              </span>
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-dark-700/60 transition-colors"
            aria-label="Close modal"
            data-testid="btn-modal-close-x"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          {/* ImpactDescriptionList */}
          {impactItems.length > 0 && (
            <ul
              className="space-y-1.5 text-sm text-gray-400"
              data-testid="modal-impact-list"
            >
              {impactItems.map((item) => (
                <li key={item} className="flex items-start gap-2">
                  <span className="mt-1.5 w-1 h-1 rounded-full bg-gray-500 shrink-0" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          )}

          {/* StatusReasonInput — only for suspend/archive (AC-13.4) */}
          {needsReason && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label
                  htmlFor="modal-status-reason"
                  className="block text-sm font-medium text-gray-300"
                >
                  Reason <span className="text-red-400" aria-hidden="true">*</span>
                </label>
                <span
                  className={`text-xs tabular-nums ${reason.length > 450 ? 'text-amber-400' : 'text-gray-500'}`}
                  aria-live="polite"
                  aria-label={`${reason.length} of 500 characters used`}
                  data-testid="modal-reason-char-count"
                >
                  {reason.length} / 500
                </span>
              </div>
              <textarea
                id="modal-status-reason"
                value={reason}
                onChange={(e) => {
                  setReason(e.target.value);
                  setReasonError(undefined);
                }}
                onBlur={() =>
                  setReasonError(validateStatusReason(reason, true))
                }
                rows={3}
                maxLength={510}
                className={`w-full rounded-lg bg-dark-900/60 border px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 outline-none transition-colors resize-y focus:ring-2 focus:ring-primary-500/50 ${
                  reasonError
                    ? 'border-red-500/60'
                    : 'border-dark-700/60 focus:border-primary-500/60'
                }`}
                placeholder="Describe the reason (min 10 characters)…"
                aria-required="true"
                aria-describedby={reasonError ? 'modal-reason-error' : 'modal-reason-hint'}
                data-testid="modal-reason-input"
              />
              {reasonError ? (
                <p
                  id="modal-reason-error"
                  className="text-xs text-red-400"
                  role="alert"
                  data-testid="modal-reason-error"
                >
                  {reasonError}
                </p>
              ) : (
                <p id="modal-reason-hint" className="text-xs text-gray-600">
                  Required. Minimum 10 characters.
                </p>
              )}
            </div>
          )}

          {/* API error inline */}
          {apiError && (
            <div
              className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 flex gap-2"
              role="alert"
              data-testid="modal-api-error"
            >
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
              <p className="text-sm text-red-300">{apiError}</p>
            </div>
          )}
        </div>

        {/* Footer — ModalActions */}
        <div className="flex items-center justify-end gap-3 px-5 pb-5">
          <button
            type="button"
            onClick={handleClose}
            className="px-4 py-2 rounded-lg text-sm font-medium text-gray-300 bg-dark-700/60 border border-dark-600/60 hover:bg-dark-600/60 hover:text-white transition-colors"
            data-testid="btn-modal-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={confirmDisabled}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            data-testid="btn-modal-confirm"
          >
            {isSubmitting ? 'Confirming…' : 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  );
}
