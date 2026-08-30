/**
 * API client for F003 workspace settings endpoints.
 */
import { api } from './api';
import type {
  WorkspaceSettingsResponse,
  WorkspaceSettingsUpdate,
} from '../types/workspaceSettings';

/**
 * GET /api/v1/workspaces/{workspaceId}/settings
 *
 * Returns the current settings for the given workspace.
 */
export async function getWorkspaceSettings(
  workspaceId: string,
): Promise<WorkspaceSettingsResponse> {
  const response = await api.get<WorkspaceSettingsResponse>(
    `/workspaces/${workspaceId}/settings`,
  );
  return response.data;
}

/**
 * PATCH /api/v1/workspaces/{workspaceId}/settings
 *
 * Partially updates workspace settings. Only the provided fields are changed.
 * Returns the full updated settings object.
 */
export async function updateWorkspaceSettings(
  workspaceId: string,
  update: WorkspaceSettingsUpdate,
): Promise<WorkspaceSettingsResponse> {
  const response = await api.patch<WorkspaceSettingsResponse>(
    `/workspaces/${workspaceId}/settings`,
    update,
  );
  return response.data;
}
