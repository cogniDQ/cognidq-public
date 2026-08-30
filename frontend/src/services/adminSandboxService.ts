/**
 * F134 P11 — Admin Sandbox Service
 *
 * Wraps admin /demo-requests, /admin/sandboxes endpoints.
 */
import { api } from './api';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AdminDemoRequest {
  id: string;
  status: string;
  first_name: string;
  last_name: string;
  email: string;
  company: string;
  use_case?: string;
  template_id?: string;
  created_at: string;
  reviewed_at?: string;
}

export interface AdminDemoRequestsResponse {
  items: AdminDemoRequest[];
  total: number;
  page: number;
  page_size: number;
}

export interface SandboxEnvironment {
  id: string;
  tenant_id: string;
  workspace_id?: string;
  status: string;
  expires_at?: string;
  engagement_score?: string;
  created_at: string;
  updated_at?: string;
}

export interface SandboxListResponse {
  items: SandboxEnvironment[];
  total: number;
}

export interface SandboxUsageSummary {
  summary: {
    total_events: number;
    engagement_score: string;
  };
  events_by_type: Array<{
    event_type: string;
    count: number;
    last_seen_at?: string;
  }>;
  timeline: Array<{
    day: string;
    count: number;
  }>;
}

export interface ExtendSandboxPayload {
  note: string;
  extra_days?: number;
}

export interface SuspendSandboxPayload {
  reason: string;
}

// ── Admin demo request operations ─────────────────────────────────────────────

export const listAdminDemoRequests = async (params?: {
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<AdminDemoRequestsResponse> => {
  const { data } = await api.get<AdminDemoRequestsResponse>('/admin/demo-requests', {
    params,
  });
  return data;
};

export const approveAdminDemoRequest = async (
  requestId: string,
  templateId?: string,
): Promise<void> => {
  await api.post(`/admin/demo-requests/${requestId}/approve`, {
    template_id: templateId,
  });
};

export const rejectAdminDemoRequest = async (
  requestId: string,
  reason: string,
): Promise<void> => {
  await api.post(`/admin/demo-requests/${requestId}/reject`, { reason });
};

// ── Admin sandbox operations ──────────────────────────────────────────────────

export const listAdminSandboxes = async (params?: {
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<SandboxListResponse> => {
  const { data } = await api.get<SandboxListResponse>('/admin/sandboxes', { params });
  return data;
};

export const getAdminSandbox = async (
  sandboxId: string,
): Promise<SandboxEnvironment> => {
  const { data } = await api.get<SandboxEnvironment>(`/admin/sandboxes/${sandboxId}`);
  return data;
};

export const extendSandbox = async (
  sandboxId: string,
  payload: ExtendSandboxPayload,
): Promise<void> => {
  await api.post(`/admin/sandboxes/${sandboxId}/extend`, payload);
};

export const suspendSandbox = async (
  sandboxId: string,
  payload: SuspendSandboxPayload,
): Promise<void> => {
  await api.post(`/admin/sandboxes/${sandboxId}/suspend`, payload);
};

export const archiveSandbox = async (sandboxId: string): Promise<void> => {
  await api.post(`/admin/sandboxes/${sandboxId}/archive`);
};

export const deleteSandbox = async (
  sandboxId: string,
  force = false,
): Promise<void> => {
  await api.delete(`/admin/sandboxes/${sandboxId}`, { params: { force } });
};

export const getSandboxUsage = async (
  sandboxId: string,
): Promise<SandboxUsageSummary> => {
  const { data } = await api.get<SandboxUsageSummary>(
    `/admin/sandboxes/${sandboxId}/usage`,
  );
  return data;
};
