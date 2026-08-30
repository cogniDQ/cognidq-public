/**
 * WorkspaceRoleSelector — F007 P04
 *
 * A controlled dropdown that lets a `workspace_administrator` assign or
 * update the workspace role of a member.
 *
 * Behaviour:
 *  - Shows current role in a <select> element.
 *  - Calls `PUT /workspaces/{workspaceId}/members/{userId}/role` on change.
 *  - Optimistic: updates displayed value immediately — rolls back on API error
 *    (toast notification both ways).
 *  - When `readonly=true`, renders a plain text badge instead of a select.
 *
 * Props:
 *   workspaceId  — workspace UUID
 *   userId       — target member's user UUID
 *   currentRole  — current WorkspaceRoleName (or null if unassigned)
 *   readonly     — when true, renders read-only role badge (no dropdown)
 *   onRoleChange — optional callback fired after a successful API update
 */
import React, { useState } from 'react';
import toast from 'react-hot-toast';
import {
  ALL_ROLE_NAMES,
  ROLE_DISPLAY_NAMES,
  WorkspaceRoleName,
  assignMemberRole,
} from '../../services/workspaceRoles';

interface WorkspaceRoleSelectorProps {
  workspaceId: string;
  userId: string;
  currentRole: WorkspaceRoleName | null;
  readonly?: boolean;
  onRoleChange?: (newRole: WorkspaceRoleName) => void;
}

const WorkspaceRoleSelector: React.FC<WorkspaceRoleSelectorProps> = ({
  workspaceId,
  userId,
  currentRole,
  readonly = false,
  onRoleChange,
}) => {
  const [displayedRole, setDisplayedRole] = useState<WorkspaceRoleName | null>(
    currentRole,
  );
  const [saving, setSaving] = useState(false);

  const handleChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newRole = e.target.value as WorkspaceRoleName;
    const previousRole = displayedRole;

    // Optimistic update
    setDisplayedRole(newRole);
    setSaving(true);

    try {
      await assignMemberRole(workspaceId, userId, newRole);
      toast.success(
        `Role updated to "${ROLE_DISPLAY_NAMES[newRole]}"`,
        { id: `role-update-${userId}` },
      );
      onRoleChange?.(newRole);
    } catch (_err: unknown) {
      // Rollback
      setDisplayedRole(previousRole);
      const err = _err as { response?: { data?: { error?: { message?: string } } } };
      const apiMsg = err?.response?.data?.error?.message;
      toast.error(apiMsg ?? 'Failed to update role. Please try again.', {
        id: `role-update-error-${userId}`,
      });
    } finally {
      setSaving(false);
    }
  };

  // ── Read-only: render plain text ──────────────────────────────────────────
  if (readonly) {
    return (
      <span
        data-testid="workspace-role-selector-readonly"
        className="text-sm text-gray-700"
      >
        {displayedRole ? ROLE_DISPLAY_NAMES[displayedRole] : '—'}
      </span>
    );
  }

  // ── Editable: render select ───────────────────────────────────────────────
  return (
    <select
      data-testid="workspace-role-selector"
      value={displayedRole ?? ''}
      onChange={handleChange}
      disabled={saving}
      aria-label="Workspace role"
      className="
        text-sm rounded border border-gray-300
        bg-white px-2 py-1
        focus:outline-none focus:ring-2 focus:ring-blue-500
        disabled:opacity-50 disabled:cursor-not-allowed
      "
    >
      {!displayedRole && (
        <option value="" disabled>
          — Assign role —
        </option>
      )}
      {ALL_ROLE_NAMES.map((role) => (
        <option key={role} value={role}>
          {ROLE_DISPLAY_NAMES[role]}
        </option>
      ))}
    </select>
  );
};

export default WorkspaceRoleSelector;
