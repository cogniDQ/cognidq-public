/**
 * Tenant Members service — wraps GET /api/v1/tenants/{tenant_id}/members.
 */
import { api } from './api';

export interface TenantMemberAssignment {
  workspace_id: string;
  workspace_name: string;
  role_name: string;
  granted_at: string | null;
}

export interface TenantMember {
  user_id: string;
  email: string;
  full_name: string | null;
  platform_role: string | null;
  status: string | null;
  assignments: TenantMemberAssignment[];
}

export async function listTenantMembers(tenantId: string): Promise<TenantMember[]> {
  const { data } = await api.get(`/tenants/${tenantId}/members`);
  return data.data ?? [];
}
