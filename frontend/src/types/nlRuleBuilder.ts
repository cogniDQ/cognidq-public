// Types for NL Rule Builder (F100)
// Mirrors backend SIR schema from F099

export type RuleType =
  | 'null_check'
  | 'not_null'
  | 'empty_check'
  | 'placeholder_check'
  | 'multi_field_completeness'
  | 'conditional_completeness'
  | 'group_completeness'
  | 'population_completeness'
  | 'uniqueness'
  | 'composite_uniqueness'
  | 'scoped_uniqueness'
  | 'fuzzy_uniqueness'
  | 'temporal_uniqueness'
  | 'regex_format'
  | 'length_check'
  | 'case_check'
  | 'charset_check'
  | 'standard_format'
  | 'structural_pattern'
  | 'column_comparison'
  | 'formula_check'
  | 'temporal_consistency'
  | 'inter_record'
  | 'aggregation_consistency'
  | 'value_in_list'
  | 'numeric_range'
  | 'date_logic'
  | 'reference_lookup'
  | 'business_rule'
  | 'cross_field'
  | 'negative_pattern'
  | 'regex_validation'
  | 'reference_comparison'
  | 'tolerated_deviation'
  | 'statistical_outlier'
  | 'derived_value'
  | 'freshness'
  | 'record_age'
  | 'latency'
  | 'processing_delay'
  | 'delivery_window'
  | 'heartbeat'
  | 'record_count'
  | 'one_to_one'
  | 'field_level_recon'
  | 'aggregate_recon'
  | 'tolerance_recon'
  | 'missing_extra'
  // backward compat
  | 'date_comparison'
  | 'numeric_threshold'
  | 'conditional_rule'
  | 'arithmetic_comparison'
  | 'unknown'

export interface SIREntity {
  raw_text: string
  resolved_column?: string | null
  resolved_dataset?: string | null
  column_id?: string | null
  dataset_id?: string | null
}

export interface SIRCondition {
  field: SIREntity
  operator: string
  value?: unknown
}

export interface SIRScope {
  dataset_hint?: string | null
  domain_hint?: string | null
  source_system_hint?: string | null
}

export type ClarifyingAnswerType =
  | 'single_select'
  | 'multi_select'
  | 'free_text'
  | 'numeric'

export interface ClarifyingQuestion {
  field: string
  question: string
  options: string[]
  required: boolean
  /** E1 — typed clarifying questions */
  answer_type?: ClarifyingAnswerType
  min_value?: number | null
  max_value?: number | null
  rationale?: string | null
}

export interface StructuredIntermediateRepresentation {
  schema_version: string
  rule_type: RuleType
  subject: SIREntity
  operator?: string | null
  object?: SIREntity | null
  scope?: SIRScope
  conditions: SIRCondition[]
  constraints: unknown[]
  confidence: number
  requires_disambiguation: boolean
  parse_warnings: string[]
  clarifying_questions?: ClarifyingQuestion[]
  clarification_context?: string | null
  // F126 compound fields
  is_compound?: boolean
  obligation_logic?: string | null
  obligations?: StructuredIntermediateRepresentation[]
  inline_severity?: string | null
  threshold_pass?: number | null
  threshold_warn?: number | null
}

export interface ClarificationTurn {
  field: string
  question: string
  answer: string
  answered_at?: string | null
}

export interface ParseRuleRequest {
  rule_text: string
  dataset_id?: string
  domain?: string
  source_system?: string
  rule_category?: string
  severity?: 'critical' | 'high' | 'medium' | 'low' | 'info'
  tags?: string[]
  clarification_answers?: Record<string, string>
  /** F1 — multi-turn clarification history (oldest first) */
  clarification_history?: ClarificationTurn[]
}

// F125 — Explainability types
export interface ParseExplanationItem {
  topic: string
  decision: string
  evidence: string[]
  confidence_impact: number
  caveat?: string | null
}

export interface ParseTrustSummary {
  confidence_band: 'high' | 'medium' | 'low'
  confidence_score: number
  caveats: string[]
  assumptions: string[]
  recommendation: string
}

// F126 — Decomposition type
export interface DecompositionSummary {
  count: number
  logic: 'AND' | 'OR' | 'INDEPENDENT' | null
  obligations: string[]
}

export interface ParseRuleResponse {
  request_id: string
  parse_result_id?: string | null
  parsed_rule: StructuredIntermediateRepresentation | null
  status: 'parsed' | 'needs_clarification' | 'cannot_interpret' | 'parse_error'
  reason?: string | null
  suggestions: string[]
  clarifying_questions?: ClarifyingQuestion[]
  clarification_context?: string | null
  check_configs?: CheckConfigOutput[] | null
  detected_datasets?: DetectedDataset[] | null
  detected_columns?: DetectedColumn[] | null
  // F125 — Explainability
  explainability?: ParseExplanationItem[]
  trust_summary?: ParseTrustSummary | null
  // F126 — Decomposition
  decomposition_summary?: DecompositionSummary | null
  // NL Rule Builder Reliability spec §10/§11 — structured proposal contract.
  proposal_status?: 'valid_rule_proposal' | 'needs_refinement' | 'invalid_request' | null
  rule_proposal?: Record<string, unknown> | null
  validation?: ProposalValidation | null
  refinement?: RefinementGuidance | null
}

export type RefinementReason =
  | 'missing_dataset'
  | 'ambiguous_dataset'
  | 'unknown_dataset'
  | 'missing_column'
  | 'unknown_column'
  | 'ambiguous_column'
  | 'unsupported_check_type'
  | 'missing_threshold'
  | 'missing_allowed_values'
  | 'type_incompatible'
  | 'invalid_operator'
  | 'low_confidence'
  | 'unknown_intent'
  | 'invalid_rule_structure'

export interface RefinementSuggestion {
  type: string
  value: string
  label: string
  confidence?: number | null
  rationale?: string | null
}

export interface RefinementGuidance {
  reason: RefinementReason
  message: string
  suggestions?: RefinementSuggestion[]
  next_question?: string | null
  field?: string | null
}

export interface ProposalValidation {
  dataset_exists: boolean
  column_exists: boolean
  check_type_supported: boolean
  operator_supported: boolean
  type_compatible: boolean
  required_params_present: boolean
  dq_flow_convertible: boolean
  missing_fields: string[]
  incompatible_fields: string[]
  errors: string[]
}

export interface ThresholdConfig {
  threshold_pass: number
  threshold_warn: number
  null_handling: 'skip' | 'fail' | 'impute'
  include_empty_strings: boolean
}

export interface CheckConfigOutput {
  check_dimension: string
  check_subtype: string
  columns: string[]
  dataset_id?: string | null
  dataset_name?: string | null
  config: Record<string, unknown>
  thresholds: ThresholdConfig
  severity: string
  rule_name: string
  description?: string | null
}

export interface DetectedDataset {
  dataset_id?: string | null
  dataset_name: string
  data_source_name?: string | null
  match_score: number
  match_reason: string
}

export interface DetectedColumn {
  raw_text: string
  resolved_name?: string | null
  dataset_id?: string | null
  dataset_name?: string | null
  data_type?: string | null
  role: 'subject' | 'object' | 'condition' | 'scope'
}

export interface NLRuleDraft {
  rule_text: string
  dataset_id: string
  domain: string
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info'
  tags: string[]
  use_context: boolean
}

export interface RecentParseEntry {
  rule_text: string
  confidence: number
  rule_type: RuleType
  timestamp: string
}

export interface ValidateParseRequest {
  parse_result_id: string
  validated: boolean
  adjustments?: Record<string, unknown>
}

export interface ValidateParseResponse {
  parse_result_id: string
  validated: boolean
  validated_at: string
  check_configs: CheckConfigOutput[]
}

export interface SavedParseEntry {
  request_id: string
  parse_result_id: string
  rule_text: string
  rule_type: string
  confidence: number
  status: string
  validated: boolean
  check_configs?: CheckConfigOutput[] | null
  created_at: string
  validated_at?: string | null
}

export interface SavedParsesListResponse {
  items: SavedParseEntry[]
  total: number
  page: number
  page_size: number
}

// E3 — Test-on-sample response (mirrors backend TestPreviewResponse)
export interface TestStatistics {
  total_rows: number
  rows_passed: number
  rows_failed: number
  pass_rate: number
}

export interface TestPreviewResponse {
  status: 'success' | 'error' | string
  sample_data: Record<string, unknown>[]
  statistics?: TestStatistics | null
  violations: Record<string, unknown>[]
  expression?: string | null
  warnings: string[]
  error_message?: string | null
}

export const DEFAULT_DRAFT: NLRuleDraft = {
  rule_text: '',
  dataset_id: '',
  domain: '',
  severity: 'medium',
  tags: [],
  use_context: false,
}

export interface GeneratedFlowNode {
  node_id: string
  node_type: string
  label: string
}

export interface GeneratedFlowConnection {
  connection_id: string
  source_node: string
  target_node: string
}

export interface GenerateFlowFromParseResponse {
  flow_id: string
  flow_name: string
  status: string
  nodes: GeneratedFlowNode[]
  connections: GeneratedFlowConnection[]
  is_new_flow: boolean
}
