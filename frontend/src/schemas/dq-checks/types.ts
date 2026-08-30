/**
 * DQ Check Schema Registry — Shared Types
 * 
 * Core type definitions for the schema-driven check configuration system.
 * All dimension schemas extend these base types.
 */

// ─── Enums & Literals ─────────────────────────────────────────────

export type Severity = 'blocker' | 'critical' | 'high' | 'medium' | 'low'

export type NullHandling = 'fail' | 'skip' | 'pass'

export type Dimension =
  | 'completeness'
  | 'validity'
  | 'uniqueness'
  | 'conformity'
  | 'consistency'
  | 'timeliness'
  | 'accuracy'
  | 'reconciliation'

export const DIMENSIONS: Dimension[] = [
  'completeness', 'validity', 'uniqueness', 'conformity',
  'consistency', 'timeliness', 'accuracy', 'reconciliation',
]

export const SEVERITY_OPTIONS: { value: Severity; label: string }[] = [
  { value: 'blocker', label: 'Blocker' },
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
]

export const NULL_HANDLING_OPTIONS: { value: NullHandling; label: string; description: string }[] = [
  { value: 'fail', label: 'Fail', description: 'Null values count as failures' },
  { value: 'skip', label: 'Skip', description: 'Null values are excluded from evaluation' },
  { value: 'pass', label: 'Pass', description: 'Null values count as passing' },
]

// ─── Node Status ──────────────────────────────────────────────────

export type NodeStatus =
  | 'NO_SOURCE'
  | 'NOT_CONFIGURED'
  | 'PARTIALLY_CONFIGURED'
  | 'INVALID'
  | 'WARNING'
  | 'READY'

export const NODE_STATUS_COLORS: Record<NodeStatus, string> = {
  NO_SOURCE: 'border-dark-700',
  NOT_CONFIGURED: 'border-dark-700',
  PARTIALLY_CONFIGURED: 'border-yellow-500/50',
  INVALID: 'border-red-500/50',
  WARNING: 'border-orange-500/50',
  READY: 'border-green-500/50',
}

export const NODE_STATUS_BADGE: Record<NodeStatus, { symbol: string; color: string }> = {
  NO_SOURCE: { symbol: '○', color: 'text-gray-500' },
  NOT_CONFIGURED: { symbol: '○', color: 'text-gray-500' },
  PARTIALLY_CONFIGURED: { symbol: '◉', color: 'text-yellow-400' },
  INVALID: { symbol: '⚠', color: 'text-red-400' },
  WARNING: { symbol: '△', color: 'text-orange-400' },
  READY: { symbol: '✓', color: 'text-green-400' },
}

export const NODE_STATUS_TEXT: Record<NodeStatus, string> = {
  NO_SOURCE: 'Connect a data source first',
  NOT_CONFIGURED: 'Not configured — click to set up',
  PARTIALLY_CONFIGURED: 'Configuration incomplete',
  INVALID: 'Invalid configuration',
  WARNING: 'Valid with warnings',
  READY: 'Ready',
}

// ─── Input Types ──────────────────────────────────────────────────

export type InputType =
  | 'text'
  | 'number'
  | 'number-slider'
  | 'dropdown'
  | 'dropdown-searchable'
  | 'dropdown-with-descriptions'
  | 'multi-select'
  | 'column-picker'
  | 'tag-input'
  | 'key-pair-table'
  | 'duration'
  | 'time'
  | 'expression'
  | 'toggle'
  | 'radio'
  | 'readonly-chip'
  | 'dataset-picker'

// ─── Field Metadata ───────────────────────────────────────────────

export type SectionId =
  | 'general'
  | 'checkType'
  | 'targetScope'
  | 'businessLogic'
  | 'referenceData'
  | 'thresholds'
  | 'advanced'

export interface FieldOption {
  value: string
  label: string
  description?: string
}

export interface FieldMeta {
  key: string
  label: string
  helpText: string
  inputType: InputType
  required: boolean | ((config: Record<string, unknown>) => boolean)
  defaultValue: unknown
  section: SectionId
  visibleWhen?: (config: Record<string, unknown>) => boolean
  options?: FieldOption[]
  validation?: (value: unknown, config: Record<string, unknown>) => string | null
  min?: number
  max?: number
  placeholder?: string
}

// ─── Subtype & Dimension Schemas ──────────────────────────────────

export interface SubtypeSchema {
  subtype: string
  label: string
  description: string
  fields: FieldMeta[]
  requiresReferenceData: boolean
  defaultConfig: () => Record<string, unknown>
}

export interface DimensionSchema {
  dimension: Dimension
  subtypes: SubtypeSchema[]
  defaultSubtype: string
}

// ─── Base Check Config ────────────────────────────────────────────

export interface BaseCheckConfig {
  ruleName: string
  description: string
  severity: Severity
  subtype: string
  columns: string[]
  threshold_pass: number
  threshold_warn: number | null
  null_handling: NullHandling
  filter_expression: string
}

export function createBaseDefaults(): BaseCheckConfig {
  return {
    ruleName: '',
    description: '',
    severity: 'medium',
    subtype: '',
    columns: [],
    threshold_pass: 100,
    threshold_warn: null,
    null_handling: 'fail',
    filter_expression: '',
  }
}

// ─── Canonical Rule ───────────────────────────────────────────────

export interface CanonicalRule {
  dimension: string
  type: string
  columns: string[]
  parameters: Record<string, unknown>
  severity: Severity
}

// ─── Check Node Config (stored in FlowNode.config) ───────────────

export interface CheckNodeConfig {
  checkConfig: BaseCheckConfig & Record<string, unknown>
  canonicalRule?: CanonicalRule
  templateId?: string
  templateName?: string
}

// ─── Validation ───────────────────────────────────────────────────

export interface ValidationError {
  field: string
  message: string
  tier: 1 | 2 | 3 // 1=field-level, 2=cross-field, 3=structural
}
