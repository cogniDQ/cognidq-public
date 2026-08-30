import { useState } from 'react'
import { X, Save } from 'lucide-react'
import type { RuleResponse, UpdateRuleRequest } from '@/services/ruleService'

const CATEGORIES = [
  'completeness',
  'validity',
  'conformity',
  'uniqueness',
  'consistency',
  'accuracy',
  'timeliness',
  'statistical',
  'reconciliation',
]

// Keep in sync with backend `_VALID_SUBTYPES_BY_DIMENSION`
// (backend/app/services/proposal/engine.py).
const RULE_TYPES: Record<string, string[]> = {
  completeness: ['null', 'empty', 'placeholder', 'conditional', 'multi_field', 'population', 'group'],
  validity: ['allowed_values', 'range', 'regex', 'reference_lookup', 'business_rule', 'cross_field', 'date_logic', 'negative'],
  conformity: ['regex', 'standard', 'length', 'charset', 'case', 'structural'],
  uniqueness: ['exact', 'composite', 'scoped', 'cross_dataset', 'fuzzy', 'temporal'],
  consistency: ['intra_record', 'formula', 'temporal', 'inter_record', 'cross_table', 'aggregation'],
  accuracy: ['reference_comparison', 'trusted_source', 'tolerated_deviation', 'statistical', 'derived_value'],
  timeliness: ['freshness', 'record_age', 'latency', 'processing_delay', 'delivery_window', 'heartbeat'],
  statistical: ['distribution_check', 'anomaly_detection'],
  reconciliation: ['record_count', 'one_to_one', 'aggregate', 'field_level', 'tolerance', 'missing_extra'],
}

const SEVERITIES = ['blocker', 'critical', 'major', 'minor', 'info']
const STATUSES = ['draft', 'active', 'inactive', 'archived']

interface RuleEditModalProps {
  rule: RuleResponse
  onSave: (ruleId: string, updates: UpdateRuleRequest) => Promise<void>
  onClose: () => void
}

export default function RuleEditModal({ rule, onSave, onClose }: RuleEditModalProps) {
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState(rule.name)
  const [description, setDescription] = useState(rule.description || '')
  const [category, setCategory] = useState(rule.category)
  const canonicalInit = (rule.canonical_rule || {}) as Record<string, unknown>
  const initialSubtype =
    rule.rule_type ||
    (canonicalInit.subtype as string | undefined) ||
    (canonicalInit.check_subtype as string | undefined) ||
    ''
  const [ruleType, setRuleType] = useState(initialSubtype)
  const [status, setStatus] = useState(rule.status)
  const [isActive, setIsActive] = useState(rule.is_active)
  const [targetTable, setTargetTable] = useState(rule.target_table || '')
  const [targetColumns, setTargetColumns] = useState(rule.target_columns?.join(', ') || '')
  const [tags, setTags] = useState(rule.tags?.join(', ') || '')

  // Canonical rule fields
  const canonical = (rule.canonical_rule || {}) as Record<string, unknown>
  const [dimension, setDimension] = useState((canonical.dimension as string) || category)
  const [entity, setEntity] = useState((canonical.entity as string) || '')
  const [condition, setCondition] = useState((canonical.condition as string) || '')
  const [expectation, setExpectation] = useState((canonical.expectation as string) || '')
  const [severity, setSeverity] = useState((canonical.severity as string) || 'medium')

  // Threshold config
  const thresholds = (rule.threshold_config || {}) as Record<string, number | undefined>
  const [passThreshold, setPassThreshold] = useState(thresholds.pass_threshold?.toString() || '')
  const [warningThreshold, setWarningThreshold] = useState(thresholds.warning_threshold?.toString() || '')
  const [maxViolations, setMaxViolations] = useState(thresholds.max_violations?.toString() || '')

  const availableTypes = RULE_TYPES[category] || []
  const subtypeOptions =
    ruleType && !availableTypes.includes(ruleType)
      ? [ruleType, ...availableTypes]
      : availableTypes

  const handleSave = async () => {
    setSaving(true)
    try {
      const updates: UpdateRuleRequest = {
        name,
        description: description || undefined,
        category,
        rule_type: ruleType || undefined,
        status,
        is_active: isActive,
        target_table: targetTable || undefined,
        target_columns: targetColumns ? targetColumns.split(',').map((c) => c.trim()).filter(Boolean) : undefined,
        tags: tags ? tags.split(',').map((t) => t.trim()).filter(Boolean) : undefined,
        canonical_rule: {
          dimension: dimension || category,
          entity,
          condition,
          expectation,
          severity,
        },
        threshold_config: {
          pass_threshold: passThreshold ? parseFloat(passThreshold) : undefined,
          warning_threshold: warningThreshold ? parseFloat(warningThreshold) : undefined,
          max_violations: maxViolations ? parseInt(maxViolations, 10) : undefined,
        },
      }
      await onSave(rule.id, updates)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Edit Rule</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-600">
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        <div className="px-6 py-4 space-y-6">
          {/* Basic Info */}
          <section>
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 uppercase tracking-wider">
              Basic Info
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Status</label>
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s.charAt(0).toUpperCase() + s.slice(1)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-end">
                <label className="inline-flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={isActive}
                    onChange={(e) => setIsActive(e.target.checked)}
                    className="rounded border-gray-300"
                  />
                  <span className="text-sm text-gray-700 dark:text-gray-300">Active</span>
                </label>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Tags</label>
                <input
                  type="text"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  placeholder="comma-separated"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
            </div>
          </section>

          {/* Check Configuration */}
          <section>
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 uppercase tracking-wider">
              Check Configuration
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Category (Check Type)
                </label>
                <select
                  value={category}
                  onChange={(e) => {
                    setCategory(e.target.value)
                    setDimension(e.target.value)
                    setRuleType('')
                  }}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c.charAt(0).toUpperCase() + c.slice(1)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Check Subtype
                </label>
                <select
                  value={ruleType}
                  onChange={(e) => setRuleType(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                >
                  <option value="">Select subtype...</option>
                  {subtypeOptions.map((t) => (
                    <option key={t} value={t}>
                      {t.replace(/_/g, ' ')}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Severity</label>
                <select
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                >
                  {SEVERITIES.map((s) => (
                    <option key={s} value={s}>
                      {s.charAt(0).toUpperCase() + s.slice(1)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </section>

          {/* Canonical Rule Definition */}
          <section>
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 uppercase tracking-wider">
              Rule Definition
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Entity</label>
                <input
                  type="text"
                  value={entity}
                  onChange={(e) => setEntity(e.target.value)}
                  placeholder="table.column"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Condition</label>
                <input
                  type="text"
                  value={condition}
                  onChange={(e) => setCondition(e.target.value)}
                  placeholder="IS NOT NULL, REGEX, etc."
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Expectation</label>
                <input
                  type="text"
                  value={expectation}
                  onChange={(e) => setExpectation(e.target.value)}
                  placeholder="100%, >95%, etc."
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
            </div>
          </section>

          {/* Target */}
          <section>
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 uppercase tracking-wider">
              Target
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Table</label>
                <input
                  type="text"
                  value={targetTable}
                  onChange={(e) => setTargetTable(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Columns</label>
                <input
                  type="text"
                  value={targetColumns}
                  onChange={(e) => setTargetColumns(e.target.value)}
                  placeholder="comma-separated"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
            </div>
          </section>

          {/* Thresholds */}
          <section>
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 uppercase tracking-wider">
              Thresholds
            </h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Pass Threshold (%)
                </label>
                <input
                  type="number"
                  value={passThreshold}
                  onChange={(e) => setPassThreshold(e.target.value)}
                  min="0"
                  max="100"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Warning Threshold (%)
                </label>
                <input
                  type="number"
                  value={warningThreshold}
                  onChange={(e) => setWarningThreshold(e.target.value)}
                  min="0"
                  max="100"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Max Violations
                </label>
                <input
                  type="number"
                  value={maxViolations}
                  onChange={(e) => setMaxViolations(e.target.value)}
                  min="0"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
            </div>
          </section>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !name}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  )
}
