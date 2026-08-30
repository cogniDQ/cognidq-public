/**
 * RuleFormModal — Schema-driven manual rule create/edit
 *
 * Uses the same `dq-checks` schema that powers the Flow Builder so that
 * fields, validation, and defaults stay in sync. The user picks a dataset,
 * dimension, and subtype; the form then renders dynamic fields from the
 * subtype schema (BusinessLogic, ReferenceData, etc.).
 *
 * When the optional `rule` prop is supplied the modal switches to edit mode:
 * all fields are prefilled and submit calls `onUpdate(id, payload)` instead
 * of `onCreate(payload)`.
 */
import { useEffect, useMemo, useState, useCallback } from 'react'
import { X, Save, AlertTriangle, Loader2 } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import {
  buildDefaultConfig,
  buildCanonicalRule,
  getDimensionSchema,
  getSubtypeSchema,
  getRegisteredSchemas,
  validateConfig,
} from '@/schemas/dq-checks'
import type {
  BaseCheckConfig,
  Severity,
} from '@/schemas/dq-checks/types'

import { GeneralSection } from '@/components/flow-builder/config-sections/GeneralSection'
import { CheckTypeSection } from '@/components/flow-builder/config-sections/CheckTypeSection'
import { TargetScopeSection } from '@/components/flow-builder/config-sections/TargetScopeSection'
import { BusinessLogicSection } from '@/components/flow-builder/config-sections/BusinessLogicSection'
import { ReferenceDataSection } from '@/components/flow-builder/config-sections/ReferenceDataSection'
import { ThresholdsSection } from '@/components/flow-builder/config-sections/ThresholdsSection'
import { AdvancedSettingsSection } from '@/components/flow-builder/config-sections/AdvancedSettingsSection'

import { listDatasets, getDataset } from '@/services/datasetService'
import type { CreateRuleRequest, RuleResponse, UpdateRuleRequest } from '@/services/ruleService'

type CheckConfig = BaseCheckConfig & Record<string, unknown>

// Map dq-checks schema severities → backend ViolationSeverity enum.
const SEVERITY_MAP: Record<Severity, 'blocker' | 'critical' | 'major' | 'minor' | 'info'> = {
  blocker: 'blocker',
  critical: 'critical',
  high: 'major',
  medium: 'major',
  low: 'minor',
}

// Reverse map (best-effort) so edit mode can show the original UI severity.
const SEVERITY_REVERSE: Record<string, Severity> = {
  blocker: 'blocker',
  critical: 'critical',
  major: 'medium',
  minor: 'low',
  info: 'low',
}

interface RuleFormModalProps {
  workspaceId: string
  /** When provided, modal is in edit mode and prefills from this rule. */
  rule?: RuleResponse
  onCreate?: (payload: CreateRuleRequest) => Promise<void>
  onUpdate?: (ruleId: string, payload: UpdateRuleRequest) => Promise<void>
  onClose: () => void
}

export default function RuleFormModal({
  workspaceId,
  rule,
  onCreate,
  onUpdate,
  onClose,
}: RuleFormModalProps) {
  const isEdit = !!rule
  const dimensions = useMemo(() => getRegisteredSchemas().map((s) => s.dimension), [])

  // ── Recover the original check_config (when stored) or reconstruct it ──
  const initialFromRule = useMemo(() => {
    if (!rule) return null
    const meta = (rule.metadata || {}) as Record<string, unknown>
    const savedCfg = (meta.check_config as Record<string, unknown> | undefined) || null
    const dim = rule.category
    const canonical = (rule.canonical_rule || {}) as Record<string, unknown>
    const params = (canonical.parameters as Record<string, unknown> | undefined) || {}
    const subtype =
      (savedCfg?.subtype as string) ||
      rule.rule_type ||
      (canonical.type as string) ||
      (params.subtype as string) ||
      ''
    const baseDefaults = buildDefaultConfig(dim, subtype || undefined)
    const merged: CheckConfig = {
      ...baseDefaults,
      ...(savedCfg || {}),
      subtype,
      ruleName: rule.name || '',
      description: rule.description || '',
      severity:
        (savedCfg?.severity as Severity) ||
        SEVERITY_REVERSE[String(canonical.severity || '').toLowerCase()] ||
        'medium',
      columns:
        (savedCfg?.columns as string[]) ||
        (params.columns as string[]) ||
        rule.target_columns ||
        [],
      threshold_pass:
        (savedCfg?.threshold_pass as number) ??
        (params.threshold_pass as number) ??
        ((rule.threshold_config as Record<string, unknown> | undefined)?.pass_threshold as number) ??
        100,
      threshold_warn:
        (savedCfg?.threshold_warn as number | null) ??
        ((rule.threshold_config as Record<string, unknown> | undefined)?.warning_threshold as
          | number
          | null) ??
        null,
      null_handling:
        (savedCfg?.null_handling as 'fail' | 'skip' | 'pass') ||
        ((params.null_handling as 'fail' | 'skip' | 'pass') ?? 'fail'),
      filter_expression:
        (savedCfg?.filter_expression as string) ||
        ((params.filter_expression as string) ?? ''),
    }
    return { dimension: dim, config: merged }
  }, [rule])

  const [dimension, setDimension] = useState<string>(
    initialFromRule?.dimension || dimensions[0] || 'completeness',
  )
  const [config, setConfig] = useState<CheckConfig>(
    initialFromRule?.config || buildDefaultConfig(dimensions[0] || 'completeness'),
  )

  const [tagsInput, setTagsInput] = useState((rule?.tags || []).join(', '))
  const [status, setStatus] = useState<'draft' | 'active' | 'inactive'>(
    ((rule?.status as 'draft' | 'active' | 'inactive') ?? 'draft'),
  )
  const [isActive, setIsActive] = useState<boolean>(rule?.is_active ?? true)

  const [datasetId, setDatasetId] = useState<string>('')
  const [datasetTouched, setDatasetTouched] = useState(false)
  const [saving, setSaving] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // ── Datasets list for the workspace (active only) ──────────────
  const datasetsQuery = useQuery({
    queryKey: ['rule-create-modal:datasets', workspaceId],
    queryFn: () => listDatasets(workspaceId, { page_size: 100, status: 'active' }),
    staleTime: 60_000,
  })

  const datasetOptions = useMemo(
    () =>
      (datasetsQuery.data?.items ?? []).map((d) => ({
        id: d.dataset_id,
        name: d.dataset_name,
        description: d.business_domain || d.physical_identifier,
      })),
    [datasetsQuery.data],
  )

  // In edit mode, auto-select the dataset that matches the rule's target.
  useEffect(() => {
    if (!rule || datasetTouched || datasetId) return
    const items = datasetsQuery.data?.items
    if (!items || items.length === 0) return
    const match = items.find(
      (d) =>
        (rule.data_source_id && d.data_source_id === rule.data_source_id &&
          (d.physical_identifier === rule.target_table || d.dataset_name === rule.target_table)) ||
        d.physical_identifier === rule.target_table ||
        d.dataset_name === rule.target_table,
    )
    if (match) setDatasetId(match.dataset_id)
  }, [rule, datasetsQuery.data, datasetTouched, datasetId])

  // ── Selected dataset detail (fields/columns) ───────────────────
  const datasetDetail = useQuery({
    queryKey: ['rule-create-modal:dataset-detail', workspaceId, datasetId],
    queryFn: () => getDataset(workspaceId, datasetId),
    enabled: !!datasetId,
    staleTime: 60_000,
  })

  const availableColumns = useMemo<string[]>(() => {
    const ds = datasetDetail.data
    if (!ds || !ds.fields) return []
    return ds.fields.map((f) => f.field_name).filter(Boolean)
  }, [datasetDetail.data])

  const hasSource = !!datasetId

  // ── Dimension switching: reset to that dimension's default subtype config
  const handleDimensionChange = useCallback((next: string) => {
    setDimension(next)
    setConfig((prev) => {
      const defaults = buildDefaultConfig(next)
      // Preserve general fields the user has already typed.
      return {
        ...defaults,
        ruleName: prev.ruleName,
        description: prev.description,
        severity: prev.severity,
        columns: [],
        threshold_pass: prev.threshold_pass,
        threshold_warn: prev.threshold_warn,
        null_handling: prev.null_handling,
        filter_expression: prev.filter_expression,
      }
    })
  }, [])

  // ── Field updates (mirrors useCheckConfigPanel.updateField) ────
  const updateField = useCallback(
    (key: string, value: unknown) => {
      setConfig((prev) => {
        if (key === 'subtype' && value !== prev.subtype) {
          const next = buildDefaultConfig(dimension, value as string)
          return {
            ...next,
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
        return { ...prev, [key]: value }
      })
    },
    [dimension],
  )

  // Reset table-scoped columns whenever the dataset is changed by the user.
  // (Skip while we're auto-selecting the rule's original dataset in edit mode.)
  useEffect(() => {
    if (!datasetTouched) return
    setConfig((prev) => ({ ...prev, columns: [] }))
  }, [datasetId, datasetTouched])

  // ── Validation ─────────────────────────────────────────────────
  const errors = useMemo(
    () => validateConfig(dimension, config, hasSource),
    [dimension, config, hasSource],
  )
  const blockingErrors = errors.filter((e) => e.tier === 3)

  const canSubmit =
    hasSource &&
    !!config.subtype &&
    !!config.ruleName?.trim() &&
    blockingErrors.length === 0 &&
    !saving

  // ── Submit ─────────────────────────────────────────────────────
  const handleSubmit = async () => {
    setSubmitError(null)
    if (!hasSource) {
      setDatasetTouched(true)
      return
    }
    if (!canSubmit) return

    const ds = datasetDetail.data
    const tableName = ds?.physical_identifier || ds?.dataset_name || ''
    const schemaName = ds?.schema_name || undefined

    const canonical = buildCanonicalRule(dimension, config)
    const firstCol = (config.columns?.[0] as string) || ''
    const entity = firstCol ? `${tableName}.${firstCol}` : tableName || (config.subtype as string)
    const condition = (config.subtype as string).replace(/_/g, ' ').toUpperCase()
    const expectation = `${config.threshold_pass ?? 100}%`

    const backendSeverity = SEVERITY_MAP[config.severity] || 'major'

    const payload: CreateRuleRequest = {
      name: config.ruleName.trim(),
      description: config.description?.trim() || undefined,
      category: dimension,
      rule_type: config.subtype as string,
      canonical_rule: {
        dimension,
        entity,
        condition,
        expectation,
        severity: backendSeverity,
        parameters: {
          ...(canonical.parameters || {}),
          subtype: config.subtype,
          columns: config.columns,
        },
      },
      data_source_id: ds?.data_source_id || undefined,
      target_schema: schemaName,
      target_table: tableName || undefined,
      target_columns: (config.columns as string[])?.length ? (config.columns as string[]) : undefined,
      status,
      is_active: isActive,
      tags: tagsInput
        ? tagsInput.split(',').map((t) => t.trim()).filter(Boolean)
        : undefined,
      threshold_config:
        config.threshold_pass !== undefined || config.threshold_warn !== undefined
          ? {
              pass_threshold:
                typeof config.threshold_pass === 'number' ? config.threshold_pass : undefined,
              warning_threshold:
                typeof config.threshold_warn === 'number' ? config.threshold_warn : undefined,
            }
          : undefined,
      metadata: {
        dq_check_subtype: config.subtype,
        check_config: config,
      },
    }

    setSaving(true)
    try {
      if (isEdit && rule && onUpdate) {
        await onUpdate(rule.id, payload as UpdateRuleRequest)
      } else if (onCreate) {
        await onCreate(payload)
      }
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      if (typeof detail === 'string') setSubmitError(detail)
      else if (Array.isArray(detail))
        setSubmitError(detail.map((m: { msg?: string }) => m?.msg || JSON.stringify(m)).join('; '))
      else setSubmitError(isEdit ? 'Failed to update rule' : 'Failed to create rule')
    } finally {
      setSaving(false)
    }
  }

  // ── Render ─────────────────────────────────────────────────────
  const schema = getDimensionSchema(dimension)
  const subtypeSchema = getSubtypeSchema(dimension, (config.subtype as string) || '')
  const businessFields = subtypeSchema?.fields || []
  const advancedFields = subtypeSchema?.fields.filter((f) => f.section === 'advanced') || []
  const requiresReference = !!subtypeSchema?.requiresReferenceData
  const showCompareColumns = ['reference_comparison', 'trusted_source', 'tolerated_deviation'].includes(
    (config.subtype as string) || '',
  )

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
      data-testid="rule-create-modal"
    >
      <div
        className="bg-dark-900 border border-dark-700 rounded-xl shadow-2xl w-full max-w-3xl max-h-[92vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-dark-700 flex-shrink-0">
          <div>
            <h3 className="text-sm font-semibold text-white">
              {isEdit ? 'Edit Rule' : 'New Rule'}
            </h3>
            <p className="text-xs text-gray-400">
              Schema-driven configuration — same fields as the Flow Builder
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-dark-700 rounded-lg transition-colors"
            aria-label="Close"
          >
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {submitError && (
            <div
              role="alert"
              className="px-3 py-2 bg-red-500/10 border border-red-500/30 rounded-lg text-xs text-red-400"
            >
              {submitError}
            </div>
          )}

          {/* Target Dataset */}
          <section className="space-y-2">
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-1">
              Target Dataset
              <span className="text-red-400 text-sm leading-none" title="Required">*</span>
            </h4>
            <select
              value={datasetId}
              onChange={(e) => {
                setDatasetTouched(true)
                setDatasetId(e.target.value)
              }}
              className={`w-full bg-dark-800 border rounded-lg px-3 py-2 text-sm text-gray-200 focus:ring-1 outline-none ${
                !hasSource && datasetTouched
                  ? 'border-red-500 focus:border-red-500 focus:ring-red-500'
                  : 'border-dark-700 focus:border-primary-500 focus:ring-primary-500'
              }`}
              data-testid="rule-create-dataset"
            >
              <option value="">
                {datasetsQuery.isLoading ? 'Loading datasets…' : 'Select a dataset…'}
              </option>
              {datasetOptions.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                  {d.description ? ` — ${d.description}` : ''}
                </option>
              ))}
            </select>
            {datasetId && datasetDetail.isLoading && (
              <p className="flex items-center gap-2 text-xs text-gray-500">
                <Loader2 className="w-3 h-3 animate-spin" />
                Loading columns…
              </p>
            )}
            {!hasSource && (
              <div className={`p-2 rounded-lg flex items-start gap-2 ${
                datasetTouched
                  ? 'bg-red-500/10 border border-red-500/30'
                  : 'bg-yellow-500/10 border border-yellow-500/30'
              }`}>
                <AlertTriangle className={`w-4 h-4 mt-0.5 flex-shrink-0 ${datasetTouched ? 'text-red-400' : 'text-yellow-400'}`} />
                <p className={`text-xs ${datasetTouched ? 'text-red-400' : 'text-yellow-400'}`}>
                  A dataset is required. Rules without a dataset cannot be executed in a flow.
                </p>
              </div>
            )}
          </section>

          <div className="border-t border-dark-700" />

          {/* Dimension picker (rule-level, not part of GeneralSection) */}
          <section className="space-y-2">
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              Dimension
            </h4>
            <select
              value={dimension}
              onChange={(e) => handleDimensionChange(e.target.value)}
              className="w-full bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
              data-testid="rule-create-dimension"
            >
              {dimensions.map((d) => (
                <option key={d} value={d}>
                  {d.charAt(0).toUpperCase() + d.slice(1)}
                </option>
              ))}
            </select>
          </section>

          <div className="border-t border-dark-700" />

          <GeneralSection config={config} onChange={updateField} errors={errors} />

          <div className="border-t border-dark-700" />

          <CheckTypeSection
            dimension={dimension}
            schema={schema}
            config={config}
            onChange={updateField}
            errors={errors}
            onOpenTemplatePicker={() => { /* Templates not exposed in manual create */ }}
            appliedTemplate={null}
          />

          <div className="border-t border-dark-700" />

          <TargetScopeSection
            config={config}
            onChange={updateField}
            availableColumns={availableColumns}
            errors={errors}
            hasSource={hasSource}
            columnLabel={config.subtype === 'composite' ? 'Composite Key Columns' : undefined}
          />

          {businessFields.length > 0 && (
            <>
              <div className="border-t border-dark-700" />
              <BusinessLogicSection
                fields={businessFields}
                config={config}
                onChange={updateField}
                errors={errors}
                availableColumns={availableColumns}
              />
            </>
          )}

          {requiresReference && (
            <>
              <div className="border-t border-dark-700" />
              <ReferenceDataSection
                config={config}
                onChange={updateField}
                errors={errors}
                sourceColumns={availableColumns}
                availableDatasets={datasetOptions}
                showCompareColumns={showCompareColumns}
              />
            </>
          )}

          <div className="border-t border-dark-700" />

          <ThresholdsSection config={config} onChange={updateField} errors={errors} />

          {advancedFields.length > 0 && (
            <>
              <div className="border-t border-dark-700" />
              <AdvancedSettingsSection
                config={config}
                onChange={updateField}
                errors={errors}
                advancedFields={advancedFields}
              />
            </>
          )}

          <div className="border-t border-dark-700" />

          {/* Rule-level meta */}
          <section className="space-y-3">
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              Lifecycle
            </h4>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">Status</label>
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value as typeof status)}
                  className="w-full bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
                >
                  <option value="draft">Draft</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </div>
              <div className="flex items-end">
                <label className="inline-flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={isActive}
                    onChange={(e) => setIsActive(e.target.checked)}
                    className="rounded border-dark-700 bg-dark-800"
                  />
                  <span className="text-sm text-gray-300">Active</span>
                </label>
              </div>
              <div className="col-span-2">
                <label className="block text-sm font-medium text-gray-300 mb-1">Tags</label>
                <input
                  type="text"
                  value={tagsInput}
                  onChange={(e) => setTagsInput(e.target.value)}
                  placeholder="comma-separated"
                  className="w-full bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
                />
              </div>
            </div>
          </section>
        </div>

        {/* Blocking errors banner */}
        {hasSource && blockingErrors.length > 0 && (
          <div className="mx-5 mb-2 px-3 py-2 bg-red-500/10 border border-red-500/30 rounded-lg text-xs text-red-400 flex-shrink-0">
            Fix {blockingErrors.length} error{blockingErrors.length === 1 ? '' : 's'} before saving:{' '}
            {blockingErrors.map((e) => e.message).join(' · ')}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-dark-700 flex-shrink-0">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-gray-300 border border-dark-600 rounded-lg hover:bg-dark-700"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            data-testid="rule-create-submit"
            className="inline-flex items-center gap-2 px-4 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {saving
              ? isEdit
                ? 'Saving…'
                : 'Creating…'
              : isEdit
                ? 'Save Changes'
                : 'Create Rule'}
          </button>
        </div>
      </div>
    </div>
  )
}
