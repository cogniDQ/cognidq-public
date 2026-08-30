/**
 * F082 — Activity Log Page — API service
 *
 * Wraps the two F053 backend endpoints:
 *   GET /api/v1/workspaces/{workspace_id}/audit/logs        → listAuditLogs
 *   GET /api/v1/workspaces/{workspace_id}/audit/logs/export → buildAuditLogExportUrl
 *
 * Permission required: view_audit_logs on the target workspace (workspace_administrator only).
 */

import { api } from './api';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface AuditLogEntry {
  log_id: string;
  occurred_at: string;
  action_type: string | null;
  actor_id: string | null;
  actor_display_name: string | null;
  actor_role: string | null;
  actor_type: string | null;
  target_entity_type: string | null;
  target_entity_id: string | null;
  workspace_id: string | null;
  request_id: string | null;
}

export interface AuditLogPage {
  items: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface AuditLogFilters {
  action_type?: string;
  entity_type?: string;
  actor_id?: string;
  from_date?: string;
  to_date?: string;
  sort_dir?: 'asc' | 'desc';
}

// ─────────────────────────────────────────────────────────────────────────────
// API calls
// ─────────────────────────────────────────────────────────────────────────────

/** Fetch a paginated page of workspace audit log entries. */
export async function listAuditLogs(
  workspaceId: string,
  filters: AuditLogFilters = {},
  page = 1,
  pageSize = 50,
): Promise<AuditLogPage> {
  const params: Record<string, string | number | undefined> = {
    ...filters,
    page,
    page_size: pageSize,
  };
  const res = await api.get<AuditLogPage>(`/workspaces/${workspaceId}/audit/logs`, { params });
  return res.data;
}

/**
 * Build the absolute URL for the CSV export endpoint.
 * The caller must fetch this URL with the Authorization header; window.location.href
 * must NOT be used because auth is header-based.
 */
export function buildAuditLogExportUrl(
  workspaceId: string,
  filters: AuditLogFilters = {},
): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== '' && k !== 'sort_dir') params.set(k, v as string);
  }
  const apiBase = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api/v1';
  const qs = params.toString();
  return `${apiBase}/workspaces/${workspaceId}/audit/logs/export${qs ? `?${qs}` : ''}`;
}
