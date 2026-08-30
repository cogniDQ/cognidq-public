/**
 * API client for F002 workspace management endpoints.
 *
 * All calls go through the project-wide axios instance (`api`) which
 * automatically attaches the Bearer token from localStorage and handles
 * 401 by redirecting to /auth/login.
 */
import { api } from './api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type WorkspaceStatus = 'active' | 'archived';
export type SortBy = 'created_at' | 'updated_at';
export type SortDir = 'asc' | 'desc';

/** Summary shape returned by GET /api/v1/workspaces (list endpoint). */
export interface WorkspaceSummary {
  workspace_id: string;
  tenant_id?: string;
  tenant_name?: string | null;
  workspace_name: string;
  workspace_slug: string;
  status: WorkspaceStatus;
  default_timezone: string;
  created_at: string;
  updated_at: string;
}

export interface ListWorkspacesParams {
  include_archived?: boolean;
  q?: string;
  sort_by?: SortBy;
  sort_dir?: SortDir;
  page?: number;
  page_size?: number;
  /** Platform Admin/Viewer only — scope results to a specific tenant. */
  tenant_id?: string;
}

export interface ListWorkspacesResponse {
  data: WorkspaceSummary[];
  meta: {
    total: number;
    page: number;
    page_size: number;
    has_next: boolean;
  };
}

// ---------------------------------------------------------------------------
// Create Workspace
// ---------------------------------------------------------------------------

export interface CreateWorkspaceRequest {
  workspace_name: string;
  workspace_slug: string;
  description?: string | null;
  default_timezone?: string;
  /** Required for platform_admin callers whose JWT carries no tenant_id. */
  tenant_id?: string;
}

/** Full workspace object returned from POST /api/v1/workspaces (201 Created). */
export interface WorkspaceDetail {
  workspace_id: string;
  tenant_id: string;
  tenant_name?: string | null;
  workspace_name: string;
  workspace_slug: string;
  description: string | null;
  default_timezone: string;
  status: WorkspaceStatus;
  status_reason: string | null;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
}

export interface CreateWorkspaceResponse {
  data: WorkspaceDetail;
}

/** Structured API error field item from 422 responses. */
export interface ApiFieldError {
  field: string;
  reason: string;
}

/** Structured API error body shape returned on 4xx/5xx responses. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    fields: ApiFieldError[] | null;
  };
}

// ---------------------------------------------------------------------------
// API methods
// ---------------------------------------------------------------------------

/**
 * Fetch a paginated, filtered list of workspaces.
 * Undefined / empty-string parameters are stripped before building the request.
 */
export async function listWorkspaces(
  params: ListWorkspacesParams = {},
): Promise<ListWorkspacesResponse> {
  const query: Record<string, string | number | boolean> = {};

  if (params.include_archived != null) query.include_archived = params.include_archived;
  if (params.q) query.q = params.q;
  if (params.sort_by) query.sort_by = params.sort_by;
  if (params.sort_dir) query.sort_dir = params.sort_dir;
  if (params.page != null) query.page = params.page;
  if (params.page_size != null) query.page_size = params.page_size;
  if (params.tenant_id) query.tenant_id = params.tenant_id;

  const response = await api.get<ListWorkspacesResponse>('/workspaces', { params: query });
  return response.data;
}

// ---------------------------------------------------------------------------
// Workspace Detail (P11)
// ---------------------------------------------------------------------------

/** Full workspace shape extended with async-loaded count fields. */
export interface WorkspaceDetailWithCounts extends WorkspaceDetail {
  dataset_count: number | null;
  member_count: number | null;
}

/** Response shape from GET /workspaces/{id}. */
export interface GetWorkspaceResponse {
  data: WorkspaceDetailWithCounts;
  warnings?: Array<{ code: string; message: string }>;
}

// ---------------------------------------------------------------------------
// Update Workspace (P11)
// ---------------------------------------------------------------------------

export interface UpdateWorkspaceRequest {
  workspace_name?: string;
  description?: string | null;
  default_timezone?: string;
}

// ---------------------------------------------------------------------------
// Archive Workspace (P11)
// ---------------------------------------------------------------------------

export interface ArchiveWorkspaceRequest {
  status_reason: string;
  /** Only sent when re-confirming after a 409 last_active_workspace response. */
  confirm_last_workspace?: true;
}

/**
 * Create a new workspace. Returns the full workspace object on success (201).
 */
export async function createWorkspace(
  body: CreateWorkspaceRequest,
): Promise<CreateWorkspaceResponse> {
  const response = await api.post<CreateWorkspaceResponse>('/workspaces', body);
  return response.data;
}

// ---------------------------------------------------------------------------
// P11 API methods
// ---------------------------------------------------------------------------

/** Fetch the full detail of a single workspace by ID. */
export async function getWorkspace(id: string): Promise<GetWorkspaceResponse> {
  const response = await api.get<GetWorkspaceResponse>(`/workspaces/${id}`);
  return response.data;
}

/** Update editable workspace fields (workspace_name, description, default_timezone). */
export async function updateWorkspace(
  id: string,
  body: UpdateWorkspaceRequest,
): Promise<{ data: WorkspaceDetail }> {
  const response = await api.patch<{ data: WorkspaceDetail }>(`/workspaces/${id}`, body);
  return response.data;
}

/** Archive a workspace. Include confirm_last_workspace:true on second attempt after 409. */
export async function archiveWorkspace(
  id: string,
  body: ArchiveWorkspaceRequest,
): Promise<{ data: WorkspaceDetail }> {
  const response = await api.post<{ data: WorkspaceDetail }>(`/workspaces/${id}/archive`, body);
  return response.data;
}

/** Restore an archived workspace to active status. */
export async function restoreWorkspace(id: string): Promise<{ data: WorkspaceDetail }> {
  const response = await api.post<{ data: WorkspaceDetail }>(`/workspaces/${id}/restore`);
  return response.data;
}
