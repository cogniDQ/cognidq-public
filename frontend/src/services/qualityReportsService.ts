/**
 * F083 — Quality Reports Page — API service
 *
 * Wraps the F050 backend report endpoints:
 *   GET /api/v1/workspaces/{workspace_id}/reports/issues/summary      — issue dashboard
 *   GET /api/v1/workspaces/{workspace_id}/reports/issues/by-status    — status counts
 *   GET /api/v1/workspaces/{workspace_id}/reports/issues/by-severity  — severity counts
 *   GET /api/v1/workspaces/{workspace_id}/reports/issues/export       — CSV export
 *   GET /api/v1/workspaces/{workspace_id}/reports/incidents/summary   — incident dashboard
 *   GET /api/v1/workspaces/{workspace_id}/reports/incidents/by-status — status counts
 *   GET /api/v1/workspaces/{workspace_id}/reports/incidents/export    — CSV export
 *
 * Permissions: issues:read (issue endpoints) / incidents:read (incident endpoints)
 */

import { api } from './api';

// ─────────────────────────────────────────────────────────────────────────────
// Issue report types (mirror F050 report_models.py)
// ─────────────────────────────────────────────────────────────────────────────

export interface IssueStatusCounts {
  open: number;
  resolved: number;
  closed: number;
}

export interface IssueSeverityCounts {
  critical: number;
  major: number;
  minor: number;
  info: number;
}

export interface ResolutionTimeStats {
  avg_hours: number;
  median_hours: number;
  p95_hours: number;
  total_resolved: number;
}

export interface IssueDashboardSummary {
  status_counts: IssueStatusCounts;
  severity_counts: IssueSeverityCounts;
  overdue_count: number;
  resolution_stats: ResolutionTimeStats;
}

// ─────────────────────────────────────────────────────────────────────────────
// Incident report types
// ─────────────────────────────────────────────────────────────────────────────

export interface IncidentStatusCounts {
  open: number;
  acknowledged: number;
  resolved: number;
  closed: number;
}

export interface IncidentSeverityCounts {
  critical: number;
  major: number;
  minor: number;
  info: number;
}

export interface IncidentPriorityCounts {
  p1: number;
  p2: number;
  p3: number;
  p4: number;
}

export interface IncidentDashboardSummary {
  status_counts: IncidentStatusCounts;
  severity_counts: IncidentSeverityCounts;
  priority_counts: IncidentPriorityCounts;
  sla_breach_count: number;
  resolution_stats: ResolutionTimeStats;
}

// ─────────────────────────────────────────────────────────────────────────────
// API calls
// ─────────────────────────────────────────────────────────────────────────────

export async function getIssueSummary(workspaceId: string): Promise<IssueDashboardSummary> {
  const res = await api.get<IssueDashboardSummary>(
    `/workspaces/${workspaceId}/reports/issues/summary`,
  );
  return res.data;
}

export async function getIncidentSummary(workspaceId: string): Promise<IncidentDashboardSummary> {
  const res = await api.get<IncidentDashboardSummary>(
    `/workspaces/${workspaceId}/reports/incidents/summary`,
  );
  return res.data;
}

/**
 * Build the absolute URL for the issues CSV export endpoint.
 * Must be fetched with Authorization header (not window.location.href).
 */
export function buildIssueExportUrl(workspaceId: string): string {
  const apiBase = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api/v1';
  return `${apiBase}/workspaces/${workspaceId}/reports/issues/export`;
}

/**
 * Build the absolute URL for the incidents CSV export endpoint.
 */
export function buildIncidentExportUrl(workspaceId: string): string {
  const apiBase = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api/v1';
  return `${apiBase}/workspaces/${workspaceId}/reports/incidents/export`;
}
