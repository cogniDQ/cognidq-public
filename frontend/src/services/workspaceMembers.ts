/**
 * Workspace members API service — F078
 *
 * Provides functions to:
 *   - List all members of a workspace (with their roles)
 *   - Search for tenant users who are not yet workspace members
 */
import { api } from './api';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface WorkspaceMemberItem {
  user_id: string;
  email: string;
  display_name: string;
  role_name: string;
  granted_by: string | null;
  granted_at: string;
}

export interface WorkspaceMembersResponse {
  workspace_id: string;
  members: WorkspaceMemberItem[];
  total: number;
}

export interface UserSearchItem {
  user_id: string;
  email: string;
  display_name: string;
}

export interface UserSearchResponse {
  users: UserSearchItem[];
}

// ─────────────────────────────────────────────────────────────────────────────
// API calls
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch all members of a workspace with their role assignments.
 * Requires `members:read` permission in the workspace.
 */
export async function listWorkspaceMembers(
  workspaceId: string,
): Promise<WorkspaceMembersResponse> {
  const token = localStorage.getItem('access_token');
  const { data } = await api.get<WorkspaceMembersResponse>(
    `/workspaces/${workspaceId}/members`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  return data;
}

/**
 * Search for users within the same tenant who are NOT yet members of the workspace.
 * Requires `members:read` permission in the workspace.
 *
 * @param q - Email prefix search string (minimum 1 character)
 */
export async function searchNonMembers(
  workspaceId: string,
  q: string,
): Promise<UserSearchResponse> {
  const token = localStorage.getItem('access_token');
  const { data } = await api.get<UserSearchResponse>(
    `/workspaces/${workspaceId}/users/search`,
    {
      headers: { Authorization: `Bearer ${token}` },
      params: { q },
    },
  );
  return data;
}
