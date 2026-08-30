/**
 * Team API service
 */
import { api } from './api';

export interface TeamMember {
  user_id: string;
  email?: string;
  full_name?: string;
  role: string;
  joined_at: string;
}

export interface Team {
  id: string;
  domain_id: string;
  workspace_id: string;
  name: string;
  description?: string;
  slug: string;
  is_active: boolean;
  metadata?: Record<string, any>;
  created_by?: string;
  created_at: string;
  updated_at: string;
  members_count?: number;
  members?: TeamMember[];
}

export interface Domain {
  id: string;
  workspace_id: string;
  name: string;
  description?: string;
  slug: string;
  is_active: boolean;
  metadata?: Record<string, any>;
  created_by?: string;
  created_at: string;
  updated_at: string;
  teams_count?: number;
  teams?: Team[];
}

export interface TeamHierarchy {
  workspace_id: string;
  workspace_name: string;
  domains: Array<{
    id: string;
    name: string;
    slug: string;
    description?: string;
    teams: Array<{
      id: string;
      name: string;
      slug: string;
      description?: string;
      is_active: boolean;
    }>;
  }>;
}

export interface CreateDomainRequest {
  name: string;
  description?: string;
  slug?: string;
  metadata?: Record<string, any>;
}

export interface UpdateDomainRequest {
  name?: string;
  description?: string;
  slug?: string;
  is_active?: boolean;
  metadata?: Record<string, any>;
}

export interface CreateTeamRequest {
  domain_id: string;
  name: string;
  description?: string;
  slug?: string;
  metadata?: Record<string, any>;
}

export interface UpdateTeamRequest {
  name?: string;
  description?: string;
  slug?: string;
  is_active?: boolean;
  metadata?: Record<string, any>;
}

export interface AddTeamMemberRequest {
  user_id: string;
  role: string;
}

export interface UpdateTeamMemberRequest {
  role: string;
}

class TeamService {
  // Domain endpoints
  async createDomain(orgId: string, data: CreateDomainRequest): Promise<Domain> {
    const response = await api.post(`/workspaces/${orgId}/domains`, data);
    return response.data;
  }

  async getDomains(orgId: string): Promise<Domain[]> {
    const response = await api.get(`/workspaces/${orgId}/domains`);
    return response.data;
  }

  async getDomain(orgId: string, domainId: string): Promise<Domain> {
    const response = await api.get(`/workspaces/${orgId}/domains/${domainId}`);
    return response.data;
  }

  async updateDomain(orgId: string, domainId: string, data: UpdateDomainRequest): Promise<Domain> {
    const response = await api.patch(`/workspaces/${orgId}/domains/${domainId}`, data);
    return response.data;
  }

  async deleteDomain(orgId: string, domainId: string): Promise<void> {
    await api.delete(`/workspaces/${orgId}/domains/${domainId}`);
  }

  // Team endpoints
  async createTeam(orgId: string, data: CreateTeamRequest): Promise<Team> {
    const response = await api.post(`/workspaces/${orgId}/teams`, data);
    return response.data;
  }

  async getTeams(orgId: string, domainId?: string): Promise<Team[]> {
    const params = domainId ? { domain_id: domainId } : {};
    const response = await api.get(`/workspaces/${orgId}/teams`, { params });
    return response.data;
  }

  async getTeam(orgId: string, teamId: string): Promise<Team> {
    const response = await api.get(`/workspaces/${orgId}/teams/${teamId}`);
    return response.data;
  }

  async updateTeam(orgId: string, teamId: string, data: UpdateTeamRequest): Promise<Team> {
    const response = await api.patch(`/workspaces/${orgId}/teams/${teamId}`, data);
    return response.data;
  }

  async deleteTeam(orgId: string, teamId: string): Promise<void> {
    await api.delete(`/workspaces/${orgId}/teams/${teamId}`);
  }

  async getHierarchy(orgId: string): Promise<TeamHierarchy> {
    const response = await api.get(`/workspaces/${orgId}/teams/hierarchy`);
    return response.data;
  }

  // Team member endpoints
  async addMember(orgId: string, teamId: string, data: AddTeamMemberRequest): Promise<void> {
    await api.post(`/workspaces/${orgId}/teams/${teamId}/members`, data);
  }

  async getMembers(orgId: string, teamId: string): Promise<TeamMember[]> {
    const response = await api.get(`/workspaces/${orgId}/teams/${teamId}/members`);
    return response.data;
  }

  async updateMemberRole(orgId: string, teamId: string, userId: string, data: UpdateTeamMemberRequest): Promise<void> {
    await api.patch(`/workspaces/${orgId}/teams/${teamId}/members/${userId}`, data);
  }

  async removeMember(orgId: string, teamId: string, userId: string): Promise<void> {
    await api.delete(`/workspaces/${orgId}/teams/${teamId}/members/${userId}`);
  }
}

export default new TeamService();
