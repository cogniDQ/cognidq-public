// F031 P05 — TypeScript interfaces for Issues module

export type IssueSeverity = 'critical' | 'major' | 'minor' | 'informational'
export type IssueStatus = 'open' | 'in_progress' | 'resolved' | 'closed' | 'reopened'

export interface IssueListItem {
  id: string
  workspace_id: string
  issue_type: string
  severity: IssueSeverity
  status: IssueStatus
  title: string
  impact_summary: string | null
  failure_count: number | null
  due_at: string | null
  opened_at: string | null
  // F037 — denormalized triage fields
  assignee_id: string | null
  assignee_display_name: string | null
  dataset_name: string | null
  updated_at: string | null
}

export interface IssuePage {
  items: IssueListItem[]
  total: number
  page: number
  page_size: number
  has_next: boolean
}

export interface IssueDetail {
  id: string
  workspace_id: string
  tenant_id: string
  flow_execution_id: string
  flow_node_result_id: string | null
  rule_id: string | null
  dataset_id: string | null
  assignee_id: string | null
  issue_type: string
  severity: IssueSeverity
  status: IssueStatus
  title: string
  impact_summary: string | null
  resolution_summary: string | null
  failure_count: number | null
  rows_scanned: number | null
  pass_rate: number | null
  due_at: string | null
  opened_at: string | null
  resolved_at: string | null
  closed_at: string | null
  updated_at: string | null
  created_at: string | null
  // F033 — enriched context objects (null when referenced entity is missing)
  rule: RuleSummary | null
  dataset: DatasetSummary | null
  assignee: AssigneeSummary | null
  flow_execution: FlowExecutionSummary | null
  node_result: NodeResultSummary | null
}

// F033 — Context summary interfaces

export interface RuleSummary {
  id: string
  name: string
  category: string | null
  severity: string | null
  status: string | null
  target_table: string | null
  target_columns: string[] | null
}

export interface DatasetSummary {
  dataset_id: string
  dataset_name: string
  business_domain: string | null
  criticality: string | null
  status: string | null
}

export interface AssigneeSummary {
  id: string
  display_name: string
  email: string
}

export interface FlowExecutionSummary {
  id: string
  flow_name: string | null
  status: string | null
  started_at: string | null
  completed_at: string | null
  nodes_total: number | null
  nodes_passed: number | null
  nodes_failed: number | null
}

export interface NodeResultSummary {
  id: string
  node_id: string
  node_type: string | null
  status: string | null
  rows_scanned: number | null
  rows_passed: number | null
  rows_failed: number | null
  pass_rate: number | null
  // Sprint 4.2 — evidence fields
  check_type?: string | null
  dataset?: string | null
  table_name?: string | null
  schema_name?: string | null
  columns?: string[] | null
  threshold?: string | null
  violations?: Array<Record<string, unknown>> | null
  sample_data?: Array<Record<string, unknown>> | null
}

export type SortColumn = 'opened_at' | 'due_at' | 'severity' | 'status' | 'updated_at'
export type SortDir = 'asc' | 'desc'

export interface IssueListParams {
  page?: number
  page_size?: number
  status?: IssueStatus | ''
  severity?: IssueSeverity | ''
  // F037 — triage filters and sort
  assignee_id?: string
  dataset_id?: string
  overdue?: boolean
  sort_by?: SortColumn
  sort_dir?: SortDir
}

// F035 — Issue mutation types

export interface IssueUpdatePayload {
  status?: IssueStatus
  assignee_id?: string | null
  due_at?: string | null
  resolution_summary?: string | null
}

export const ALLOWED_TRANSITIONS: Record<IssueStatus, IssueStatus[]> = {
  open: ['in_progress', 'resolved', 'closed'],
  in_progress: ['open', 'resolved', 'closed'],
  resolved: ['closed', 'reopened'],
  closed: ['reopened'],
  reopened: ['in_progress', 'resolved', 'closed'],
}

export const RESOLUTION_REQUIRED_STATUSES: ReadonlySet<IssueStatus> = new Set(['resolved', 'closed'])
