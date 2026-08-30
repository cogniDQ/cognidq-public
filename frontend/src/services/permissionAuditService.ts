/**
 * F008 — Permission Audit Visibility — API service
 *
 * Wraps the two F008 backend endpoints:
 *   GET /api/v1/workspaces/{workspace_id}/audit/permissions        → fetchEntries
 *   GET /api/v1/workspaces/{workspace_id}/audit/permissions/export → buildExportUrl
 *
 * The export URL is consumed by the Export CSV handler in PermissionAuditPage
 * which fetches it with fetch() + Blob to carry the Authorization header.
 */

import { api } from './api';
import type { PermissionAuditPage } from '../types/audit';

export interface AuditFilters {
  actor_id?: string;
  action_type?: string;
  target_entity_id?: string;
  target_entity_type?: string;
  from_date?: string;
  to_date?: string;
  sort_dir?: string;
}

const base = (workspaceId: string) =>
  `/workspaces/${workspaceId}/audit/permissions`;

/** Fetch a paginated page of permission audit entries. */
export async function fetchEntries(
  workspaceId: string,
  filters: AuditFilters = {},
  page = 1,
  pageSize = 25,
): Promise<PermissionAuditPage> {
  const params: Record<string, string | number | undefined> = {
    ...filters,
    page,
    page_size: pageSize,
  };
  const res = await api.get<PermissionAuditPage>(base(workspaceId), { params });
  return res.data;
}

/**
 * Build the absolute URL for the CSV export endpoint.
 * The caller must fetch this URL with the Authorization header; it must NOT
 * be used with window.location.href because auth is header-based.
 */
export function buildExportUrl(
  workspaceId: string,
  filters: AuditFilters = {},
): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== '') params.set(k, v);
  }
  const apiBase = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api/v1';
  const qs = params.toString();
  return `${apiBase}/workspaces/${workspaceId}/audit/permissions/export${qs ? `?${qs}` : ''}`;
}
