/**
 * useCheckConfigPanel — Hook for check node configuration panel state management
 * 
 * Manages form state, validation, dirty tracking, status derivation, 
 * and save/reset logic for the redesigned check config panel.
 */
import { useState, useRef, useMemo, useCallback, useEffect } from 'react'
import { FlowNode } from './types'
import {
  buildDefaultConfig,
  buildCanonicalRule,
  validateConfig,
  deriveNodeStatus,
  buildSummaryText,
} from '../../schemas/dq-checks/index'
import type {
  BaseCheckConfig,
  ValidationError,
  NodeStatus,
  CheckNodeConfig,
} from '../../schemas/dq-checks/types'

// ─── Deep equality for dirty tracking ─────────────────────────────

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (a === null || b === null) return false
  if (typeof a !== typeof b) return false
  if (typeof a !== 'object') return false

  const aObj = a as Record<string, unknown>
  const bObj = b as Record<string, unknown>
  const aKeys = Object.keys(aObj)
  const bKeys = Object.keys(bObj)

  if (aKeys.length !== bKeys.length) return false
  return aKeys.every(key => deepEqual(aObj[key], bObj[key]))
}

// ─── Hook Types ───────────────────────────────────────────────────

interface UseCheckConfigPanelProps {
  node: FlowNode
  allNodes: FlowNode[]
  onSave: (nodeId: string, config: CheckNodeConfig) => void
}

interface UseCheckConfigPanelReturn {
  // Config state
  config: BaseCheckConfig & Record<string, unknown>
  updateField: (key: string, value: unknown) => void
  setConfig: (config: BaseCheckConfig & Record<string, unknown>) => void

  // Derived state
  isDirty: boolean
  errors: ValidationError[]
  blockingErrors: ValidationError[]
  nodeStatus: NodeStatus
  summaryText: string

  // Source info
  hasSource: boolean
  connectedSource: FlowNode | null
  availableColumns: string[]

  // Actions
  save: () => boolean
  reset: () => void
  revertToSaved: () => void

  // Template support
  applyTemplate: (templateConfig: Record<string, unknown>, templateId: string, templateName: string) => void
  appliedTemplate: { id: string; name: string } | null
}

// ─── Hook Implementation ──────────────────────────────────────────

export function useCheckConfigPanel({
  node,
  allNodes,
  onSave,
}: UseCheckConfigPanelProps): UseCheckConfigPanelReturn {
  const dimension = node.checkType || ''

  // Find connected source
  const connectedSource = useMemo(() => {
    return allNodes.find(n =>
      n.type === 'source' && n.connections.includes(node.id)
    ) || null
  }, [allNodes, node.id])

  const hasSource = connectedSource !== null

  // Extract available columns from connected source
  const availableColumns = useMemo((): string[] => {
    if (!connectedSource?.config) return []
    const metadata = connectedSource.config.metadata
    const columns = metadata?.columns || connectedSource.config.columns
    if (!columns || !Array.isArray(columns)) return []
    return columns
      .map((col: unknown) =>
        typeof col === 'string' ? col : ((col as Record<string, string>)?.column_name || (col as Record<string, string>)?.name || '')
      )
      .filter(Boolean) as string[]
  }, [connectedSource])

  // ─── Initialize config from saved node state ───────────────────

  const loadConfig = useCallback((): BaseCheckConfig & Record<string, unknown> => {
    const saved = node.config
    if (saved && typeof saved === 'object') {
      // If saved config has the new format (checkConfig nested)
      if (saved.checkConfig) {
        return { ...saved.checkConfig }
      }
      // Legacy format: config is the raw check config
      // Migrate: map old field names to new
      const base = buildDefaultConfig(dimension)
      return {
        ...base,
        ...saved,
        subtype: saved.subtype || base.subtype,
        severity: saved.severityLevel || saved.severity || base.severity,
        threshold_pass: saved.threshold_pass ?? saved.threshold ?? base.threshold_pass,
        threshold_warn: saved.threshold_warn ?? null,
        null_handling: saved.null_handling || base.null_handling,
        columns: saved.columns || [],
        ruleName: saved.ruleName || '',
        description: saved.description || '',
        filter_expression: saved.filter_expression || '',
      }
    }
    return buildDefaultConfig(dimension)
  }, [node.config, dimension])

  const [currentConfig, setCurrentConfig] = useState<BaseCheckConfig & Record<string, unknown>>(loadConfig)
  const originalConfig = useRef<BaseCheckConfig & Record<string, unknown>>(loadConfig())
  const [appliedTemplate, setAppliedTemplate] = useState<{ id: string; name: string } | null>(null)

  // Reset config when switching to a different node
  useEffect(() => {
    const fresh = loadConfig()
    setCurrentConfig(fresh)
    originalConfig.current = { ...fresh }
    setAppliedTemplate(null)
  }, [node.id])  

  // ─── Field updates ─────────────────────────────────────────────

  const updateField = useCallback((key: string, value: unknown) => {
    setCurrentConfig(prev => {
      const updated = { ...prev, [key]: value }

      // When subtype changes, merge new subtype defaults but keep shared fields
      if (key === 'subtype' && value !== prev.subtype) {
        const subtypeDefaults = buildDefaultConfig(dimension, value as string)
        // Keep shared fields (columns, threshold, severity, etc.)
        return {
          ...subtypeDefaults,
          ruleName: prev.ruleName,
          description: prev.description,
          severity: prev.severity,
          columns: prev.columns,
          threshold_pass: prev.threshold_pass,
          threshold_warn: prev.threshold_warn,
          null_handling: prev.null_handling,
          filter_expression: prev.filter_expression,
          subtype: value as string,
        }
      }

      return updated
    })
  }, [dimension])

  const setConfig = useCallback((config: BaseCheckConfig & Record<string, unknown>) => {
    setCurrentConfig(config)
  }, [])

  // ─── Derived state ─────────────────────────────────────────────

  const isDirty = useMemo(
    () => !deepEqual(currentConfig, originalConfig.current),
    [currentConfig]
  )

  const errors = useMemo(
    () => validateConfig(dimension, currentConfig, hasSource),
    [dimension, currentConfig, hasSource]
  )

  const blockingErrors = useMemo(
    () => errors.filter(e => e.tier === 3),
    [errors]
  )

  const nodeStatus = useMemo(
    () => deriveNodeStatus(hasSource, currentConfig, errors, dimension),
    [hasSource, currentConfig, errors, dimension]
  )

  const summaryText = useMemo(
    () => buildSummaryText(dimension, currentConfig),
    [dimension, currentConfig]
  )

  // ─── Actions ───────────────────────────────────────────────────

  const save = useCallback((): boolean => {
    // Re-validate to catch any issues
    const saveErrors = validateConfig(dimension, currentConfig, hasSource)
    const blocking = saveErrors.filter(e => e.tier === 3)
    if (blocking.length > 0) return false

    const canonicalRule = buildCanonicalRule(dimension, currentConfig)
    const nodeConfig: CheckNodeConfig = {
      checkConfig: currentConfig,
      canonicalRule,
      templateId: appliedTemplate?.id,
      templateName: appliedTemplate?.name,
    }

    onSave(node.id, nodeConfig)
    originalConfig.current = { ...currentConfig }
    return true
  }, [dimension, currentConfig, hasSource, appliedTemplate, onSave, node.id])

  const reset = useCallback(() => {
    const defaults = buildDefaultConfig(dimension)
    setCurrentConfig(defaults)
    setAppliedTemplate(null)
  }, [dimension])

  const revertToSaved = useCallback(() => {
    setCurrentConfig({ ...originalConfig.current })
    setAppliedTemplate(null)
  }, [])

  // ─── Template support ──────────────────────────────────────────

  const applyTemplate = useCallback((
    templateConfig: Record<string, unknown>,
    templateId: string,
    templateName: string
  ) => {
    const base = buildDefaultConfig(dimension)
    setCurrentConfig({
      ...base,
      ...templateConfig,
      // Ensure we keep the correct dimension context
      subtype: (templateConfig.subtype as string) || base.subtype,
    })
    setAppliedTemplate({ id: templateId, name: templateName })
  }, [dimension])

  return {
    config: currentConfig,
    updateField,
    setConfig,
    isDirty,
    errors,
    blockingErrors,
    nodeStatus,
    summaryText,
    hasSource,
    connectedSource,
    availableColumns,
    save,
    reset,
    revertToSaved,
    applyTemplate,
    appliedTemplate,
  }
}
