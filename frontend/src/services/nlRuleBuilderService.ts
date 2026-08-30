import { api } from './api'
import type {
  ParseRuleRequest,
  ParseRuleResponse,
  ValidateParseRequest,
  ValidateParseResponse,
  SavedParsesListResponse,
  GenerateFlowFromParseResponse,
  TestPreviewResponse,
} from '@/types/nlRuleBuilder'
import type { ResolveRequest, ResolveResponse } from '@/types/resolution'

export async function parseRule(
  workspaceId: string,
  payload: ParseRuleRequest
): Promise<ParseRuleResponse> {
  const { data } = await api.post(
    `/workspaces/${workspaceId}/rule-builder/parse`,
    payload
  )
  return data
}

export async function resolveRule(
  workspaceId: string,
  payload: ResolveRequest
): Promise<ResolveResponse> {
  const { data } = await api.post(
    `/workspaces/${workspaceId}/rule-builder/resolve`,
    payload
  )
  return data
}

export async function listParses(
  workspaceId: string,
  page = 1,
  pageSize = 20,
  validatedOnly?: boolean
): Promise<SavedParsesListResponse> {
  const params: Record<string, unknown> = { page, page_size: pageSize }
  if (validatedOnly !== undefined) params.validated_only = validatedOnly
  const { data } = await api.get(
    `/workspaces/${workspaceId}/rule-builder/parses`,
    { params }
  )
  return data
}

export async function validateParse(
  workspaceId: string,
  parseResultId: string,
  payload: ValidateParseRequest
): Promise<ValidateParseResponse> {
  const { data } = await api.post(
    `/workspaces/${workspaceId}/rule-builder/parses/${parseResultId}/validate`,
    payload
  )
  return data
}

export async function createFlowFromParse(
  workspaceId: string,
  parseResultId: string,
  flowName?: string
): Promise<GenerateFlowFromParseResponse> {
  const params: Record<string, string> = {}
  if (flowName) params.flow_name = flowName
  const { data } = await api.post(
    `/workspaces/${workspaceId}/rule-builder/parses/${parseResultId}/create-flow`,
    null,
    { params }
  )
  return data
}

// E3 — test-on-sample
export async function testParseOnSample(
  workspaceId: string,
  parseResultId: string,
  options?: { check_index?: number; sample_size?: number; violation_limit?: number }
): Promise<TestPreviewResponse> {
  const params: Record<string, number> = {}
  if (options?.check_index !== undefined) params.check_index = options.check_index
  if (options?.sample_size !== undefined) params.sample_size = options.sample_size
  if (options?.violation_limit !== undefined) params.violation_limit = options.violation_limit
  const { data } = await api.post(
    `/workspaces/${workspaceId}/rule-builder/parses/${parseResultId}/test`,
    null,
    { params }
  )
  return data
}
