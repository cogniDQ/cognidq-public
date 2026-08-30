/**
 * Roles & Permissions — shows the fixed workspace-role permission matrix,
 * the two platform-level roles, and (when scoped to a workspace) the
 * custom roles for that workspace with create / edit / delete support.
 */
import { useMemo, useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Shield, CheckCircle, XCircle, Crown, Boxes,
  Plus, Pencil, Trash2, Sparkles, X, Loader2,
} from 'lucide-react';
import {
  FIXED_ROLE_PERMISSIONS,
  ROLE_DISPLAY_NAMES,
  ALL_ROLE_NAMES,
  listCustomRoles,
  listKnownPermissions,
  createCustomRole,
  updateCustomRole,
  deleteCustomRole,
  type WorkspaceRoleName,
  type CustomRoleResponse,
} from '../services/workspaceRoles';
import { useWorkspacePermissions } from '../hooks/useWorkspacePermissions';
import { getActorRole, getActorId } from '../utils/jwt';

// ── Platform roles (not workspace-scoped) ────────────────────────────────

const PLATFORM_ROLES = [
  {
    key: 'platform_admin' as const,
    label: 'Platform Admin',
    description: 'Full platform access. Can manage tenants, view all workspaces, and read all workspace data.',
    scope: 'Platform',
    access: 'All workspace read permissions + tenant management',
  },
  {
    key: 'platform_viewer' as const,
    label: 'Platform Viewer',
    description: 'Read-only platform access. Can view tenants and workspaces across the platform.',
    scope: 'Platform',
    access: 'All workspace read permissions (no writes)',
  },
];

// ── Workspace role descriptions ──────────────────────────────────────────

const ROLE_DESCRIPTIONS: Record<WorkspaceRoleName, string> = {
  workspace_administrator: 'Full control over workspace settings, members, roles, data sources, datasets, quality rules, and issues.',
  data_engineer: 'Can manage data sources, datasets, rules, executions, and issues. Cannot manage members or workspace settings.',
  data_steward: 'Can manage datasets and rules. Can triage issues. Read-only for data sources.',
  business_analyst: 'Read-only access to datasets, rules, executions, issues, incidents, and reports.',
  governance_viewer: 'Read-only access across the workspace for governance auditing purposes.',
};

// ── Group permissions by resource ────────────────────────────────────────

function groupByResource(perms: string[]): Record<string, string[]> {
  const grouped: Record<string, string[]> = {};
  for (const p of [...perms].sort()) {
    const [resource] = p.split(':');
    (grouped[resource] ??= []).push(p);
  }
  return grouped;
}

function buildFixedPermissionResources() {
  const allPerms = new Set<string>();
  for (const perms of Object.values(FIXED_ROLE_PERMISSIONS)) {
    for (const p of perms) allPerms.add(p);
  }
  return groupByResource(Array.from(allPerms));
}

type SelectedRole =
  | { type: 'workspace'; name: WorkspaceRoleName }
  | { type: 'platform'; key: string }
  | { type: 'custom'; id: string };

const NAME_RE = /^[a-z][a-z0-9_]{2,59}$/;

const RolesPermissions: React.FC = () => {
  const params = useParams<{ workspace_id?: string }>();
  const workspaceId = params.workspace_id;
  const inWorkspace = Boolean(workspaceId);

  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const platformRole = getActorRole(token);
  const actorId = getActorId(token);
  const isPlatformOp = platformRole === 'platform_admin' || platformRole === 'platform_viewer';
  const isTenantAdmin = platformRole === 'tenant_admin';

  const { can } = useWorkspacePermissions(
    isPlatformOp || isTenantAdmin ? undefined : workspaceId,
    isPlatformOp || isTenantAdmin ? undefined : (actorId ?? undefined),
  );

  // roles:write is granted to workspace_administrator, tenant_admin, platform_admin
  const canManageRoles =
    inWorkspace && (platformRole === 'platform_admin' || isTenantAdmin || can('roles:write'));

  const queryClient = useQueryClient();

  const [selected, setSelected] = useState<SelectedRole>({ type: 'workspace', name: 'workspace_administrator' });
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<CustomRoleResponse | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<CustomRoleResponse | null>(null);

  const fixedPermissionsByResource = useMemo(buildFixedPermissionResources, []);

  // Fetch custom roles + known permissions when in workspace context
  const { data: customRoles = [] } = useQuery({
    queryKey: ['custom-roles', workspaceId],
    queryFn: () => listCustomRoles(workspaceId!),
    enabled: inWorkspace,
  });

  const { data: knownPermissions = [] } = useQuery({
    queryKey: ['known-permissions', workspaceId],
    queryFn: () => listKnownPermissions(workspaceId!),
    enabled: inWorkspace && canManageRoles,
  });

  const knownPermsByResource = useMemo(
    () => groupByResource(knownPermissions),
    [knownPermissions],
  );

  const deleteMutation = useMutation({
    mutationFn: (role: CustomRoleResponse) => deleteCustomRole(workspaceId!, role.id),
    onSuccess: (_void, role) => {
      queryClient.invalidateQueries({ queryKey: ['custom-roles', workspaceId] });
      if (selected.type === 'custom' && selected.id === role.id) {
        setSelected({ type: 'workspace', name: 'workspace_administrator' });
      }
      setConfirmDelete(null);
    },
  });

  const currentPermissions: ReadonlySet<string> | null = useMemo(() => {
    if (selected.type === 'workspace') return FIXED_ROLE_PERMISSIONS[selected.name];
    if (selected.type === 'custom') {
      const role = customRoles.find(r => r.id === selected.id);
      return role ? new Set(role.permissions) : null;
    }
    return null;
  }, [selected, customRoles]);

  const isPlatformSelected = selected.type === 'platform';
  const selectedPlatform = isPlatformSelected
    ? PLATFORM_ROLES.find(r => r.key === selected.key)
    : null;

  const selectedCustom = selected.type === 'custom'
    ? customRoles.find(r => r.id === selected.id) ?? null
    : null;

  // If selected custom role disappears (e.g., after delete), reset selection.
  useEffect(() => {
    if (selected.type === 'custom' && !customRoles.find(r => r.id === selected.id)) {
      setSelected({ type: 'workspace', name: 'workspace_administrator' });
    }
  }, [customRoles, selected]);

  const openCreate = () => {
    setEditing(null);
    setEditorOpen(true);
  };
  const openEdit = (role: CustomRoleResponse) => {
    setEditing(role);
    setEditorOpen(true);
  };

  const onSaved = (role: CustomRoleResponse) => {
    queryClient.invalidateQueries({ queryKey: ['custom-roles', workspaceId] });
    setEditorOpen(false);
    setSelected({ type: 'custom', id: role.id });
  };

  const matrixResources = selected.type === 'custom'
    ? knownPermsByResource
    : fixedPermissionsByResource;

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">Roles & Permissions</h1>
          <p className="text-gray-400">
            {inWorkspace
              ? 'View built-in roles and manage custom roles for this workspace.'
              : 'View the fixed role-based access control matrix for workspace and platform roles.'}
          </p>
        </div>
        {canManageRoles && (
          <button
            onClick={openCreate}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 text-white font-medium shadow-lg shadow-purple-900/30 transition-all"
          >
            <Plus className="w-4 h-4" /> Create Role
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Role list */}
        <div className="lg:col-span-1 space-y-4">
          {/* Platform roles */}
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              <Crown className="w-4 h-4" /> Platform Roles
            </h2>
            <div className="space-y-2">
              {PLATFORM_ROLES.map(role => {
                const isActive = selected.type === 'platform' && selected.key === role.key;
                return (
                  <button
                    key={role.key}
                    onClick={() => setSelected({ type: 'platform', key: role.key })}
                    className={`w-full text-left p-3 rounded-lg transition-colors ${
                      isActive
                        ? 'bg-gradient-to-r from-purple-600 to-blue-600 text-white'
                        : 'bg-gray-750 text-gray-300 hover:bg-gray-700'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Crown className="w-4 h-4 shrink-0" />
                      <span className="font-medium">{role.label}</span>
                    </div>
                    <p className="text-xs mt-1 opacity-70">{role.scope}</p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Workspace roles */}
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              <Boxes className="w-4 h-4" /> Workspace Roles
            </h2>
            <div className="space-y-2">
              {ALL_ROLE_NAMES.map(name => {
                const isActive = selected.type === 'workspace' && selected.name === name;
                const perms = FIXED_ROLE_PERMISSIONS[name];
                return (
                  <button
                    key={name}
                    onClick={() => setSelected({ type: 'workspace', name })}
                    className={`w-full text-left p-3 rounded-lg transition-colors ${
                      isActive
                        ? 'bg-gradient-to-r from-purple-600 to-blue-600 text-white'
                        : 'bg-gray-750 text-gray-300 hover:bg-gray-700'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Shield className="w-4 h-4 shrink-0" />
                      <span className="font-medium">{ROLE_DISPLAY_NAMES[name]}</span>
                    </div>
                    <p className="text-xs mt-1 opacity-70">{perms.size} permissions</p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Custom roles (workspace-scoped only) */}
          {inWorkspace && (
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-2">
                  <Sparkles className="w-4 h-4" /> Custom Roles
                </h2>
                {canManageRoles && (
                  <button
                    onClick={openCreate}
                    className="p-1 rounded text-gray-400 hover:text-white hover:bg-gray-700"
                    title="Create role"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                )}
              </div>
              {customRoles.length === 0 ? (
                <p className="text-xs text-gray-500 italic">
                  No custom roles yet.
                  {canManageRoles && ' Click + to create one.'}
                </p>
              ) : (
                <div className="space-y-2">
                  {customRoles.map(role => {
                    const isActive = selected.type === 'custom' && selected.id === role.id;
                    return (
                      <div
                        key={role.id}
                        className={`group flex items-center gap-1 rounded-lg transition-colors ${
                          isActive
                            ? 'bg-gradient-to-r from-purple-600 to-blue-600 text-white'
                            : 'bg-gray-750 text-gray-300 hover:bg-gray-700'
                        }`}
                      >
                        <button
                          onClick={() => setSelected({ type: 'custom', id: role.id })}
                          className="flex-1 text-left p-3 min-w-0"
                        >
                          <div className="flex items-center gap-2">
                            <Sparkles className="w-4 h-4 shrink-0" />
                            <span className="font-medium truncate">{role.display_name}</span>
                          </div>
                          <p className="text-xs mt-1 opacity-70 truncate">
                            {role.permissions.length} permissions · <code>{role.name}</code>
                          </p>
                        </button>
                        {canManageRoles && (
                          <div className="flex items-center pr-2 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button
                              onClick={(e) => { e.stopPropagation(); openEdit(role); }}
                              className="p-1.5 rounded hover:bg-black/20"
                              title="Edit"
                            >
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); setConfirmDelete(role); }}
                              className="p-1.5 rounded hover:bg-black/20"
                              title="Delete"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right: Permission detail */}
        <div className="lg:col-span-2">
          {isPlatformSelected && selectedPlatform ? (
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
              <div className="mb-6">
                <div className="flex items-center gap-3 mb-2">
                  <Crown className="w-6 h-6 text-yellow-400" />
                  <h2 className="text-2xl font-semibold text-white">{selectedPlatform.label}</h2>
                </div>
                <p className="text-gray-400">{selectedPlatform.description}</p>
                <div className="flex items-center gap-4 mt-3">
                  <span className="px-3 py-1 text-xs bg-yellow-900/50 text-yellow-300 rounded">
                    Platform Scope
                  </span>
                  <span className="px-3 py-1 text-xs bg-green-900/50 text-green-300 rounded">
                    System Role
                  </span>
                </div>
              </div>

              <h3 className="text-lg font-semibold text-white mb-4">Access Details</h3>
              <div className="border border-gray-700 rounded-lg p-4 space-y-3">
                <div className="flex items-start gap-3">
                  <CheckCircle className="w-5 h-5 text-green-400 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-white font-medium">Tenant Management</p>
                    <p className="text-sm text-gray-400">
                      {selectedPlatform.key === 'platform_admin'
                        ? 'Create, edit, and manage tenants across the platform.'
                        : 'View all tenants (read-only).'}
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <CheckCircle className="w-5 h-5 text-green-400 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-white font-medium">Cross-Workspace Read Access</p>
                    <p className="text-sm text-gray-400">
                      Can access any workspace's data, issues, audit logs, and reports in read-only mode
                      without needing a workspace role assignment.
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  {selectedPlatform.key === 'platform_admin' ? (
                    <CheckCircle className="w-5 h-5 text-green-400 mt-0.5 shrink-0" />
                  ) : (
                    <XCircle className="w-5 h-5 text-gray-500 mt-0.5 shrink-0" />
                  )}
                  <div>
                    <p className={`font-medium ${selectedPlatform.key === 'platform_admin' ? 'text-white' : 'text-gray-500'}`}>
                      Workspace Write Operations
                    </p>
                    <p className="text-sm text-gray-400">
                      {selectedPlatform.key === 'platform_admin'
                        ? 'Platform admins can also create workspaces and manage platform-level settings.'
                        : 'Platform viewers cannot write to workspace data. Write operations require a workspace role.'}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ) : currentPermissions ? (
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
              <div className="mb-6">
                <div className="flex items-center justify-between gap-3 mb-2">
                  <div className="flex items-center gap-3">
                    {selected.type === 'custom' ? (
                      <Sparkles className="w-6 h-6 text-pink-400" />
                    ) : (
                      <Shield className="w-6 h-6 text-purple-400" />
                    )}
                    <h2 className="text-2xl font-semibold text-white">
                      {selected.type === 'workspace' ? ROLE_DISPLAY_NAMES[selected.name]
                        : selectedCustom?.display_name}
                    </h2>
                  </div>
                  {selected.type === 'custom' && selectedCustom && canManageRoles && (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => openEdit(selectedCustom)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-sm bg-gray-700 hover:bg-gray-600 text-gray-200"
                      >
                        <Pencil className="w-3.5 h-3.5" /> Edit
                      </button>
                      <button
                        onClick={() => setConfirmDelete(selectedCustom)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-sm bg-red-900/50 hover:bg-red-900/80 text-red-200"
                      >
                        <Trash2 className="w-3.5 h-3.5" /> Delete
                      </button>
                    </div>
                  )}
                </div>
                <p className="text-gray-400">
                  {selected.type === 'workspace' ? ROLE_DESCRIPTIONS[selected.name]
                    : (selectedCustom?.description || 'No description.')}
                </p>
                <div className="flex items-center gap-4 mt-3 flex-wrap">
                  <span className="px-3 py-1 text-xs bg-purple-900/50 text-purple-300 rounded">
                    Workspace Scope
                  </span>
                  <span className={`px-3 py-1 text-xs rounded ${
                    selected.type === 'custom'
                      ? 'bg-pink-900/50 text-pink-300'
                      : 'bg-green-900/50 text-green-300'
                  }`}>
                    {selected.type === 'custom' ? 'Custom Role' : 'System Role'}
                  </span>
                  {selected.type === 'custom' && selectedCustom && (
                    <span className="px-2 py-1 text-xs bg-gray-900 text-gray-300 rounded font-mono">
                      {selectedCustom.name}
                    </span>
                  )}
                  <span className="text-xs text-gray-500">
                    {currentPermissions.size} permissions
                  </span>
                </div>
              </div>

              <h3 className="text-lg font-semibold text-white mb-4">Permission Matrix</h3>
              <div className="space-y-4">
                {Object.entries(matrixResources).map(([resource, perms]) => (
                  <div key={resource} className="border border-gray-700 rounded-lg p-4">
                    <h4 className="text-white font-medium mb-3 capitalize">{resource}</h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {perms.map(perm => {
                        const has = currentPermissions.has(perm);
                        return (
                          <div
                            key={perm}
                            className={`flex items-center gap-2 px-3 py-2 rounded ${
                              has
                                ? 'bg-green-900/30 border border-green-700/50'
                                : 'bg-gray-750 border border-gray-700'
                            }`}
                          >
                            {has ? (
                              <CheckCircle className="w-4 h-4 text-green-400 shrink-0" />
                            ) : (
                              <XCircle className="w-4 h-4 text-gray-500 shrink-0" />
                            )}
                            <span className={`text-sm ${has ? 'text-green-300' : 'text-gray-500'}`}>
                              {perm}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* Editor modal */}
      {editorOpen && workspaceId && (
        <RoleEditorModal
          workspaceId={workspaceId}
          editing={editing}
          knownPermissions={knownPermissions}
          knownPermsByResource={knownPermsByResource}
          onClose={() => setEditorOpen(false)}
          onSaved={onSaved}
        />
      )}

      {/* Delete confirmation */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 max-w-md w-full">
            <h3 className="text-xl font-semibold text-white mb-2">Delete custom role?</h3>
            <p className="text-gray-400 mb-4">
              You're about to delete <strong className="text-white">{confirmDelete.display_name}</strong>.
              This cannot be undone.
            </p>
            {deleteMutation.isError && (
              <div className="bg-red-900/40 border border-red-700 text-red-200 text-sm p-3 rounded mb-4">
                {(deleteMutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
                  || 'Failed to delete role.'}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirmDelete(null)}
                className="px-4 py-2 rounded bg-gray-700 hover:bg-gray-600 text-gray-200"
                disabled={deleteMutation.isPending}
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate(confirmDelete)}
                disabled={deleteMutation.isPending}
                className="inline-flex items-center gap-2 px-4 py-2 rounded bg-red-600 hover:bg-red-500 text-white disabled:opacity-50"
              >
                {deleteMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Editor modal
// ─────────────────────────────────────────────────────────────────────────────

interface RoleEditorModalProps {
  workspaceId: string;
  editing: CustomRoleResponse | null;
  knownPermissions: string[];
  knownPermsByResource: Record<string, string[]>;
  onClose: () => void;
  onSaved: (role: CustomRoleResponse) => void;
}

const RoleEditorModal: React.FC<RoleEditorModalProps> = ({
  workspaceId, editing, knownPermissions, knownPermsByResource, onClose, onSaved,
}) => {
  const isEdit = Boolean(editing);
  const [name, setName] = useState(editing?.name ?? '');
  const [displayName, setDisplayName] = useState(editing?.display_name ?? '');
  const [description, setDescription] = useState(editing?.description ?? '');
  const [perms, setPerms] = useState<Set<string>>(
    new Set(editing?.permissions ?? []),
  );
  const [error, setError] = useState<string | null>(null);

  const togglePerm = (p: string) => {
    setPerms(prev => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p); else next.add(p);
      return next;
    });
  };

  const toggleResource = (_resource: string, all: string[]) => {
    setPerms(prev => {
      const next = new Set(prev);
      const hasAll = all.every(p => next.has(p));
      if (hasAll) all.forEach(p => next.delete(p));
      else all.forEach(p => next.add(p));
      return next;
    });
  };

  const mutation = useMutation({
    mutationFn: async () => {
      if (isEdit && editing) {
        return updateCustomRole(workspaceId, editing.id, {
          display_name: displayName,
          description: description || null,
          permissions: Array.from(perms),
        });
      }
      return createCustomRole(workspaceId, {
        name,
        display_name: displayName,
        description: description || null,
        permissions: Array.from(perms),
      });
    },
    onSuccess: (role) => onSaved(role),
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || 'Failed to save role.');
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!isEdit && !NAME_RE.test(name)) {
      setError('Name must start with a lowercase letter and contain 3-60 chars (a-z, 0-9, _).');
      return;
    }
    if (!displayName.trim()) {
      setError('Display name is required.');
      return;
    }
    if (perms.size === 0) {
      setError('Select at least one permission.');
      return;
    }
    mutation.mutate();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 overflow-y-auto">
      <form
        onSubmit={submit}
        className="bg-gray-800 border border-gray-700 rounded-lg max-w-3xl w-full my-8 max-h-[90vh] flex flex-col"
      >
        <div className="flex items-center justify-between p-6 border-b border-gray-700 shrink-0">
          <div className="flex items-center gap-3">
            <Sparkles className="w-6 h-6 text-pink-400" />
            <h2 className="text-2xl font-semibold text-white">
              {isEdit ? 'Edit Custom Role' : 'Create Custom Role'}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded hover:bg-gray-700 text-gray-400 hover:text-white"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4 overflow-y-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Slug (name)</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={isEdit}
                placeholder="qa_reviewer"
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white placeholder-gray-500 disabled:opacity-50 disabled:cursor-not-allowed font-mono"
                required={!isEdit}
              />
              <p className="text-xs text-gray-500 mt-1">
                Lowercase, digits, underscores. 3-60 chars. Cannot be changed after creation.
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Display name</label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="QA Reviewer"
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white placeholder-gray-500"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Description</label>
            <textarea
              value={description ?? ''}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="What can this role do?"
              className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white placeholder-gray-500"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-gray-300">
                Permissions <span className="text-gray-500">({perms.size} selected)</span>
              </label>
            </div>
            <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
              {Object.entries(knownPermsByResource).map(([resource, list]) => {
                const allSelected = list.every(p => perms.has(p));
                const someSelected = list.some(p => perms.has(p));
                return (
                  <div key={resource} className="border border-gray-700 rounded-lg p-3 bg-gray-900/40">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-white font-medium capitalize">{resource}</h4>
                      <button
                        type="button"
                        onClick={() => toggleResource(resource, list)}
                        className={`text-xs px-2 py-1 rounded ${
                          allSelected
                            ? 'bg-purple-700 text-white'
                            : someSelected
                              ? 'bg-purple-900/50 text-purple-200'
                              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                        }`}
                      >
                        {allSelected ? 'Unselect all' : 'Select all'}
                      </button>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {list.map(p => {
                        const has = perms.has(p);
                        return (
                          <button
                            type="button"
                            key={p}
                            onClick={() => togglePerm(p)}
                            className={`flex items-center gap-2 px-3 py-2 rounded text-left ${
                              has
                                ? 'bg-green-900/30 border border-green-700/50'
                                : 'bg-gray-750 border border-gray-700 hover:bg-gray-700'
                            }`}
                          >
                            {has ? (
                              <CheckCircle className="w-4 h-4 text-green-400 shrink-0" />
                            ) : (
                              <XCircle className="w-4 h-4 text-gray-500 shrink-0" />
                            )}
                            <span className={`text-sm ${has ? 'text-green-300' : 'text-gray-300'}`}>
                              {p}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
              {knownPermissions.length === 0 && (
                <p className="text-sm text-gray-500 italic">Loading permissions...</p>
              )}
            </div>
          </div>

          {error && (
            <div className="bg-red-900/40 border border-red-700 text-red-200 text-sm p-3 rounded">
              {error}
            </div>
          )}
        </div>

        <div className="p-6 border-t border-gray-700 flex justify-end gap-2 shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded bg-gray-700 hover:bg-gray-600 text-gray-200"
            disabled={mutation.isPending}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="inline-flex items-center gap-2 px-4 py-2 rounded bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 text-white font-medium disabled:opacity-50"
          >
            {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
            {isEdit ? 'Save changes' : 'Create role'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default RolesPermissions;
