/**
 * Check Configuration Panel — Redesigned (F094 P01)
 * 
 * Schema-driven right-side panel (440px) for configuring DQ check nodes.
 * Uses useCheckConfigPanel hook for state management and section components
 * for consistent rendering across all 8 dimensions.
 * 
 * Standard section order:
 *   General → Check Type → Target Scope → Business Logic →
 *   Reference Data → Thresholds → Advanced → Summary
 * 
 * Sections 4-5 (Business Logic, Reference Data) and column picker
 * are rendered from P02/P03+ shared components. P01 provides the shell.
 */
import { useState } from 'react'
import { X, Save, AlertTriangle, RotateCcw } from 'lucide-react'
import { FlowNode } from './types'
import { useCheckConfigPanel } from './useCheckConfigPanel'
import { getDimensionSchema, getSubtypeSchema } from '../../schemas/dq-checks/index'
import type { CheckNodeConfig } from '../../schemas/dq-checks/types'
import { GeneralSection } from './config-sections/GeneralSection'
import { CheckTypeSection } from './config-sections/CheckTypeSection'
import { TargetScopeSection } from './config-sections/TargetScopeSection'
import { BusinessLogicSection } from './config-sections/BusinessLogicSection'
import { ThresholdsSection } from './config-sections/ThresholdsSection'
import { AdvancedSettingsSection } from './config-sections/AdvancedSettingsSection'
import { SummaryPreviewSection } from './config-sections/SummaryPreviewSection'
import { ReferenceDataSection } from './config-sections/ReferenceDataSection'
import { TemplatePicker, Template } from './TemplatePicker'
import type { DatasetOption } from './shared/DatasetPicker'

// ─── Props ────────────────────────────────────────────────────────

interface CheckConfigPanelProps {
  node: FlowNode | null
  checkConfig: any
  onConfigChange: (config: any) => void
  onClose: () => void
  onSave: (config: any) => void
  allNodes?: FlowNode[]
  availableDatasets?: DatasetOption[]
  loadingDatasets?: boolean
}

// ─── Component ────────────────────────────────────────────────────

export function CheckConfigPanel(props: CheckConfigPanelProps) {
  if (!props.node) return null
  return <CheckConfigPanelInner {...props} node={props.node} />
}

function CheckConfigPanelInner({ node, onConfigChange, onClose, onSave, allNodes = [], availableDatasets = [], loadingDatasets = false }: CheckConfigPanelProps & { node: FlowNode }) {
  const dimension = node.checkType || ''
  const schema = getDimensionSchema(dimension)
  const [showTemplatePicker, setShowTemplatePicker] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)

  // Wrap the legacy onSave to bridge with new hook
  const handleNodeSave = (_nodeId: string, config: CheckNodeConfig) => {
    // Bridge: write the new config format back to the old state manager
    // The checkConfig in useFlowBuilder expects a flat object
    const flatConfig = {
      ...config.checkConfig,
      canonicalRule: config.canonicalRule,
      templateId: config.templateId,
      templateName: config.templateName,
    }
    onConfigChange(flatConfig)
    // Pass config directly to avoid stale closure race condition
    onSave(flatConfig)
  }

  const {
    config,
    updateField,
    isDirty,
    errors,
    blockingErrors,
    nodeStatus: _nodeStatus,
    summaryText,
    hasSource,
    connectedSource,
    availableColumns,
    save,
    reset,
    revertToSaved,
    applyTemplate,
    appliedTemplate,
  } = useCheckConfigPanel({
    node,
    allNodes,
    onSave: handleNodeSave,
  })

  // ─── Close handling ─────────────────────────────────────────────

  const handleClose = () => {
    if (isDirty) {
      setShowConfirm(true)
    } else {
      onClose()
    }
  }

  const handleDiscard = () => {
    revertToSaved()
    setShowConfirm(false)
    onClose()
  }

  const handleSaveAndClose = () => {
    if (save()) {
      setShowConfirm(false)
      onClose()
    }
  }

  const handleSave = () => {
    save()
  }

  const handleTemplateApply = (template: Template) => {
    applyTemplate(template.presetConfig, template.id, template.name)
    setShowTemplatePicker(false)
  }

  // ─── Render ─────────────────────────────────────────────────────

  const dimLabel = dimension.charAt(0).toUpperCase() + dimension.slice(1)
  const sourceName = connectedSource?.name || connectedSource?.config?.name || 'Unknown'

  return (
    <div className="absolute right-0 top-0 bottom-0 w-[440px] bg-dark-800 border-l border-dark-700 flex flex-col z-50 shadow-xl">
      {/* ── Template Picker Overlay ──────────────────────────────── */}
      {showTemplatePicker && (
        <TemplatePicker
          dimension={dimension}
          templates={[]}
          onApply={handleTemplateApply}
          onBack={() => setShowTemplatePicker(false)}
        />
      )}

      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-dark-700 flex-shrink-0">
        <div>
          <h3 className="text-sm font-semibold text-white">Configure Check</h3>
          <p className="text-xs text-gray-400">
            {dimLabel} {hasSource ? `· ${sourceName}` : ''}
          </p>
        </div>
        <button
          onClick={handleClose}
          className="p-1.5 hover:bg-dark-700 rounded-lg transition-colors"
        >
          <X className="w-4 h-4 text-gray-400" />
        </button>
      </div>

      {/* ── Content (scrollable) ─────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">

        {/* No source warning */}
        {!hasSource && (
          <div className="p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg flex items-start space-x-2">
            <AlertTriangle className="w-4 h-4 text-yellow-400 mt-0.5 flex-shrink-0" />
            <div className="text-xs text-yellow-400">
              <p className="font-medium">No data source connected</p>
              <p className="text-yellow-500/80 mt-1">Connect a data source to enable column selection</p>
            </div>
          </div>
        )}

        {/* Section 1: General */}
        <GeneralSection config={config} onChange={updateField} errors={errors} />

        {/* Divider */}
        <div className="border-t border-dark-700" />

        {/* Section 2: Check Type */}
        <CheckTypeSection
          dimension={dimension}
          schema={schema}
          config={config}
          onChange={updateField}
          errors={errors}
          onOpenTemplatePicker={() => setShowTemplatePicker(true)}
          appliedTemplate={appliedTemplate}
        />

        {/* Divider */}
        <div className="border-t border-dark-700" />

        {/* Section 3: Target Scope (Column Picker) */}
        <TargetScopeSection
          config={config}
          onChange={updateField}
          availableColumns={availableColumns}
          errors={errors}
          hasSource={hasSource}
          columnLabel={config.subtype === 'composite' ? 'Composite Key Columns' : undefined}
        />

        {/* Divider */}
        <div className="border-t border-dark-700" />

        {/* Section 4: Business Logic (schema-driven dynamic fields) */}
        {(() => {
          const subtypeSchema = getSubtypeSchema(dimension, config.subtype as string || '')
          const fields = subtypeSchema?.fields || []
          if (fields.length === 0) return null
          return (
            <>
              <BusinessLogicSection
                fields={fields}
                config={config}
                onChange={updateField}
                onConfigChange={updateField}
                errors={errors}
                availableColumns={availableColumns}
              />
              <div className="border-t border-dark-700" />
            </>
          )
        })()}

        {/* Section 5: Reference Data — shown when subtype requires it */}
        {(() => {
          const subtypeSchema = getSubtypeSchema(dimension, config.subtype as string || '')
          if (!subtypeSchema?.requiresReferenceData) return null
          const showCompare = ['reference_comparison', 'trusted_source', 'tolerated_deviation'].includes(config.subtype as string)
          return (
            <>
              <ReferenceDataSection
                config={config}
                onChange={updateField}
                errors={errors}
                sourceColumns={availableColumns}
                availableDatasets={availableDatasets}
                loadingDatasets={loadingDatasets}
                showCompareColumns={showCompare}
              />
              <div className="border-t border-dark-700" />
            </>
          )
        })()}

        {/* Section 6: Thresholds */}
        <ThresholdsSection config={config} onChange={updateField} errors={errors} />

        {/* Divider */}
        <div className="border-t border-dark-700" />

        {/* Section 7: Advanced Settings */}
        {(() => {
          const subtypeSchema = getSubtypeSchema(dimension, config.subtype as string || '')
          const advancedFields = subtypeSchema?.fields.filter(f => f.section === 'advanced') || []
          return (
            <AdvancedSettingsSection
              config={config}
              onChange={updateField}
              errors={errors}
              advancedFields={advancedFields}
            />
          )
        })()}

        {/* Divider */}
        <div className="border-t border-dark-700" />

        {/* Section 8: Summary */}
        <SummaryPreviewSection
          dimension={dimension}
          summaryText={summaryText}
          config={config}
        />
      </div>

      {/* ── Error Summary Banner ─────────────────────────────────── */}
      {blockingErrors.length > 0 && (
        <div className="mx-4 mb-2 px-3 py-2 bg-red-500/10 border border-red-500/30 rounded-lg text-xs text-red-400">
          Fix {blockingErrors.length} error(s) before saving
        </div>
      )}

      {/* ── Confirmation Bar ─────────────────────────────────────── */}
      {showConfirm && (
        <div className="px-4 py-2 bg-dark-700 border-t border-dark-600 flex items-center justify-between text-xs">
          <span className="text-gray-300">You have unsaved changes.</span>
          <div className="flex space-x-2">
            <button
              onClick={handleDiscard}
              className="px-3 py-1 text-gray-400 hover:text-gray-300 border border-dark-600 rounded"
            >
              Discard
            </button>
            <button
              onClick={handleSaveAndClose}
              className="px-3 py-1 bg-primary-600 text-white rounded hover:bg-primary-500"
            >
              Save & Close
            </button>
          </div>
        </div>
      )}

      {/* ── Footer ───────────────────────────────────────────────── */}
      <div className="px-4 py-3 border-t border-dark-700 flex items-center justify-between flex-shrink-0">
        <button
          onClick={reset}
          className="text-xs text-gray-400 hover:text-gray-300 flex items-center space-x-1"
        >
          <RotateCcw className="w-3 h-3" />
          <span>Reset defaults</span>
        </button>
        <button
          onClick={handleSave}
          disabled={blockingErrors.length > 0}
          className={`px-6 py-2 rounded-lg text-sm font-medium flex items-center space-x-2 transition-colors ${
            blockingErrors.length > 0
              ? 'bg-dark-700 text-gray-500 cursor-not-allowed'
              : 'bg-primary-600 hover:bg-primary-500 text-white'
          }`}
        >
          <Save className="w-4 h-4" />
          <span>Save</span>
        </button>
      </div>
    </div>
  )
}
