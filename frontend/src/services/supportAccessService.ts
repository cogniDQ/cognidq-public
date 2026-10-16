/**
 * Ephemeral support-access grants.
 *
 * Wraps:
 *   POST /tenants/{tenant_id}/support-access-grants
 *   GET  /tenants/{tenant_id}/support-access-grants
 *   POST /tenants/{tenant_id}/support-access-grants/{id}/revoke
 *   GET  /admin/support-access-grants/active
 */
import { api } from './api';

export interface SupportAccessGrant {
  id: string;
  tenant_id: string;
  workspace_id: string | null;
  granted_by_user_id: string;
  reason: string | null;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
  tenant_name?: string;
  workspace_name?: string | null;
}

export interface CreateGrantRequest {
  workspace_id?: string;
  duration_minutes: number;
  reason?: string;
}

export const createSupportAccessGrant = async (
  tenantId: string,
  body: CreateGrantRequest,
): Promise<SupportAccessGrant> => {
  const { data } = await api.post<{ data: SupportAccessGrant }>(
    `/tenants/${tenantId}/support-access-grants`,
    body,
  );
  return data.data;
};

export const listSupportAccessGrants = async (tenantId: string): Promise<SupportAccessGrant[]> => {
  const { data } = await api.get<{ data: SupportAccessGrant[] }>(
    `/tenants/${tenantId}/support-access-grants`,
  );
  return data.data;
};

export const revokeSupportAccessGrant = async (tenantId: string, grantId: string): Promise<void> => {
  await api.post(`/tenants/${tenantId}/support-access-grants/${grantId}/revoke`);
};

export const listActiveGrantsForAdmin = async (): Promise<SupportAccessGrant[]> => {
  const { data } = await api.get<{ data: SupportAccessGrant[] }>(
    '/admin/support-access-grants/active',
  );
  return data.data;
};
