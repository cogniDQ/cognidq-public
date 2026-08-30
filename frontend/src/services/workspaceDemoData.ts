/**
 * D4 — Workspace demo data bootstrap client.
 */
import { api } from './api';

export interface WorkspaceDemoDataStatus {
  workspace_id: string;
  template_id: string;
  seeded: boolean;
  sources: Record<string, number>;
}

export async function getWorkspaceDemoDataStatus(
  workspaceId: string,
): Promise<WorkspaceDemoDataStatus> {
  const response = await api.get<{ data: WorkspaceDemoDataStatus }>(
    `/workspaces/${workspaceId}/demo-data`,
  );
  return response.data.data;
}

export async function loadWorkspaceDemoData(
  workspaceId: string,
): Promise<WorkspaceDemoDataStatus> {
  const response = await api.post<{ data: WorkspaceDemoDataStatus }>(
    `/workspaces/${workspaceId}/demo-data/load`,
    {},
  );
  return response.data.data;
}
