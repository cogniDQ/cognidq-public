/**
 * Incidents API service — F079
 *
 * Provides functions to:
 *   - List workspace incidents (with filters + pagination)
 *   - Create a new incident
 *   - Update incident status / owner / resolution
 *   - Export incidents as CSV
 */
import { api } from './api';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export type IncidentStatus =
  | 'open'
  | 'acknowledged'
  | 'mitigated'
  | 'resolved'
  | 'closed'
  | 'reopened';

export type IncidentSeverity = 'critical' | 'major' | 'minor' | 'informational';
export type IncidentPriority = 'P1' | 'P2' | 'P3' | 'P4';

export interface IncidentListItem {
  id: string;
  title: string;
  severity: IncidentSeverity;
  priority: IncidentPriority;
  status: IncidentStatus;
  impact_summary: string | null;
  owner_id: string | null;
  owner_name: string | null;
  created_by_name: string | null;
  issue_count: number;
  has_sla_breach: boolean;
  earliest_due_at: string | null;
  opened_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
}

export interface IncidentListResponse {
  items: IncidentListItem[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface CreateIncidentRequest {
  title: string;
  severity: IncidentSeverity;
  priority: IncidentPriority;
  impact_summary?: string;
  owner_id?: string;
  issue_ids: string[];
}

export interface UpdateIncidentRequest {
  status?: IncidentStatus;
  owner_id?: string | null;
  impact_summary?: string;
  resolution_summary?: string;
}

export interface IncidentResponse {
  id: string;
  workspace_id: string;
  title: string;
  severity: IncidentSeverity;
  priority: IncidentPriority;
  status: IncidentStatus;
  impact_summary: string | null;
  resolution_summary: string | null;
  owner_id: string | null;
  owner_name: string | null;
  created_by_user_id: string | null;
  created_by_name: string | null;
  issue_count: number;
  opened_at: string;
}

export interface IncidentLinkedIssue {
  id: string;
  title: string;
  status: string;
  severity: string;
  dataset_name: string | null;
  rule_name: string | null;
  opened_at: string | null;
  due_at: string | null;
  assignee_id: string | null;
}

export interface IncidentActivityEntry {
  log_id: string;
  occurred_at: string | null;
  action_type: string;
  actor_id: string | null;
  actor_name: string | null;
  actor_role: string | null;
}

export interface IncidentDetailResponse {
  id: string;
  workspace_id: string;
  tenant_id: string;
  title: string;
  severity: IncidentSeverity;
  priority: IncidentPriority;
  status: IncidentStatus;
  impact_summary: string | null;
  resolution_summary: string | null;
  owner_id: string | null;
  owner_name: string | null;
  created_by_user_id: string | null;
  created_by_name: string | null;
  external_ticket_id: string | null;
  external_ticket_url: string | null;
  opened_at: string | null;
  acknowledged_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  updated_at: string | null;
  linked_issues: IncidentLinkedIssue[];
  activity: IncidentActivityEntry[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

export const INCIDENT_STATUSES: IncidentStatus[] = [
  'open', 'acknowledged', 'mitigated', 'resolved', 'closed', 'reopened',
];

export const ALLOWED_TRANSITIONS: Record<IncidentStatus, IncidentStatus[]> = {
  open:         ['acknowledged'],
  acknowledged: ['mitigated', 'resolved', 'closed'],
  mitigated:    ['resolved', 'closed'],
  resolved:     ['closed'],
  closed:       ['reopened'],
  reopened:     ['acknowledged', 'mitigated', 'resolved', 'closed'],
};

export const INCIDENT_SEVERITIES: IncidentSeverity[] = [
  'critical', 'major', 'minor', 'informational',
];

export const INCIDENT_PRIORITIES: IncidentPriority[] = ['P1', 'P2', 'P3', 'P4'];

// ─────────────────────────────────────────────────────────────────────────────
// API calls
// ─────────────────────────────────────────────────────────────────────────────

function authHeader() {
  const token = localStorage.getItem('access_token');
  return { Authorization: `Bearer ${token}` };
}

export async function listIncidents(
  workspaceId: string,
  params: {
    page?: number;
    page_size?: number;
    status?: string;
    severity?: string;
    priority?: string;
  } = {},
): Promise<IncidentListResponse> {
  const { data } = await api.get<IncidentListResponse>(
    `/workspaces/${workspaceId}/incidents`,
    { headers: authHeader(), params },
  );
  return data;
}

export async function createIncident(
  workspaceId: string,
  body: CreateIncidentRequest,
): Promise<IncidentResponse> {
  const { data } = await api.post<IncidentResponse>(
    `/workspaces/${workspaceId}/incidents`,
    body,
    { headers: authHeader() },
  );
  return data;
}

export async function updateIncident(
  workspaceId: string,
  incidentId: string,
  body: UpdateIncidentRequest,
): Promise<IncidentResponse> {
  const { data } = await api.patch<IncidentResponse>(
    `/workspaces/${workspaceId}/incidents/${incidentId}`,
    body,
    { headers: authHeader() },
  );
  return data;
}

export async function getIncidentDetail(
  workspaceId: string,
  incidentId: string,
): Promise<IncidentDetailResponse> {
  const { data } = await api.get<IncidentDetailResponse>(
    `/workspaces/${workspaceId}/incidents/${incidentId}`,
    { headers: authHeader() },
  );
  return data;
}

export async function exportIncidentsCsv(
  workspaceId: string,
  params: { status?: string; severity?: string; priority?: string } = {},
): Promise<void> {
  const token = localStorage.getItem('access_token');
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => Boolean(v)) as [string, string][],
  ).toString();
  const url = `${api.defaults.baseURL}/workspaces/${workspaceId}/incidents/export${query ? `?${query}` : ''}`;

  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new Error('Export failed');

  const blob = await res.blob();
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `incidents_export_${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}
