/**
 * TenantRowActions — per-row action buttons.
 *
 * Edit, Provision and Delete are absent (not just disabled) for
 * Platform Viewer.  Delete is a destructive hard-delete that requires
 * the user to retype the tenant slug to confirm.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Eye, Pencil, Rocket, Trash2, AlertTriangle, Loader2 } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';

import { deleteTenant } from '../../../services/tenant';

interface TenantRowActionsProps {
  tenantId: string;
  tenantName: string;
  tenantSlug: string;
  isPlatformAdmin: boolean;
}

export default function TenantRowActions({
  tenantId,
  tenantName,
  tenantSlug,
  isPlatformAdmin,
}: TenantRowActionsProps) {
  const queryClient = useQueryClient();
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [confirmText, setConfirmText] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const closeDialog = () => {
    if (isDeleting) return;
    setIsConfirmOpen(false);
    setConfirmText('');
    setErrorMsg(null);
  };

  const handleConfirmDelete = async () => {
    if (confirmText.trim() !== tenantSlug) {
      setErrorMsg(`Type "${tenantSlug}" exactly to confirm.`);
      return;
    }
    setIsDeleting(true);
    setErrorMsg(null);
    try {
      await deleteTenant(tenantId);
      await queryClient.invalidateQueries({ queryKey: ['tenants'] });
      setIsConfirmOpen(false);
      setConfirmText('');
    } catch (err: unknown) {
      const e = err as {
        response?: { data?: { error?: { message?: string } } };
        message?: string;
      };
      const msg =
        e?.response?.data?.error?.message ||
        e?.message ||
        'Failed to delete tenant. Please try again.';
      setErrorMsg(msg);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <>
      <div className="flex items-center gap-2 justify-end">
        <Link
          to={`/admin/tenants/${tenantId}`}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-dark-700 hover:bg-dark-600 text-gray-300 hover:text-white text-xs font-medium transition-colors"
          aria-label="View tenant details"
          data-testid={`view-btn-${tenantId}`}
        >
          <Eye className="w-3.5 h-3.5" aria-hidden="true" />
          View
        </Link>

        {isPlatformAdmin && (
          <Link
            to={`/admin/tenants/${tenantId}/edit`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-dark-700 hover:bg-dark-600 text-gray-300 hover:text-white text-xs font-medium transition-colors"
            aria-label="Edit tenant"
            data-testid={`edit-btn-${tenantId}`}
          >
            <Pencil className="w-3.5 h-3.5" aria-hidden="true" />
            Edit
          </Link>
        )}

        {isPlatformAdmin && (
          <Link
            to={`/admin/tenants/${tenantId}/provision`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary-600/90 hover:bg-primary-600 text-white text-xs font-medium transition-colors"
            aria-label="Provision tenant"
            data-testid={`provision-btn-${tenantId}`}
          >
            <Rocket className="w-3.5 h-3.5" aria-hidden="true" />
            Provision
          </Link>
        )}

        {isPlatformAdmin && (
          <button
            type="button"
            onClick={() => setIsConfirmOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-red-600/90 hover:bg-red-600 text-white text-xs font-medium transition-colors"
            aria-label="Delete tenant"
            data-testid={`delete-btn-${tenantId}`}
          >
            <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
            Delete
          </button>
        )}
      </div>

      {isConfirmOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby={`delete-tenant-title-${tenantId}`}
          onClick={closeDialog}
        >
          <div
            className="w-full max-w-md rounded-lg border border-red-800/40 bg-dark-900 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start gap-3 px-5 pt-5 pb-3">
              <div className="flex-shrink-0 mt-0.5 text-red-500">
                <AlertTriangle className="w-5 h-5" aria-hidden="true" />
              </div>
              <div className="flex-1">
                <h2
                  id={`delete-tenant-title-${tenantId}`}
                  className="text-base font-semibold text-white"
                >
                  Delete tenant permanently?
                </h2>
                <p className="mt-1 text-sm text-gray-400">
                  This will permanently delete{' '}
                  <span className="text-white font-medium">{tenantName}</span> and
                  every workspace, audit log, dataset and other record that
                  belongs to it.{' '}
                  <span className="text-red-400">This cannot be undone.</span>
                </p>
              </div>
            </div>

            <div className="px-5 pb-3">
              <label
                htmlFor={`delete-tenant-confirm-${tenantId}`}
                className="block text-xs font-medium text-gray-300 mb-1.5"
              >
                Type <span className="font-mono text-red-400">{tenantSlug}</span> to confirm.
              </label>
              <input
                id={`delete-tenant-confirm-${tenantId}`}
                data-testid={`delete-confirm-input-${tenantId}`}
                type="text"
                autoFocus
                disabled={isDeleting}
                value={confirmText}
                onChange={(e) => {
                  setConfirmText(e.target.value);
                  if (errorMsg) setErrorMsg(null);
                }}
                className="w-full rounded-md border border-dark-600 bg-dark-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500 disabled:opacity-60"
                placeholder={tenantSlug}
              />
              {errorMsg && (
                <p
                  role="alert"
                  className="mt-2 text-xs text-red-400"
                  data-testid={`delete-error-${tenantId}`}
                >
                  {errorMsg}
                </p>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-dark-700/60">
              <button
                type="button"
                onClick={closeDialog}
                disabled={isDeleting}
                className="px-3 py-1.5 rounded-md bg-dark-700 hover:bg-dark-600 text-gray-200 text-sm font-medium transition-colors disabled:opacity-60"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                disabled={isDeleting || confirmText.trim() !== tenantSlug}
                data-testid={`delete-confirm-btn-${tenantId}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-red-600 hover:bg-red-500 text-white text-sm font-medium transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isDeleting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                    Deleting…
                  </>
                ) : (
                  <>
                    <Trash2 className="w-4 h-4" aria-hidden="true" />
                    Delete tenant
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
