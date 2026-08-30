/**
 * AddMemberModal — search for a tenant user by email and assign them a role
 * in the workspace (F078 P03).
 *
 * Usage: rendered by WorkspaceMembersPage when workspace_administrator clicks
 * "Add Member".
 */
import { useState, useEffect, useRef } from 'react';
import { X, Search, UserPlus, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';

import { searchNonMembers } from '../../../services/workspaceMembers';
import { assignMemberRole } from '../../../services/workspaceRoles';
import type { WorkspaceRoleName } from '../../../services/workspaceRoles';
import { ROLE_DISPLAY_NAMES, ALL_ROLE_NAMES } from '../../../services/workspaceRoles';
import type { UserSearchItem } from '../../../services/workspaceMembers';

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

interface AddMemberModalProps {
  workspaceId: string;
  onClose: () => void;
  onAdded: () => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export default function AddMemberModal({ workspaceId, onClose, onAdded }: AddMemberModalProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<UserSearchItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<UserSearchItem | null>(null);
  const [selectedRole, setSelectedRole] = useState<WorkspaceRoleName>('governance_viewer');
  const [adding, setAdding] = useState(false);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (query.length < 2) {
      setResults([]);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await searchNonMembers(workspaceId, query);
        setResults(res.users);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, workspaceId]);

  async function handleAdd() {
    if (!selected) return;
    setAdding(true);
    try {
      await assignMemberRole(workspaceId, selected.user_id, selectedRole);
      toast.success(`${selected.display_name} added as ${ROLE_DISPLAY_NAMES[selectedRole]}.`);
      onAdded();
    } catch {
      toast.error('Failed to add member. Please try again.');
    } finally {
      setAdding(false);
    }
  }

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={e => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-md bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl p-6">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-500 hover:text-gray-300 transition-colors"
          aria-label="Close"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Title */}
        <div className="flex items-center gap-2 mb-5">
          <UserPlus className="w-5 h-5 text-indigo-400" />
          <h2 className="text-lg font-semibold text-white">Add Member</h2>
        </div>

        {/* Search input */}
        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
          <input
            ref={inputRef}
            type="text"
            placeholder="Search by email…"
            value={query}
            onChange={e => {
              setQuery(e.target.value);
              setSelected(null);
            }}
            className="w-full pl-9 pr-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          {searching && (
            <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 animate-spin" />
          )}
        </div>

        {/* Search results */}
        {!selected && results.length > 0 && (
          <ul className="mb-4 rounded-lg border border-gray-700 overflow-hidden divide-y divide-gray-700/50 max-h-48 overflow-y-auto">
            {results.map(user => (
              <li key={user.user_id}>
                <button
                  onClick={() => setSelected(user)}
                  className="w-full text-left px-4 py-2.5 bg-gray-800 hover:bg-gray-700 transition-colors"
                >
                  <div className="text-sm font-medium text-white">{user.display_name}</div>
                  <div className="text-xs text-gray-500">{user.email}</div>
                </button>
              </li>
            ))}
          </ul>
        )}

        {!selected && query.length >= 2 && !searching && results.length === 0 && (
          <p className="text-sm text-gray-500 mb-4">No users found matching "{query}".</p>
        )}

        {/* Selected user + role picker */}
        {selected && (
          <div className="mb-5">
            <div className="flex items-center justify-between p-3 rounded-lg bg-gray-800 border border-indigo-700 mb-3">
              <div>
                <div className="text-sm font-medium text-white">{selected.display_name}</div>
                <div className="text-xs text-gray-500">{selected.email}</div>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-gray-500 hover:text-gray-300 transition-colors ml-2"
                aria-label="Deselect user"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <label className="block text-sm text-gray-400 mb-1.5">
              Assign role
            </label>
            <select
              value={selectedRole}
              onChange={e => setSelectedRole(e.target.value as WorkspaceRoleName)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {ALL_ROLE_NAMES.map(r => (
                <option key={r} value={r}>
                  {ROLE_DISPLAY_NAMES[r]}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200 transition-colors"
          >
            Cancel
          </button>
          <button
            disabled={!selected || adding}
            onClick={handleAdd}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {adding && <Loader2 className="w-4 h-4 animate-spin" />}
            {adding ? 'Adding…' : 'Add Member'}
          </button>
        </div>
      </div>
    </div>
  );
}
