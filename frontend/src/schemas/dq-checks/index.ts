/**
 * DQ Check Schema Registry — Index
 * 
 * Central registry that maps dimensions to their schemas.
 * Dimension schema files are registered here as they are implemented.
 * P01 ships the registry structure; P03-P05 populate dimension schemas.
 */
import type { Dimension, DimensionSchema, SubtypeSchema, BaseCheckConfig, CanonicalRule, NodeStatus, ValidationError } from './types'
import { DIMENSIONS, createBaseDefaults } from './types'
import { registry, registerDimension } from './registry-store'

// Re-export so callers can still import registerDimension from index
export { registerDimension }

// ─── Auto-register dimension schemas on import ────────────────────
import './completeness'
import './validity'
import './uniqueness'
import './conformity'
import './consistency'
import './timeliness'
import './accuracy'
import './reconciliation'

// ─── Public API ───────────────────────────────────────────────────

/**
 * Get the schema for a dimension. Returns undefined if not yet registered.
 */
export function getDimensionSchema(dimension: string): DimensionSchema | undefined {
  return registry.get(dimension as Dimension)
}

/**
 * Get a specific subtype schema within a dimension.
 */
export function getSubtypeSchema(dimension: string, subtype: string): SubtypeSchema | undefined {
  const dimSchema = getDimensionSchema(dimension)
  if (!dimSchema) return undefined
  return dimSchema.subtypes.find(s => s.subtype === subtype)
}

/**
 * Get all registered dimensions.
 */
export function getAllDimensions(): Dimension[] {
  return DIMENSIONS
}

/**
 * Get all registered dimension schemas (only those that have been loaded).
 */
export function getRegisteredSchemas(): DimensionSchema[] {
  return Array.from(registry.values())
}

/**
 * Check whether a dimension has a registered schema.
 */
export function isDimensionRegistered(dimension: string): boolean {
  return registry.has(dimension as Dimension)
}

// ─── Default Config Builder ───────────────────────────────────────

/**
 * Build a default config for a dimension + subtype combination.
 * Merges BaseCheckConfig defaults with subtype-specific defaults.
 */
export function buildDefaultConfig(dimension: string, subtype?: string): BaseCheckConfig & Record<string, unknown> {
  const base = createBaseDefaults()
  const dimSchema = getDimensionSchema(dimension)

  if (!dimSchema) {
    return { ...base, subtype: subtype || '' }
  }

  const targetSubtype = subtype || dimSchema.defaultSubtype
  const subtypeSchema = dimSchema.subtypes.find(s => s.subtype === targetSubtype)

  if (!subtypeSchema) {
    return { ...base, subtype: targetSubtype }
  }

  const subtypeDefaults = subtypeSchema.defaultConfig()
  return { ...base, subtype: targetSubtype, ...subtypeDefaults }
}

// ─── Canonical Rule Builder ───────────────────────────────────────

/**
 * Build a canonical rule dict from a check config.
 * This is the structure the backend RuleCompiler expects.
 */
export function buildCanonicalRule(
  dimension: string,
  config: BaseCheckConfig & Record<string, unknown>
): CanonicalRule {
  // Extract base params that go into parameters
  const {
    ruleName: _rn, description: _d, severity, subtype, columns,
    threshold_pass, threshold_warn, null_handling, filter_expression,
    ...dimensionParams
  } = config

  return {
    dimension,
    type: subtype,
    columns,
    parameters: {
      ...dimensionParams,
      threshold_pass,
      threshold_warn,
      null_handling,
      filter_expression: filter_expression || undefined,
    },
    severity,
  }
}

// ─── Validation Engine ────────────────────────────────────────────

/**
 * Validate a check config against its schema.
 * Returns an array of validation errors sorted by tier.
 */
export function validateConfig(
  dimension: string,
  config: BaseCheckConfig & Record<string, unknown>,
  hasSource: boolean
): ValidationError[] {
  const errors: ValidationError[] = []

  // Tier 3: Structural — must have source
  if (!hasSource) {
    // Not an error per se — status is NO_SOURCE
    return errors
  }

  // Tier 3: Structural — must have subtype
  if (!config.subtype) {
    errors.push({ field: 'subtype', message: 'Select a check type', tier: 3 })
  }

  // Tier 3: Structural — must have columns (for most subtypes)
  const dimSchema = getDimensionSchema(dimension)
  if (dimSchema && config.subtype) {
    const subtypeSchema = dimSchema.subtypes.find(s => s.subtype === config.subtype)
    if (subtypeSchema) {
      // Check required fields from schema
      for (const field of subtypeSchema.fields) {
        const isRequired = typeof field.required === 'function'
          ? field.required(config as Record<string, unknown>)
          : field.required

        // Check visibility
        const isVisible = field.visibleWhen
          ? field.visibleWhen(config as Record<string, unknown>)
          : true

        if (isRequired && isVisible) {
          const value = config[field.key as keyof typeof config]
          if (value === undefined || value === null || value === '' || (Array.isArray(value) && value.length === 0)) {
            errors.push({
              field: field.key,
              message: `${field.label} is required`,
              tier: field.section === 'targetScope' ? 3 : 1,
            })
          }

          // Run field-specific validation
          if (field.validation && value !== undefined && value !== null && value !== '') {
            const fieldError = field.validation(value, config as Record<string, unknown>)
            if (fieldError) {
              errors.push({ field: field.key, message: fieldError, tier: 1 })
            }
          }
        }
      }
    }
  }

  // Tier 1: threshold_pass range
  if (config.threshold_pass < 0 || config.threshold_pass > 100) {
    errors.push({ field: 'threshold_pass', message: 'Must be between 0 and 100', tier: 1 })
  }

  // Tier 2: threshold_warn must be <= threshold_pass
  if (config.threshold_warn !== null && config.threshold_warn !== undefined) {
    if (config.threshold_warn > config.threshold_pass) {
      errors.push({ field: 'threshold_warn', message: 'Warning threshold must be lower than pass threshold', tier: 2 })
    }
    if (config.threshold_warn < 0 || config.threshold_warn > 100) {
      errors.push({ field: 'threshold_warn', message: 'Must be between 0 and 100', tier: 1 })
    }
  }

  return errors.sort((a, b) => b.tier - a.tier) // Tier 3 first (blocking)
}

// ─── Node Status Derivation ──────────────────────────────────────

/**
 * Derive the node status from config state and validation errors.
 */
export function deriveNodeStatus(
  hasSource: boolean,
  config: (BaseCheckConfig & Record<string, unknown>) | null | undefined,
  errors: ValidationError[],
  dimension?: string
): NodeStatus {
  if (!hasSource) return 'NO_SOURCE'
  if (!config || !config.subtype) return 'NOT_CONFIGURED'

  const blockingErrors = errors.filter(e => e.tier === 3)
  if (blockingErrors.length > 0) return 'INVALID'

  const fieldErrors = errors.filter(e => e.tier === 1 || e.tier === 2)
  // Check if core required fields are set
  if (!config.columns || config.columns.length === 0) {
    // Some subtypes don't require columns (e.g., record_count reconciliation)
    const dimSchema = getDimensionSchema(dimension || '')
    if (!dimSchema) return 'PARTIALLY_CONFIGURED'
  }

  if (fieldErrors.length > 0) return 'PARTIALLY_CONFIGURED'

  // Check for non-blocking warnings
  if (getConfigWarnings(config).length > 0) return 'WARNING'

  return 'READY'
}

// ─── Config Warnings ──────────────────────────────────────────────

/**
 * Get non-blocking warning messages for a check config.
 */
export function getConfigWarnings(
  config: (BaseCheckConfig & Record<string, unknown>) | null | undefined
): string[] {
  if (!config || !config.subtype) return []
  const warnings: string[] = []
  if (config.threshold_pass === 100) {
    warnings.push('100% threshold — any single violation fails the check')
  }
  if (config.columns && config.columns.length > 20) {
    warnings.push('Checking many columns may produce noisy results')
  }
  return warnings
}

// ─── Summary Text Builder ─────────────────────────────────────────

/**
 * Build a human-readable summary from a check config.
 */
export function buildSummaryText(
  dimension: string,
  config: BaseCheckConfig & Record<string, unknown>
): string {
  const parts: string[] = []

  // Dimension > Subtype
  const dimSchema = getDimensionSchema(dimension)
  if (dimSchema && config.subtype) {
    const subtypeSchema = dimSchema.subtypes.find(s => s.subtype === config.subtype)
    const subtypeLabel = subtypeSchema?.label || config.subtype
    const dimLabel = dimension.charAt(0).toUpperCase() + dimension.slice(1)
    parts.push(`${dimLabel} > ${subtypeLabel}`)
  } else {
    parts.push(dimension.charAt(0).toUpperCase() + dimension.slice(1))
  }

  // Columns
  if (config.columns && config.columns.length > 0) {
    if (config.columns.length <= 3) {
      parts.push(`Columns: ${config.columns.join(', ')}`)
    } else {
      parts.push(`Columns: ${config.columns.slice(0, 3).join(', ')} (+${config.columns.length - 3} more)`)
    }
  }

  // Threshold
  const thresholdParts: string[] = []
  thresholdParts.push(`Pass ≥ ${config.threshold_pass}%`)
  if (config.threshold_warn !== null && config.threshold_warn !== undefined) {
    thresholdParts.push(`Warn ≥ ${config.threshold_warn}%`)
  }
  parts.push(`Threshold: ${thresholdParts.join(', ')}`)

  // Severity
  parts.push(`Severity: ${config.severity.charAt(0).toUpperCase() + config.severity.slice(1)}`)

  return parts.join('\n')
}

// ─── Re-exports ───────────────────────────────────────────────────

export type {
  Dimension,
  DimensionSchema,
  SubtypeSchema,
  BaseCheckConfig,
  CanonicalRule,
  NodeStatus,
  ValidationError,
  CheckNodeConfig,
  Severity,
  NullHandling,
  FieldMeta,
  FieldOption,
  SectionId,
  InputType,
} from './types'

export {
  DIMENSIONS,
  SEVERITY_OPTIONS,
  NULL_HANDLING_OPTIONS,
  NODE_STATUS_COLORS,
  NODE_STATUS_BADGE,
  NODE_STATUS_TEXT,
  createBaseDefaults,
} from './types'
