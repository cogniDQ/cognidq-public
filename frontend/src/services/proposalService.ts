import { api } from './api'

export interface ProposalPayload {
  parsed_rule: Record<string, unknown>
  resolved_rule: Record<string, unknown> | null
  compiled_checks: Record<string, unknown>[]
  glossary_matches: Record<string, unknown>[]
  resolution_evidence: Record<string, unknown>
  parse_confidence: number
  resolution_confidence: number
}

export interface ProposalAdjustment {
  field: string
  old_value?: unknown
  new_value?: unknown
  reason?: string
}

export interface Proposal {
  proposal_id: string
  workspace_id: string
  created_by: string | null
  status: 'pending' | 'confirmed' | 'rejected' | 'adjusted'
  original_prompt: string
  proposal_payload: ProposalPayload
  adjustments: ProposalAdjustment[]
  generated_flow_id: string | null
  confidence: number
  created_at: string
  updated_at: string
}

export interface ProposalListResponse {
  items: Proposal[]
  total: number
}

export async function createProposal(
  workspaceId: string,
  prompt: string,
  datasetContext?: string,
  domainContext?: string,
): Promise<Proposal> {
  const { data } = await api.post(`/proposals/workspaces/${workspaceId}/proposals`, {
    prompt,
    dataset_context: datasetContext,
    domain_context: domainContext,
  })
  return data
}

export async function listProposals(
  workspaceId: string,
  params?: { status?: string; limit?: number; offset?: number },
): Promise<ProposalListResponse> {
  const { data } = await api.get(`/proposals/workspaces/${workspaceId}/proposals`, { params })
  return data
}

export async function getProposal(workspaceId: string, proposalId: string): Promise<Proposal> {
  const { data } = await api.get(`/proposals/workspaces/${workspaceId}/proposals/${proposalId}`)
  return data
}

export async function confirmProposal(
  workspaceId: string,
  proposalId: string,
  adjustments: ProposalAdjustment[] = [],
  createFlow = false,
): Promise<Proposal> {
  const { data } = await api.post(
    `/proposals/workspaces/${workspaceId}/proposals/${proposalId}/confirm`,
    { adjustments, create_flow: createFlow },
  )
  return data
}

export async function rejectProposal(
  workspaceId: string,
  proposalId: string,
  reason?: string,
): Promise<Proposal> {
  const { data } = await api.post(
    `/proposals/workspaces/${workspaceId}/proposals/${proposalId}/reject`,
    { reason },
  )
  return data
}
