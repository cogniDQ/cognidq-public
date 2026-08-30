/**
 * Flow Service - API client for Flow Builder operations
 */
import { api } from './api'

// ============================================================================
// ENUMS
// ============================================================================

export enum NodeType {
  SOURCE = 'source',
  CHECK = 'check',
  JOIN = 'join',
  FILTER = 'filter',
  AGGREGATE = 'aggregate',
  TRANSFORM = 'transform',
}

export enum FlowStatus {
  DRAFT = 'draft',
  ACTIVE = 'active',
  INACTIVE = 'inactive',
  ARCHIVED = 'archived',
}

export enum ExecutionStatus {
  PENDING = 'pending',
  RUNNING = 'running',
  COMPLETED = 'completed',
  WARNING = 'warning',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
}

export enum ExecutionTrigger {
  MANUAL = 'manual',
  SCHEDULED = 'scheduled',
  API = 'api',
}

// ============================================================================
// INTERFACES
// ============================================================================

export interface NodePosition {
  x: number
  y: number
}

export interface FlowNode {
  id: string
  type: NodeType
  label: string
  checkType?: string
  position: NodePosition
  config: Record<string, any>
}

export interface FlowConnection {
  id: string
  from: string
  to: string
  source_output?: string
  target_input?: string
}

export interface FlowDefinition {
  nodes: FlowNode[]
  connections: FlowConnection[]
  metadata?: Record<string, any>
}

export interface FlowSchedule {
  enabled: boolean
  cron_expression?: string
  timezone?: string
}

export interface Flow {
  id: string
  workspace_id: string
  name: string
  description?: string
  flow_definition: FlowDefinition
  status: FlowStatus
  created_by: string
  owner_user_id?: string | null
  created_at: string
  updated_at: string
  last_executed_at?: string
  schedule?: FlowSchedule
  tags?: string[]
  version: number
  execution_count: number
}

export interface FlowExecution {
  id: string
  flow_id: string
  flow_version: number
  status: ExecutionStatus
  trigger: ExecutionTrigger
  triggered_by?: string
  started_at?: string
  completed_at?: string
  duration_seconds?: number
  execution_time_seconds?: number  // alias kept for backward compat
  nodes_executed: number
  nodes_passed: number
  nodes_failed: number
  nodes_skipped: number
  result_summary?: Record<string, any>
  error_message?: string
  execution_config?: Record<string, any>
  // Enhanced fields from detail endpoint
  flow_name?: string
  executed_by_name?: string
}

export interface FlowNodeResult {
  id: string
  execution_id: string
  node_id: string
  status: ExecutionStatus
  execution_order: number
  started_at?: string
  completed_at?: string
  execution_time_seconds?: number
  result_data?: Record<string, any>
  error_message?: string
}

export interface FlowTemplate {
  id: string
  name: string
  description?: string
  category?: string
  template_definition: FlowDefinition
  preview_image_url?: string
  created_by: string
  created_at: string
  updated_at: string
  use_count: number
  is_public: boolean
  tags?: string[]
}

export interface ValidationError {
  node_id?: string
  connection_id?: string
  error_type: string
  message: string
}

export interface FlowValidationResponse {
  is_valid: boolean
  errors: ValidationError[]
  warnings: ValidationError[]
  execution_order?: string[]
}

// ============================================================================
// REQUEST/RESPONSE TYPES
// ============================================================================

export interface CreateFlowRequest {
  name: string
  description?: string
  flow_definition: FlowDefinition
  status?: FlowStatus
  schedule?: FlowSchedule
  tags?: string[]
}

export interface UpdateFlowRequest {
  name?: string
  description?: string
  flow_definition?: FlowDefinition
  status?: FlowStatus
  schedule?: FlowSchedule
  tags?: string[]
}

export interface ListFlowsParams {
  status?: FlowStatus
  tags?: string[]
  search?: string
  skip?: number
  limit?: number
}

export interface ExecuteFlowRequest {
  execution_config?: Record<string, any>
}

export interface ExportFlowRequest {
  format: 'json' | 'yaml'
  include_metadata?: boolean
}

export interface ImportFlowRequest {
  data: string
  format: 'json' | 'yaml'
}

export interface DuplicateFlowRequest {
  new_name: string
  copy_schedule?: boolean
}

// ============================================================================
// FLOW SERVICE CLASS
// ============================================================================

class FlowService {
  private baseUrl = '/workspaces'

  /**
   * Create a new flow
   */
  async createFlow(workspaceId: string, data: CreateFlowRequest): Promise<Flow> {
    const response = await api.post(`${this.baseUrl}/${workspaceId}/flows`, data)
    return response.data
  }

  /**
   * Get a flow by ID
   */
  async getFlow(workspaceId: string, flowId: string): Promise<Flow> {
    const response = await api.get(`${this.baseUrl}/${workspaceId}/flows/${flowId}`)
    return response.data
  }

  /**
   * List flows with optional filters
   */
  /**
   * List flows with optional filters
   */
  async listFlows(workspaceId: string, params?: ListFlowsParams): Promise<Flow[]> {
    const response = await api.get(`${this.baseUrl}/${workspaceId}/flows`, { params })
    // Backend returns { flows: [], total, page, page_size }
    return response.data.flows || []
  }

  /**
   * Update a flow
   */
  async updateFlow(
    workspaceId: string,
    flowId: string,
    data: UpdateFlowRequest
  ): Promise<Flow> {
    const response = await api.patch(`${this.baseUrl}/${workspaceId}/flows/${flowId}`, data)
    return response.data
  }

  /**
   * Delete a flow
   */
  async deleteFlow(workspaceId: string, flowId: string, hardDelete: boolean = true): Promise<void> {
    await api.delete(`${this.baseUrl}/${workspaceId}/flows/${flowId}?hard_delete=${hardDelete}`)
  }

  /**
   * Assign or clear the owner of a flow
   */
  async assignOwner(
    workspaceId: string,
    flowId: string,
    ownerUserId: string | null,
  ): Promise<{ flow_id: string; owner_user_id: string | null; previous_owner_user_id: string | null }> {
    const { data } = await api.put(
      `${this.baseUrl}/${workspaceId}/flows/${flowId}/owner`,
      { owner_user_id: ownerUserId },
    )
    return data
  }

  /**
   * Validate a flow definition
   */
  async validateFlow(
    workspaceId: string,
    flowDefinition: FlowDefinition
  ): Promise<FlowValidationResponse> {
    const response = await api.post(
      `${this.baseUrl}/${workspaceId}/flows/validate`,
      { flow_definition: flowDefinition }
    )
    return response.data
  }

  /**
   * Execute a flow
   */
  async executeFlow(
    workspaceId: string,
    flowId: string,
    config?: ExecuteFlowRequest
  ): Promise<FlowExecution> {
    const response = await api.post(
      `${this.baseUrl}/${workspaceId}/flows/${flowId}/execute`,
      config || {}
    )
    return response.data
  }

  /**
   * Get flow executions
   */
  async getFlowExecutions(
    workspaceId: string,
    flowId: string,
    limit?: number
  ): Promise<FlowExecution[]> {
    const response = await api.get(
      `${this.baseUrl}/${workspaceId}/flows/${flowId}/executions`,
      { params: { limit } }
    )
    // Backend returns { executions: [], total, page, page_size }
    return response.data.executions || []
  }

  /**
   * Get execution details
   */
  async getExecution(
    workspaceId: string,
    executionId: string
  ): Promise<FlowExecution> {
    const response = await api.get(
      `${this.baseUrl}/${workspaceId}/flow-executions/${executionId}`
    )
    return response.data
  }

  /**
   * List all executions for a workspace (across all flows)
   */
  async listAllExecutions(
    workspaceId: string,
    params?: { status?: string; page?: number; page_size?: number }
  ): Promise<FlowExecution[]> {
    const response = await api.get(
      `${this.baseUrl}/${workspaceId}/flow-executions`,
      { params }
    )
    return response.data.executions || []
  }

  /**
   * Get node results for an execution
   */
  async getNodeResults(
    workspaceId: string,
    executionId: string
  ): Promise<FlowNodeResult[]> {
    const response = await api.get(
      `${this.baseUrl}/${workspaceId}/flow-executions/${executionId}/nodes`
    )
    return response.data
  }

  /**
   * Cancel a running execution
   */
  async cancelExecution(workspaceId: string, executionId: string): Promise<void> {
    await api.delete(`${this.baseUrl}/${workspaceId}/flow-executions/${executionId}`)
  }

  /**
   * Export a flow
   */
  async exportFlow(
    workspaceId: string,
    flowId: string,
    format: 'json' | 'yaml' = 'json'
  ): Promise<string> {
    const response = await api.post(
      `${this.baseUrl}/${workspaceId}/flows/${flowId}/export`,
      { format },
      { responseType: 'text' }
    )
    return response.data
  }

  /**
   * Import a flow
   */
  async importFlow(
    workspaceId: string,
    data: string,
    format: 'json' | 'yaml' = 'json'
  ): Promise<Flow> {
    const response = await api.post(`${this.baseUrl}/${workspaceId}/flows/import`, {
      data,
      format,
    })
    return response.data
  }

  /**
   * Duplicate a flow
   */
  async duplicateFlow(
    workspaceId: string,
    flowId: string,
    newName: string,
    copySchedule: boolean = false
  ): Promise<Flow> {
    const response = await api.post(
      `${this.baseUrl}/${workspaceId}/flows/${flowId}/duplicate`,
      { new_name: newName, copy_schedule: copySchedule }
    )
    return response.data
  }

  /**
   * List flow templates
   */
  async listTemplates(workspaceId: string): Promise<FlowTemplate[]> {
    const response = await api.get(`${this.baseUrl}/${workspaceId}/templates`)
    return response.data
  }

  /**
   * Create flow from template
   */
  async createFromTemplate(
    workspaceId: string,
    templateId: string,
    flowName: string
  ): Promise<Flow> {
    const response = await api.post(
      `${this.baseUrl}/${workspaceId}/templates/${templateId}/create-flow`,
      { name: flowName }
    )
    return response.data
  }

  /**
   * AI-powered flow building from natural language prompts
   */
  async aiBuildFlow(
    workspaceId: string,
    prompt: string,
    currentFlow: { nodes: FlowNode[], connections: FlowConnection[] },
    availableDataSources?: any[]
  ): Promise<{
    success: boolean
    needs_clarification: boolean
    clarification_questions: string[]
    suggested_data_sources?: any[]
    pending_tasks?: any[]
    flow_updates: { nodes: FlowNode[], connections: FlowConnection[] } | null
    message: string
  }> {
    const response = await api.post(
      `${this.baseUrl}/${workspaceId}/flows/ai-build`,
      { 
        prompt, 
        current_flow: currentFlow,
        available_data_sources: availableDataSources || []
      }
    )
    return response.data
  }

  // ── F115 — Schedule Management ───────────────────────────────────

  async getSchedule(workspaceId: string, flowId: string) {
    const response = await api.get(`${this.baseUrl}/${workspaceId}/flows/${flowId}/schedule`)
    return response.data as { flow_id: string; schedule: FlowSchedule | null; next_run_at: string | null }
  }

  async setSchedule(workspaceId: string, flowId: string, schedule: { enabled: boolean; cron: string; timezone?: string }) {
    const response = await api.put(`${this.baseUrl}/${workspaceId}/flows/${flowId}/schedule`, schedule)
    return response.data
  }

  async removeSchedule(workspaceId: string, flowId: string) {
    const response = await api.delete(`${this.baseUrl}/${workspaceId}/flows/${flowId}/schedule`)
    return response.data
  }

  async listScheduledFlows(workspaceId: string) {
    const response = await api.get(`${this.baseUrl}/${workspaceId}/flows/schedules`)
    return response.data as { schedules: Array<{ flow_id: string; flow_name: string; schedule: FlowSchedule; next_run_at: string | null; status: string }>; total: number }
  }

  async validateCron(workspaceId: string, flowId: string, schedule: { enabled: boolean; cron: string; timezone?: string }) {
    const response = await api.post(`${this.baseUrl}/${workspaceId}/flows/${flowId}/schedule/validate`, schedule)
    return response.data as { valid: boolean; error?: string; next_runs: string[] }
  }
}

export default new FlowService()
