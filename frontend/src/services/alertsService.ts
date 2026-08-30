/**
 * Alerts API service — F080
 *
 * Provides functions for:
 *   Alert Rules  (F043): list, create, update (toggle enabled), delete
 *   Alert Channels (F044): list, create, update (toggle enabled), delete
 */
import { api } from './api';

// ─────────────────────────────────────────────────────────────────────────────
// Alert Rules — Types & Constants
// ─────────────────────────────────────────────────────────────────────────────

export type AlertTriggerType =
  | 'execution_failed'
  | 'execution_completed'
  | 'issue_created'
  | 'issue_overdue'
  | 'incident_created'
  | 'incident_status_changed';

export const TRIGGER_TYPE_LABELS: Record<AlertTriggerType, string> = {
  execution_failed:        'Execution Failed',
  execution_completed:     'Execution Completed',
  issue_created:           'Issue Created',
  issue_overdue:           'Issue Overdue',
  incident_created:        'Incident Created',
  incident_status_changed: 'Incident Status Changed',
};

export const ALERT_TRIGGER_TYPES: AlertTriggerType[] = [
  'execution_failed',
  'execution_completed',
  'issue_created',
  'issue_overdue',
  'incident_created',
  'incident_status_changed',
];

export interface AlertRule {
  id: string;
  workspace_id: string;
  name: string;
  trigger_type: AlertTriggerType;
  conditions: Record<string, unknown> | null;
  recipient_user_ids: string[];
  channel_ids: string[];
  enabled: boolean;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateAlertRuleRequest {
  name: string;
  trigger_type: AlertTriggerType;
  conditions?: Record<string, unknown>;
  recipient_user_ids: string[];
  channel_ids?: string[];
  enabled?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Alert Channels — Types & Constants
// ─────────────────────────────────────────────────────────────────────────────

export type AlertChannelType = 'email' | 'webhook' | 'slack';

export const CHANNEL_TYPE_LABELS: Record<AlertChannelType, string> = {
  email:   'Email',
  webhook: 'Webhook',
  slack:   'Slack',
};

export interface AlertChannel {
  id: string;
  workspace_id: string;
  name: string;
  channel_type: AlertChannelType;
  configuration: Record<string, unknown>;
  enabled: boolean;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateAlertChannelRequest {
  name: string;
  channel_type: AlertChannelType;
  configuration?: Record<string, unknown>;
  enabled?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Alert Rule API functions
// ─────────────────────────────────────────────────────────────────────────────

function _token(): string {
  return localStorage.getItem('access_token') ?? '';
}

export async function listAlertRules(workspaceId: string): Promise<AlertRule[]> {
  const resp = await api.get(`/workspaces/${workspaceId}/alert-rules`, {
    headers: { Authorization: `Bearer ${_token()}` },
  });
  return resp.data as AlertRule[];
}

export async function createAlertRule(
  workspaceId: string,
  body: CreateAlertRuleRequest,
): Promise<AlertRule> {
  const resp = await api.post(`/workspaces/${workspaceId}/alert-rules`, body, {
    headers: { Authorization: `Bearer ${_token()}` },
  });
  return resp.data as AlertRule;
}

export async function updateAlertRule(
  workspaceId: string,
  ruleId: string,
  patch: Partial<CreateAlertRuleRequest>,
): Promise<AlertRule> {
  const resp = await api.patch(
    `/workspaces/${workspaceId}/alert-rules/${ruleId}`,
    patch,
    { headers: { Authorization: `Bearer ${_token()}` } },
  );
  return resp.data as AlertRule;
}

export async function deleteAlertRule(
  workspaceId: string,
  ruleId: string,
): Promise<void> {
  await api.delete(`/workspaces/${workspaceId}/alert-rules/${ruleId}`, {
    headers: { Authorization: `Bearer ${_token()}` },
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Alert Channel API functions
// ─────────────────────────────────────────────────────────────────────────────

export async function listAlertChannels(workspaceId: string): Promise<AlertChannel[]> {
  const resp = await api.get(`/workspaces/${workspaceId}/alert-channels`, {
    headers: { Authorization: `Bearer ${_token()}` },
  });
  return resp.data as AlertChannel[];
}

export async function createAlertChannel(
  workspaceId: string,
  body: CreateAlertChannelRequest,
): Promise<AlertChannel> {
  const resp = await api.post(`/workspaces/${workspaceId}/alert-channels`, body, {
    headers: { Authorization: `Bearer ${_token()}` },
  });
  return resp.data as AlertChannel;
}

export async function updateAlertChannel(
  workspaceId: string,
  channelId: string,
  patch: Partial<CreateAlertChannelRequest>,
): Promise<AlertChannel> {
  const resp = await api.patch(
    `/workspaces/${workspaceId}/alert-channels/${channelId}`,
    patch,
    { headers: { Authorization: `Bearer ${_token()}` } },
  );
  return resp.data as AlertChannel;
}

export async function deleteAlertChannel(
  workspaceId: string,
  channelId: string,
): Promise<void> {
  await api.delete(`/workspaces/${workspaceId}/alert-channels/${channelId}`, {
    headers: { Authorization: `Bearer ${_token()}` },
  });
}

/** F116 — Send a test notification through a channel */
export async function testAlertChannel(
  workspaceId: string,
  channelId: string,
): Promise<{ success: boolean; message?: string }> {
  const resp = await api.post(
    `/workspaces/${workspaceId}/alert-channels/${channelId}/test`,
    null,
    { headers: { Authorization: `Bearer ${_token()}` } },
  );
  return resp.data;
}

// ─────────────────────────────────────────────────────────────────────────────
// Notification Events
// ─────────────────────────────────────────────────────────────────────────────

export interface NotificationEventSummary {
  pending: number;
  sent: number;
  failed: number;
  retrying: number;
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
