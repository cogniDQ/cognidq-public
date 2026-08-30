/**
 * Notification Events API service — F081
 *
 * Wraps F045 backend endpoints:
 *   GET /workspaces/{ws}/notification-events          — list events
 *   GET /workspaces/{ws}/notification-events/summary  — status counts
 */
import { api } from './api';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export type NotificationStatus = 'pending' | 'sent' | 'failed' | 'retrying';

export const NOTIFICATION_STATUSES: NotificationStatus[] = [
  'pending', 'sent', 'failed', 'retrying',
];

export const STATUS_LABELS: Record<NotificationStatus, string> = {
  pending:  'Pending',
  sent:     'Sent',
  failed:   'Failed',
  retrying: 'Retrying',
};

export interface NotificationEvent {
  id: string;
  workspace_id: string;
  alert_rule_id: string;
  alert_channel_id: string;
  recipient: string;
  status: NotificationStatus;
  payload: Record<string, unknown> | null;
  retry_count: number;
  max_retries: number;
  last_error: string | null;
  sent_at: string | null;
  delivered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotificationEventSummary {
  pending: number;
  sent: number;
  failed: number;
  retrying: number;
}

export interface ListNotificationEventsParams {
  status?: string;
  rule_id?: string;
  channel_id?: string;
  limit?: number;
  offset?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// API helpers
// ─────────────────────────────────────────────────────────────────────────────

function _token(): string {
  return localStorage.getItem('access_token') ?? '';
}

export async function listNotificationEvents(
  workspaceId: string,
  params: ListNotificationEventsParams = {},
): Promise<NotificationEvent[]> {
  const resp = await api.get(
    `/workspaces/${workspaceId}/notification-events`,
    {
      headers: { Authorization: `Bearer ${_token()}` },
      params: {
        ...(params.status     ? { status:     params.status }     : {}),
        ...(params.rule_id    ? { rule_id:    params.rule_id }    : {}),
        ...(params.channel_id ? { channel_id: params.channel_id } : {}),
        limit:  params.limit  ?? 100,
        offset: params.offset ?? 0,
      },
    },
  );
  return resp.data as NotificationEvent[];
}

export async function getNotificationEventSummary(
  workspaceId: string,
): Promise<NotificationEventSummary> {
  const resp = await api.get(
    `/workspaces/${workspaceId}/notification-events/summary`,
    { headers: { Authorization: `Bearer ${_token()}` } },
  );
  return resp.data as NotificationEventSummary;
}

// ─────────────────────────────────────────────────────────────────────────────
// F4 — Alerts dashboard KQI metrics
// ─────────────────────────────────────────────────────────────────────────────

export interface NotificationHourlyBucket {
  hour: string
  count: number
}

export interface NotificationTopFiringRule {
  rule_id: string
  name: string
  fired_count: number
  last_fired_at: string | null
}

export interface NotificationChannelHealth {
  channel_id: string
  name: string
  channel_type: string | null
  sent_count: number
  failed_count: number
  total_count: number
  success_pct: number
  last_success_at: string | null
  last_failure_at: string | null
}

export interface NotificationEventMetrics {
  window_hours: number
  since: string
  total: number
  status_counts: Partial<Record<NotificationStatus, number>>
  success_rate: number
  failure_rate: number
  retry_rate: number
  hourly_buckets: NotificationHourlyBucket[]
  top_firing_rules: NotificationTopFiringRule[]
  channel_health: NotificationChannelHealth[]
}

export async function getNotificationEventMetrics(
  workspaceId: string,
  params: { window_hours?: number; top_n?: number } = {},
): Promise<NotificationEventMetrics> {
  const resp = await api.get(
    `/workspaces/${workspaceId}/notification-events/metrics`,
    {
      headers: { Authorization: `Bearer ${_token()}` },
      params: {
        window_hours: params.window_hours ?? 24,
        top_n: params.top_n ?? 5,
      },
    },
  )
  return resp.data as NotificationEventMetrics
}
