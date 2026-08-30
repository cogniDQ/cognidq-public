import { api } from './api'

// ── Types ──────────────────────────────────────────────────────────────────

export interface CanonicalRuleDefinition {
  dimension: string
  entity: string
  condition: string
  expectation: string
  severity: string
  parameters?: Record<string, unknown>
}

export interface ScheduleConfig {
  cron: string
  timezone?: string
  enabled?: boolean
}

export interface ThresholdConfig {
  pass_threshold?: number
  warning_threshold?: number
  blocker_threshold?: number
  max_violations?: number
}

export interface NotificationConfig {
  enabled?: boolean
  on_failure?: boolean
  on_success?: boolean
  recipients?: string[]
  channels?: string[]
}

export interface CreateRuleRequest {
  name: string
  description?: string
  category: string
  rule_type: string
  canonical_rule: CanonicalRuleDefinition
  data_source_id?: string
  target_schema?: string
  target_table?: string
  target_columns?: string[]
  status?: string
  is_active?: boolean
  schedule?: ScheduleConfig
  threshold_config?: ThresholdConfig
  notification_config?: NotificationConfig
  tags?: string[]
  metadata?: Record<string, unknown>
}

export interface UpdateRuleRequest {
  name?: string
  description?: string
  category?: string
  rule_type?: string
  canonical_rule?: CanonicalRuleDefinition
  data_source_id?: string
  target_schema?: string
  target_table?: string
  target_columns?: string[]
  status?: string
  is_active?: boolean
  schedule?: ScheduleConfig
  threshold_config?: ThresholdConfig
  notification_config?: NotificationConfig
  tags?: string[]
  metadata?: Record<string, unknown>
}

export interface RuleResponse {
  id: string
  workspace_id: string
  name: string
  description?: string
  category: string
  rule_type?: string
  canonical_rule: Record<string, unknown>
  compiled_sql?: string
  compiled_spark?: string
  data_source_id?: string
  target_schema?: string
  target_table?: string
  target_columns?: string[]
  status: string
  is_active: boolean
  schedule?: Record<string, unknown>
  threshold_config?: Record<string, unknown>
  notification_config?: Record<string, unknown>
  tags?: string[]
  metadata?: Record<string, unknown>
  created_by?: string
  updated_by?: string
  owner_user_id?: string | null
  created_at: string
  updated_at: string
}

// ── API Methods ────────────────────────────────────────────────────────────

export async function listRules(
  workspaceId: string,
  params?: {
    category?: string
    status?: string
    is_active?: boolean
    search?: string
    tags?: string[]
    data_source_id?: string
    skip?: number
    limit?: number
  }
): Promise<RuleResponse[]> {
  const { data } = await api.get(`/workspaces/${workspaceId}/rules`, { params })
  return data
}

export async function getRule(workspaceId: string, ruleId: string): Promise<RuleResponse> {
  const { data } = await api.get(`/workspaces/${workspaceId}/rules/${ruleId}`)
  return data
}

export async function createRule(workspaceId: string, payload: CreateRuleRequest): Promise<RuleResponse> {
  const { data } = await api.post(`/workspaces/${workspaceId}/rules`, payload)
  return data
}

export async function updateRule(workspaceId: string, ruleId: string, payload: UpdateRuleRequest): Promise<RuleResponse> {
  const { data } = await api.patch(`/workspaces/${workspaceId}/rules/${ruleId}`, payload)
  return data
}

export async function deleteRule(workspaceId: string, ruleId: string): Promise<void> {
  await api.delete(`/workspaces/${workspaceId}/rules/${ruleId}`)
}

export async function assignRuleOwner(
  workspaceId: string,
  ruleId: string,
  ownerUserId: string | null,
): Promise<{ rule_id: string; owner_user_id: string | null; previous_owner_user_id: string | null }> {
  const { data } = await api.put(
    `/workspaces/${workspaceId}/rules/${ruleId}/owner`,
    { owner_user_id: ownerUserId },
  )
  return data
}

// ── Executions ─────────────────────────────────────────────────────────────

export interface RuleExecutionResponse {
  id: string
  rule_id: string
  execution_type: string
  status: string
  started_at?: string | null
  completed_at?: string | null
  duration_seconds?: number | null
  rows_scanned: number
  rows_passed: number
  rows_failed: number
  pass_rate?: number | null
  error_message?: string | null
  error_details?: Record<string, unknown> | null
  result_details?: Record<string, unknown> | null
  execution_params?: Record<string, unknown> | null
  environment?: Record<string, unknown> | null
  executed_by?: string | null
  created_at: string
}

export async function getRuleExecutionHistory(
  workspaceId: string,
  ruleId: string,
  params?: { status?: string; skip?: number; limit?: number },
): Promise<RuleExecutionResponse[]> {
  const { data } = await api.get(
    `/workspaces/${workspaceId}/rules/${ruleId}/executions`,
    { params: { limit: 5, ...params } },
  )
  return data
}

export interface ExecuteRuleRequest {
  execution_type?: 'manual' | 'scheduled' | 'triggered' | 'test'
  parameters?: Record<string, unknown>
  sample_only?: boolean
  sample_size?: number
}

export async function executeRule(
  workspaceId: string,
  ruleId: string,
  payload: ExecuteRuleRequest = {},
): Promise<RuleExecutionResponse> {
  const { data } = await api.post(
    `/workspaces/${workspaceId}/rules/${ruleId}/execute`,
    { execution_type: 'manual', ...payload },
  )
  return data
}

// ── Violations (faulty records for a single execution) ─────────────────────

export interface ViolationResponse {
  id: string
  execution_id: string
  row_identifier?: string | null
  row_number?: number | null
  violation_details: Record<string, unknown>
  severity: string
  category?: string | null
  is_sample: boolean
  metadata?: Record<string, unknown> | null
  created_at: string
}

export async function getExecutionViolations(
  workspaceId: string,
  executionId: string,
  params?: { skip?: number; limit?: number },
): Promise<ViolationResponse[]> {
  const { data } = await api.get<ViolationResponse[]>(
    `/workspaces/${workspaceId}/executions/${executionId}/violations`,
    { params: { limit: 100, ...params } },
  )
  return data
}

export function downloadViolationsCsvUrl(
  workspaceId: string,
  executionId: string,
): string {
  return `/workspaces/${workspaceId}/executions/${executionId}/download-violations`
}

export async function buildFlowFromRules(
  workspaceId: string,
  ruleIds: string[],
  flowName?: string
): Promise<{ flow_id: string; flow_name: string; nodes: unknown[] }> {
  const { data } = await api.post(`/workspaces/${workspaceId}/rules/build-flow`, {
    rule_ids: ruleIds,
    flow_name: flowName,
  })
  return data
}
