/**
 * TenantActionsPanel — contextual action buttons for Platform Admin only.
 *
 * Button visibility is driven by the TDD §2.6 status transition matrix:
 *
 *   Current Status │ ActivateButton │ SuspendButton │ ArchiveButton │ EditMetadataButton
 *   ───────────────┼────────────────┼───────────────┼───────────────┼────────────────────
 *   draft          │       ✗        │       ✗        │       ✓       │         ✓
 *   active         │       ✗        │       ✓        │       ✓       │         ✓
 *   suspended      │       ✓        │       ✗        │       ✓       │         ✓
 *   archived       │       ✗        │       ✗        │       ✗       │         ✗
 *
 * Button refs are forwarded from TenantDetailPage so that focus can be
 * restored to the triggering button when the StatusChangeModal closes (AC-13.7).
 *
 * Part of the Tenant Detail page (Packet 12 + Packet 13).
 */
import { RefObject } from 'react';
import { Link } from 'react-router-dom';
import { Edit2, CheckCircle2, PauseCircle, Archive, Rocket, Plus } from 'lucide-react';
import { TenantStatus } from '../../../../services/tenant';

interface Props {
  tenantId: string;
  status: TenantStatus;
  /** Ref forwarded to the Activate button — used for focus restoration after modal close. */
  activateButtonRef?: RefObject<HTMLButtonElement>;
  /** Ref forwarded to the Suspend button — used for focus restoration after modal close. */
  suspendButtonRef?: RefObject<HTMLButtonElement>;
  /** Ref forwarded to the Archive button — used for focus restoration after modal close. */
  archiveButtonRef?: RefObject<HTMLButtonElement>;
  onActivate: () => void;
  onSuspend: () => void;
  onArchive: () => void;
}

// ---------------------------------------------------------------------------
// Transition matrix derived from TDD §2.6
// ---------------------------------------------------------------------------

/** Returns which action buttons are allowed for the given current status. */
function getAllowedActions(status: TenantStatus) {
  return {
    canEdit: status !== 'archived',
    // suspended → active
    canActivate: status === 'suspended',
    // active → suspended
    canSuspend: status === 'active',
    // draft | active | suspended → archived
    canArchive: status === 'draft' || status === 'active' || status === 'suspended',
    // archived tenants cannot be provisioned (matches backend gate)
    canProvision: status !== 'archived',
  };
}

export default function TenantActionsPanel({
  tenantId,
  status,
  activateButtonRef,
  suspendButtonRef,
  archiveButtonRef,
  onActivate,
  onSuspend,
  onArchive,
}: Props) {
  const { canEdit, canActivate, canSuspend, canArchive, canProvision } = getAllowedActions(status);

  const noneAvailable = !canEdit && !canActivate && !canSuspend && !canArchive && !canProvision;
  if (noneAvailable) {
    return (
      <aside data-testid="tenant-actions-panel" aria-label="Tenant actions">
        <p className="text-sm text-gray-500 italic">No actions available for this tenant.</p>
      </aside>
    );
  }

  return (
    <aside data-testid="tenant-actions-panel" aria-label="Tenant actions">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
        Actions
      </h2>
      <div className="flex flex-wrap gap-2">
        {canEdit && (
          <Link
            to={`/admin/tenants/${tenantId}/edit`}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-dark-700/60 border border-dark-600/60 text-gray-200 hover:bg-dark-600/60 hover:text-white transition-colors"
            data-testid="btn-edit-metadata"
          >
            <Edit2 className="w-4 h-4" aria-hidden="true" />
            Edit Metadata
          </Link>
        )}

        {canProvision && (
          <Link
            to={`/admin/tenants/${tenantId}/provision`}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-primary-600 hover:bg-primary-700 text-white transition-colors"
            data-testid="btn-provision"
          >
            <Rocket className="w-4 h-4" aria-hidden="true" />
            Provision
          </Link>
        )}

        {status === 'active' && (
          <Link
            to={`/hub/workspaces/new?tenant_id=${tenantId}`}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-dark-700/60 border border-dark-600/60 text-gray-200 hover:bg-dark-600/60 hover:text-white transition-colors"
            data-testid="btn-create-workspace"
          >
            <Plus className="w-4 h-4" aria-hidden="true" />
            Create Workspace
          </Link>
        )}

        {canActivate && (
          <button
            type="button"
            ref={activateButtonRef}
            onClick={onActivate}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20 hover:text-emerald-300 transition-colors"
            data-testid="btn-activate"
          >
            <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
            Activate
          </button>
        )}

        {canSuspend && (
          <button
            type="button"
            ref={suspendButtonRef}
            onClick={onSuspend}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-amber-500/10 border border-amber-500/30 text-amber-400 hover:bg-amber-500/20 hover:text-amber-300 transition-colors"
            data-testid="btn-suspend"
          >
            <PauseCircle className="w-4 h-4" aria-hidden="true" />
            Suspend
          </button>
        )}

        {canArchive && (
          <button
            type="button"
            ref={archiveButtonRef}
            onClick={onArchive}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20 hover:text-red-300 transition-colors"
            data-testid="btn-archive"
          >
            <Archive className="w-4 h-4" aria-hidden="true" />
            Archive
          </button>
        )}
      </div>
    </aside>
  );
}
