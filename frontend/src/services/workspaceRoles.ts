/**
 * Workspace role management API service — F007
 *
 * Provides functions to:
 *   - Get a member's current workspace role
 *   - Assign / update a member's workspace role
 *   - Revoke a member's workspace role
 *   - Check the caller's permission for a specific action
 */
import { api } from './api';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export type WorkspaceRoleName =
  | 'workspace_administrator'
  | 'data_engineer'
  | 'data_steward'
  | 'business_analyst'
  | 'governance_viewer';

export interface RoleAssignmentResponse {
  workspace_id: string;
  user_id: string;
  role_name: WorkspaceRoleName;
  granted_by: string | null;
  granted_at: string;
}

export interface PermissionCheckResponse {
  allowed: boolean;
  role_name: WorkspaceRoleName | null;
  action: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Display name map (slug → human label)
// ─────────────────────────────────────────────────────────────────────────────

export const ROLE_DISPLAY_NAMES: Record<WorkspaceRoleName, string> = {
  workspace_administrator: 'Workspace Administrator',
  data_engineer: 'Data Engineer',
  data_steward: 'Data Steward',
  business_analyst: 'Business Analyst',
  governance_viewer: 'Governance Viewer',
};

export const ALL_ROLE_NAMES: WorkspaceRoleName[] = [
  'workspace_administrator',
  'data_engineer',
  'data_steward',
  'business_analyst',
  'governance_viewer',
];

// ─────────────────────────────────────────────────────────────────────────────
// Client-side permission map (must stay in sync with backend FIXED_ROLE_PERMISSIONS)
// ─────────────────────────────────────────────────────────────────────────────

export const FIXED_ROLE_PERMISSIONS: Record<WorkspaceRoleName, ReadonlySet<string>> = {
  workspace_administrator: new Set([
    'workspaces:read', 'workspaces:write',
    'members:read', 'members:write', 'members:delete',
    'roles:read', 'roles:assign',
    'datasources:read', 'datasources:write', 'datasources:delete', 'datasources:execute',
    'datasets:read', 'datasets:write', 'datasets:delete',
    'rules:read', 'rules:write', 'rules:execute', 'rules:delete',
    'executions:read', 'executions:write',
    'issues:read', 'issues:write',
    'incidents:read', 'incidents:write',
    'alerts:read', 'alerts:write',
    'reports:read',
    'settings:read', 'settings:write',
    'view_audit_logs',
  ]),
  data_engineer: new Set([
    'workspaces:read',
    'members:read', 'roles:read',
    'datasources:read', 'datasources:write', 'datasources:delete', 'datasources:execute',
    'datasets:read', 'datasets:write', 'datasets:delete',
    'rules:read', 'rules:write', 'rules:execute', 'rules:delete',
    'executions:read', 'executions:write',
    'issues:read', 'issues:write',
    'incidents:read', 'incidents:write',
    'alerts:read', 'alerts:write',
    'reports:read',
    'settings:read',
  ]),
  data_steward: new Set([
    'workspaces:read',
    'members:read', 'roles:read',
    'datasources:read',
    'datasets:read', 'datasets:write',
    'rules:read', 'rules:write', 'rules:execute',
    'executions:read',
    'issues:read', 'issues:write',
    'incidents:read', 'incidents:write',
    'alerts:read',
    'reports:read',
    'settings:read',
  ]),
  business_analyst: new Set([
    'workspaces:read',
    'members:read', 'roles:read',
    'datasets:read',
    'rules:read',
    'executions:read',
    'issues:read',
    'incidents:read',
    'reports:read',
  ]),
  governance_viewer: new Set([
    'workspaces:read',
    'members:read', 'roles:read',
    'datasources:read',
    'datasets:read',
    'rules:read',
    'executions:read',
    'issues:read',
    'incidents:read',
    'reports:read',
  ]),
};

// ─────────────────────────────────────────────────────────────────────────────
// API functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch the current workspace role for a specific member.
 * GET /workspaces/{workspace_id}/members/{user_id}/role
 */
export async function getMemberRole(
  workspaceId: string,
  userId: string,
): Promise<RoleAssignmentResponse> {
  const resp = await api.get<RoleAssignmentResponse>(
    `/workspaces/${workspaceId}/members/${userId}/role`,
  );
  return resp.data;
}

/**
 * Assign or update the workspace role for a member.
 * PUT /workspaces/{workspace_id}/members/{user_id}/role
 */
export async function assignMemberRole(
  workspaceId: string,
  userId: string,
  roleName: WorkspaceRoleName | string,
): Promise<RoleAssignmentResponse> {
  const resp = await api.put<RoleAssignmentResponse>(
    `/workspaces/${workspaceId}/members/${userId}/role`,
    { role_name: roleName },
  );
  return resp.data;
}

// ─────────────────────────────────────────────────────────────────────────────
// Custom workspace roles
// ─────────────────────────────────────────────────────────────────────────────

export interface CustomRoleResponse {
  id: string;
  workspace_id: string;
  name: string;
  display_name: string;
  description: string | null;
  permissions: string[];
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomRolesListResponse {
  workspace_id: string;
  roles: CustomRoleResponse[];
}

export interface CustomRoleCreateRequest {
  name: string;
  display_name: string;
  description?: string | null;
  permissions: string[];
}

export interface CustomRoleUpdateRequest {
  display_name?: string;
  description?: string | null;
  permissions?: string[];
}

export async function listCustomRoles(workspaceId: string): Promise<CustomRoleResponse[]> {
  const resp = await api.get<CustomRolesListResponse>(
    `/workspaces/${workspaceId}/custom-roles`,
  );
  return resp.data.roles;
}

export async function listKnownPermissions(workspaceId: string): Promise<string[]> {
  const resp = await api.get<{ permissions: string[] }>(
    `/workspaces/${workspaceId}/custom-roles/known-permissions`,
  );
  return resp.data.permissions;
}

export async function createCustomRole(
  workspaceId: string,
  payload: CustomRoleCreateRequest,
): Promise<CustomRoleResponse> {
  const resp = await api.post<CustomRoleResponse>(
    `/workspaces/${workspaceId}/custom-roles`,
    payload,
  );
  return resp.data;
}

export async function updateCustomRole(
  workspaceId: string,
  roleId: string,
  payload: CustomRoleUpdateRequest,
): Promise<CustomRoleResponse> {
  const resp = await api.put<CustomRoleResponse>(
    `/workspaces/${workspaceId}/custom-roles/${roleId}`,
    payload,
  );
  return resp.data;
}

export async function deleteCustomRole(workspaceId: string, roleId: string): Promise<void> {
  await api.delete(`/workspaces/${workspaceId}/custom-roles/${roleId}`);
}

/**
 * Revoke the workspace role from a member.
 * DELETE /workspaces/{workspace_id}/members/{user_id}/role
 */
export async function revokeMemberRole(
  workspaceId: string,
  userId: string,
): Promise<void> {
  await api.delete(`/workspaces/${workspaceId}/members/${userId}/role`);
}

/**
 * Check whether the authenticated caller has permission for *action*.
 * POST /workspaces/{workspace_id}/permissions/check
 */
export async function checkPermission(
  workspaceId: string,
  action: string,
): Promise<PermissionCheckResponse> {
  const resp = await api.post<PermissionCheckResponse>(
    `/workspaces/${workspaceId}/permissions/check`,
    { action },
  );
  return resp.data;
}
