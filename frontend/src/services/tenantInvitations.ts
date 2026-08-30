/**
 * Tenant Invitation service — wraps
 *   POST   /api/v1/tenants/{tenant_id}/invitations
 *   GET    /api/v1/tenants/{tenant_id}/invitations
 *   DELETE /api/v1/tenants/{tenant_id}/invitations/{invitation_id}
 *
 * Authorized for platform_admin and tenant_admin (backend enforces).
 */
import { api } from './api';

export type TenantInvitationRole =
  | 'workspace_administrator'
  | 'data_engineer'
  | 'data_steward'
  | 'business_analyst'
  | 'governance_viewer';

export interface TenantInvitation {
  invitation_id: string;
  tenant_id: string | null;
  workspace_id: string | null;
  email: string;
  role: TenantInvitationRole | null;
  status: string;
  expires_at: string | null;
  created_at: string | null;
  accepted_at: string | null;
  token?: string;
  acceptance_url?: string;
}

export interface CreateInvitationPayload {
  email: string;
  full_name?: string;
  workspace_id?: string;
  role_name?: TenantInvitationRole;
  expires_in_hours?: number;
}

export async function createTenantInvitation(
  tenantId: string,
  payload: CreateInvitationPayload,
): Promise<TenantInvitation> {
  const { data } = await api.post(`/tenants/${tenantId}/invitations`, payload);
  return data.data;
}

export async function listTenantInvitations(tenantId: string): Promise<TenantInvitation[]> {
  const { data } = await api.get(`/tenants/${tenantId}/invitations`);
  return data.data ?? [];
}

export async function revokeTenantInvitation(
  tenantId: string,
  invitationId: string,
): Promise<void> {
  await api.delete(`/tenants/${tenantId}/invitations/${invitationId}`);
}
