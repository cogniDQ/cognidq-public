import { useState, useMemo } from 'react'
import {
  X,
  ChevronRight,
  ChevronLeft,
  CheckCircle2,
  Database,
  Columns,
  Settings,
  Calendar,
  AlertTriangle,
  BookOpen,
  Tag,
  Search,
  Check,
  Loader2,
  Send,
  Crosshair,
} from 'lucide-react'
import type {
  ParseRuleResponse,
  CheckConfigOutput,
  DetectedDataset,
  DetectedColumn,
} from '@/types/nlRuleBuilder'
import ConfidenceBadge from './ConfidenceBadge'

// ─── Schedule ────────────────────────────────────────────────────────────────

export interface ScheduleConfig {
  type: 'manual' | 'hourly' | 'daily' | 'weekly' | 'monthly'
  time?: string        // HH:MM (UTC)
  dayOfWeek?: number   // 0-6 for weekly
  dayOfMonth?: number  // 1-28 for monthly
}

const FREQ_OPTIONS: { value: ScheduleConfig['type']; label: string }[] = [
  { value: 'manual',  label: 'Manual (on demand)' },
  { value: 'hourly',  label: 'Every hour' },
  { value: 'daily',   label: 'Daily' },
  { value: 'weekly',  label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
]

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

// ─── Steps ───────────────────────────────────────────────────────────────────

const STEPS = [
  { id: 1, label: 'Understanding', Icon: BookOpen },
  { id: 2, label: 'Dataset',       Icon: Database },
  { id: 3, label: 'Columns & Checks', Icon: Columns },
  { id: 4, label: 'Configuration', Icon: Settings },
] as const

// ─── Props ───────────────────────────────────────────────────────────────────

interface ParseResultModalProps {
  open: boolean
  onClose: () => void
  result: ParseRuleResponse
  allDatasets: Array<{ id: string; name: string; data_source_name: string | null }>
  onSubmitProposal: (datasetId: string | undefined, schedule: ScheduleConfig) => void
  onDiscard: () => void
  isSubmitting?: boolean
}

// ─── Main Modal ──────────────────────────────────────────────────────────────

export default function ParseResultModal({
  open,
  onClose,
  result,
  allDatasets,
  onSubmitProposal,
  onDiscard,
  isSubmitting,
}: ParseResultModalProps) {
  const sir = result.parsed_rule!
  const detectedDatasets: DetectedDataset[] = result.detected_datasets || []
  const detectedColumns: DetectedColumn[]   = result.detected_columns  || []
  const checkConfigs: CheckConfigOutput[]   = result.check_configs     || []

  const [step, setStep] = useState(1)
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | undefined>(
    () => detectedDatasets[0]?.dataset_id ?? undefined
  )
  const [showDatasetPicker, setShowDatasetPicker] = useState(false)
  const [schedule, setSchedule] = useState<ScheduleConfig>({ type: 'daily', time: '02:00' })

  // ── Glossary terms ──
  const glossaryTerms = useMemo(() => {
    const terms: Array<{ term: string; resolved?: string; type: string }> = []
    const add = (rawText: string, resolved: string | null | undefined, type: string) => {
      if (rawText && !terms.find(t => t.term === rawText)) {
        terms.push({ term: rawText, resolved: resolved ?? undefined, type })
      }
    }
    add(sir.subject?.raw_text, sir.subject?.resolved_column, 'subject')
    if (sir.object) add(sir.object.raw_text, sir.object.resolved_column, 'object')
    for (const cond of sir.conditions || []) {
      add(cond.field?.raw_text, cond.field?.resolved_column, 'condition')
    }
    for (const col of detectedColumns) {
      add(col.raw_text, col.resolved_name, col.role)
    }
    return terms
  }, [sir, detectedColumns])

  // ── Dataset selection helpers ──
  const maxScore = detectedDatasets.reduce((m, d) => Math.max(m, d.match_score), 0)
  const topDatasets = detectedDatasets.filter(d => d.match_score >= maxScore - 0.05)
  const mustChoose = topDatasets.length > 1 && !selectedDatasetId
  const manuallyPicked = selectedDatasetId && !detectedDatasets.find(d => d.dataset_id === selectedDatasetId)

  // ── Checks grouped by column ──
  const checksByColumn = useMemo(() => {
    const map: Record<string, CheckConfigOutput[]> = {}
    for (const cc of checkConfigs) {
      for (const col of cc.columns) {
        if (!map[col]) map[col] = []
        map[col].push(cc)
      }
    }
    return map
  }, [checkConfigs])

  if (!open) return null

  const canNext = () => {
    if (step === 2 && mustChoose) return false
    return true
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
        onClick={onClose}
      >
        {/* Dialog */}
        <div
          className="relative bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden"
          onClick={e => e.stopPropagation()}
        >
          {/* ── Header ── */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 shrink-0">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-green-600" />
              <h2 className="text-lg font-semibold text-gray-900">Parse Result</h2>
              <ConfidenceBadge confidence={sir.confidence} />
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded-lg hover:bg-gray-100"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* ── Stepper ── */}
          <div className="flex items-center gap-1 px-6 py-3 border-b border-gray-100 bg-gray-50 shrink-0">
            {STEPS.map(({ id, label, Icon }, i) => {
              const isActive = step === id
              const isDone   = step > id
              return (
                <div key={id} className="flex items-center">
                  <button
                    onClick={() => { if (isDone) setStep(id) }}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-lg transition-colors text-sm select-none ${
                      isActive ? 'bg-primary-100 text-primary-700 font-semibold' :
                      isDone   ? 'text-green-600 hover:bg-green-50 cursor-pointer' :
                                 'text-gray-400 cursor-default'
                    }`}
                  >
                    {isDone
                      ? <CheckCircle2 className="w-4 h-4 text-green-500" />
                      : <Icon className="w-4 h-4" />
                    }
                    <span className="hidden sm:inline">{label}</span>
                    <span className="sm:hidden">{id}</span>
                  </button>
                  {i < STEPS.length - 1 && (
                    <ChevronRight className="w-3 h-3 text-gray-300 mx-0.5 shrink-0" />
                  )}
                </div>
              )
            })}
          </div>

          {/* ── Body ── */}
          <div className="flex-1 overflow-y-auto px-6 py-5 min-h-0">

            {/* STEP 1 — Understanding */}
            {step === 1 && (
              <div className="space-y-5">
                <Section title="Business Terms Detected">
                  {glossaryTerms.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {glossaryTerms.map((t, i) => (
                        <div
                          key={i}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 border border-indigo-200 rounded-full text-sm"
                        >
                          <Tag className="w-3 h-3 text-indigo-500 shrink-0" />
                          <span className="font-medium text-indigo-800">{t.term}</span>
                          {t.resolved && t.resolved !== t.term && (
                            <>
                              <ChevronRight className="w-3 h-3 text-indigo-300" />
                              <span className="font-mono text-indigo-600 text-xs">{t.resolved}</span>
                            </>
                          )}
                          <RolePill role={t.type} />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-400 italic">No specific business terms extracted.</p>
                  )}
                </Section>

                <div className="grid grid-cols-2 gap-4">
                  <InfoCard label="Rule Type">
                    <span className="px-2.5 py-1 bg-primary-100 text-primary-800 rounded-lg text-sm font-semibold">
                      {sir.rule_type.replace(/_/g, ' ')}
                    </span>
                  </InfoCard>
                  <InfoCard label="Confidence">
                    <ConfidenceBadge confidence={sir.confidence} />
                  </InfoCard>
                </div>

                {sir.operator && (
                  <InfoCard label="Operator / Condition">
                    <p className="font-mono text-gray-800 text-sm">{sir.operator}</p>
                  </InfoCard>
                )}

                {(sir.parse_warnings?.length ?? 0) > 0 && (
                  <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle className="w-4 h-4 text-yellow-600" />
                      <p className="text-sm font-semibold text-yellow-800">Parser Warnings</p>
                    </div>
                    {sir.parse_warnings!.map((w, i) => (
                      <p key={i} className="text-xs text-yellow-700">• {w}</p>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* STEP 2 — Dataset */}
            {step === 2 && (
              <div className="space-y-5">
                <Section title="Matched Datasets">
                  {mustChoose && (
                    <div className="mb-3 flex items-start gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">
                      <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-amber-500" />
                      Multiple datasets matched with equal confidence — please choose the best fit for your rule.
                    </div>
                  )}

                  {detectedDatasets.length === 0 && (
                    <p className="text-sm text-gray-400 italic mb-3">
                      No datasets matched automatically. Please select one below.
                    </p>
                  )}

                  <div className="space-y-2">
                    {[...detectedDatasets]
                      .sort((a, b) => b.match_score - a.match_score)
                      .map((ds, i) => {
                        const isTop      = ds.match_score >= maxScore - 0.01
                        const isSelected = selectedDatasetId === ds.dataset_id
                        return (
                          <label
                            key={i}
                            className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-all ${
                              isSelected
                                ? 'border-primary-400 bg-primary-50 shadow-sm'
                                : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                            }`}
                          >
                            <input
                              type="radio"
                              name="dataset-select"
                              checked={isSelected}
                              onChange={() => setSelectedDatasetId(ds.dataset_id ?? undefined)}
                              className="mt-0.5 accent-primary-600"
                            />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-semibold text-gray-800 text-sm">
                                  {ds.data_source_name
                                    ? <><span className="text-gray-400 font-normal">{ds.data_source_name} › </span>{ds.dataset_name}</>
                                    : ds.dataset_name
                                  }
                                </span>
                                {isTop && (
                                  <span className="text-xs px-1.5 py-0.5 bg-green-100 text-green-700 rounded-full font-medium">
                                    Best match
                                  </span>
                                )}
                              </div>
                              <p className="text-xs text-gray-500 mt-1">{ds.match_reason}</p>
                            </div>
                            <span className={`text-sm font-bold shrink-0 ${
                              ds.match_score >= 0.9 ? 'text-green-600' :
                              ds.match_score >= 0.7 ? 'text-yellow-600' : 'text-gray-500'
                            }`}>
                              {Math.round(ds.match_score * 100)}%
                            </span>
                          </label>
                        )
                      })}
                  </div>
                </Section>

                <div className="flex items-center gap-3">
                  <div className="flex-1 h-px bg-gray-200" />
                  <span className="text-xs text-gray-400">or</span>
                  <div className="flex-1 h-px bg-gray-200" />
                </div>

                <button
                  onClick={() => setShowDatasetPicker(true)}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 border-2 border-dashed border-gray-300 rounded-xl text-sm text-gray-600 hover:border-primary-400 hover:text-primary-600 hover:bg-primary-50 transition-all"
                >
                  <Search className="w-4 h-4" />
                  Choose another dataset…
                </button>

                {manuallyPicked && (
                  <div className="flex items-center gap-2 px-3 py-2.5 bg-primary-50 border border-primary-200 rounded-xl text-sm">
                    <Check className="w-4 h-4 text-primary-600 shrink-0" />
                    <span className="text-primary-800 font-medium">
                      Manually selected: {allDatasets.find(d => d.id === selectedDatasetId)?.name || selectedDatasetId}
                    </span>
                    <button
                      onClick={() => setSelectedDatasetId(undefined)}
                      className="ml-auto text-gray-400 hover:text-gray-600 p-0.5"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* STEP 3 — Columns & Checks */}
            {step === 3 && (
              <div className="space-y-6">
                {/* Targeted columns table */}
                <Section title="Targeted Columns">
                  {detectedColumns.length > 0 ? (
                    <div className="overflow-hidden rounded-xl border border-gray-200">
                      <table className="w-full text-sm">
                        <thead className="bg-gray-50 text-xs uppercase text-gray-500 tracking-wide">
                          <tr>
                            <th className="text-left px-4 py-2.5 font-semibold">Business Term</th>
                            <th className="text-left px-4 py-2.5 font-semibold">Resolved Column</th>
                            <th className="text-left px-4 py-2.5 font-semibold">Role</th>
                            <th className="text-left px-4 py-2.5 font-semibold">Data Type</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {detectedColumns.map((col, i) => (
                            <tr key={i} className="hover:bg-gray-50">
                              <td className="px-4 py-3 font-medium text-gray-800">{col.raw_text}</td>
                              <td className="px-4 py-3 font-mono text-gray-600 text-xs">
                                {col.resolved_name || <span className="text-gray-300">—</span>}
                              </td>
                              <td className="px-4 py-3">
                                <RolePill role={col.role} />
                              </td>
                              <td className="px-4 py-3 text-xs text-gray-500 font-mono">
                                {col.data_type || <span className="text-gray-300">—</span>}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-400 italic">No specific columns detected.</p>
                  )}
                </Section>

                {/* Checks per column */}
                {Object.keys(checksByColumn).length > 0 && (
                  <Section title="Checks per Column">
                    <div className="space-y-3">
                      {Object.entries(checksByColumn).map(([col, checks]) => (
                        <div key={col} className="rounded-xl border border-gray-200 overflow-hidden">
                          <div className="flex items-center gap-2 px-4 py-2.5 bg-gray-50 border-b border-gray-200">
                            <Crosshair className="w-3.5 h-3.5 text-gray-500" />
                            <span className="font-mono font-semibold text-gray-800 text-sm">{col}</span>
                            <span className="ml-auto text-xs text-gray-400">
                              {checks.length} check{checks.length !== 1 ? 's' : ''}
                            </span>
                          </div>
                          <div className="divide-y divide-gray-100">
                            {checks.map((cc, i) => (
                              <div key={i} className="flex items-center gap-2.5 px-4 py-3 flex-wrap">
                                <span className="px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded text-xs font-bold uppercase">
                                  {cc.check_dimension}
                                </span>
                                <span className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded text-xs">
                                  {cc.check_subtype}
                                </span>
                                <span className="text-xs text-gray-400 font-mono">{cc.rule_name}</span>
                                <SeverityBadge severity={cc.severity} />
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </Section>
                )}

                {detectedColumns.length === 0 && Object.keys(checksByColumn).length === 0 && (
                  <div className="text-center py-10 text-gray-400">
                    <Columns className="w-8 h-8 mx-auto mb-2 opacity-40" />
                    <p className="text-sm">Column and check information will be resolved during execution.</p>
                  </div>
                )}
              </div>
            )}

            {/* STEP 4 — Full Configuration */}
            {step === 4 && (
              <div className="space-y-6">
                {/* Check configurations */}
                <Section title="Check Configurations">
                  {checkConfigs.length > 0 ? (
                    <div className="space-y-3">
                      {checkConfigs.map((cc, i) => (
                        <div key={i} className="rounded-xl border border-gray-200 overflow-hidden">
                          {/* Check header */}
                          <div className="flex items-center gap-2 px-4 py-3 bg-gray-50 border-b border-gray-100 flex-wrap">
                            <span className="px-2 py-0.5 bg-indigo-100 text-indigo-800 rounded text-xs font-bold uppercase">
                              {cc.check_dimension}
                            </span>
                            <span className="px-2 py-0.5 bg-purple-100 text-purple-800 rounded text-xs">
                              {cc.check_subtype}
                            </span>
                            <SeverityBadge severity={cc.severity} />
                            <span className="ml-auto text-xs font-mono text-gray-400">{cc.rule_name}</span>
                          </div>
                          {/* Check body */}
                          <div className="p-4 space-y-2.5">
                            {cc.dataset_name && (
                              <KVRow label="Dataset" value={cc.dataset_name} />
                            )}
                            <KVRow label="Columns" value={<span className="font-mono">{cc.columns.join(', ')}</span>} />
                            {cc.description && (
                              <KVRow label="Description" value={<span className="italic text-gray-600">{cc.description}</span>} />
                            )}
                            <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                              <KVRow label="Pass threshold" value={<span className="font-bold text-green-700">{cc.thresholds.threshold_pass}%</span>} />
                              <KVRow label="Warn threshold" value={<span className="font-bold text-yellow-700">{cc.thresholds.threshold_warn}%</span>} />
                              <KVRow label="Null handling"  value={cc.thresholds.null_handling} />
                              <KVRow label="Empty strings"  value={cc.thresholds.include_empty_strings ? 'included' : 'excluded'} />
                            </div>
                            {Object.keys(cc.config).filter(k => k !== 'columns').length > 0 && (
                              <details className="text-xs mt-1">
                                <summary className="text-gray-400 cursor-pointer hover:text-gray-600 select-none">
                                  Node config details
                                </summary>
                                <div className="mt-1.5 bg-gray-50 rounded-lg p-3 font-mono text-gray-500 space-y-0.5 overflow-x-auto">
                                  {Object.entries(cc.config)
                                    .filter(([k]) => k !== 'columns')
                                    .map(([k, v]) => (
                                      <div key={k}>
                                        <span className="text-gray-400">{k}: </span>
                                        <span>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
                                      </div>
                                    ))}
                                </div>
                              </details>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-400 italic">No check configurations available yet.</p>
                  )}
                </Section>

                {/* Schedule configuration */}
                <Section title="Execution Schedule" icon={<Calendar className="w-4 h-4" />}>
                  <div className="space-y-4">
                    {/* Frequency selector */}
                    <div>
                      <p className="text-xs text-gray-500 font-medium mb-2">Frequency</p>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                        {FREQ_OPTIONS.map(opt => (
                          <label
                            key={opt.value}
                            className={`flex items-center gap-2 px-3 py-2.5 rounded-xl border cursor-pointer transition-all text-sm ${
                              schedule.type === opt.value
                                ? 'border-primary-400 bg-primary-50 text-primary-700 font-medium shadow-sm'
                                : 'border-gray-200 hover:border-gray-300 text-gray-700 hover:bg-gray-50'
                            }`}
                          >
                            <input
                              type="radio"
                              name="schedule-freq"
                              value={opt.value}
                              checked={schedule.type === opt.value}
                              onChange={() => setSchedule(prev => ({ ...prev, type: opt.value }))}
                              className="accent-primary-600"
                            />
                            {opt.label}
                          </label>
                        ))}
                      </div>
                    </div>

                    {/* Time / Day controls */}
                    {(schedule.type === 'daily' || schedule.type === 'weekly' || schedule.type === 'monthly') && (
                      <div className="flex items-end gap-4 flex-wrap">
                        <div>
                          <p className="text-xs text-gray-500 font-medium mb-1.5">Time (UTC)</p>
                          <input
                            type="time"
                            value={schedule.time || '02:00'}
                            onChange={e => setSchedule(prev => ({ ...prev, time: e.target.value }))}
                            className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-400 focus:border-transparent"
                          />
                        </div>
                        {schedule.type === 'weekly' && (
                          <div>
                            <p className="text-xs text-gray-500 font-medium mb-1.5">Day of week</p>
                            <div className="flex gap-1">
                              {DAYS.map((d, i) => (
                                <button
                                  key={d}
                                  type="button"
                                  onClick={() => setSchedule(prev => ({ ...prev, dayOfWeek: i }))}
                                  className={`w-9 h-9 rounded-full text-xs font-medium transition-colors ${
                                    schedule.dayOfWeek === i
                                      ? 'bg-primary-600 text-white shadow-sm'
                                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                                  }`}
                                >
                                  {d}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                        {schedule.type === 'monthly' && (
                          <div>
                            <p className="text-xs text-gray-500 font-medium mb-1.5">Day of month</p>
                            <input
                              type="number"
                              min={1}
                              max={28}
                              value={schedule.dayOfMonth ?? 1}
                              onChange={e => setSchedule(prev => ({ ...prev, dayOfMonth: Number(e.target.value) }))}
                              className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-20 focus:outline-none focus:ring-2 focus:ring-primary-400 focus:border-transparent"
                            />
                          </div>
                        )}
                      </div>
                    )}

                    {/* Schedule summary */}
                    <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-100">
                      <p className="text-xs text-gray-500 font-medium mb-0.5">Summary</p>
                      <p className="text-sm text-gray-700">{describeSchedule(schedule)}</p>
                    </div>
                  </div>
                </Section>
              </div>
            )}
          </div>

          {/* ── Footer ── */}
          <div className="flex items-center justify-between px-6 py-4 border-t border-gray-100 bg-gray-50 shrink-0">
            <div className="flex items-center gap-2">
              {step > 1 && (
                <button
                  onClick={() => setStep(s => s - 1)}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm text-gray-600 hover:text-gray-800 border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  <ChevronLeft className="w-4 h-4" />
                  Back
                </button>
              )}
              <button
                onClick={onDiscard}
                className="px-4 py-2 text-sm text-gray-500 hover:text-red-600 border border-gray-200 rounded-lg hover:border-red-200 hover:bg-red-50 transition-colors"
              >
                Discard
              </button>
            </div>

            {step < 4 ? (
              <button
                onClick={() => canNext() && setStep(s => s + 1)}
                disabled={!canNext()}
                className="flex items-center gap-1.5 px-5 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Next
                <ChevronRight className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={() => onSubmitProposal(selectedDatasetId, schedule)}
                disabled={!!isSubmitting}
                className="flex items-center gap-2 px-5 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {isSubmitting
                  ? <Loader2 className="w-4 h-4 animate-spin" />
                  : <Send className="w-4 h-4" />
                }
                Submit as Proposal
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Nested dataset picker */}
      {showDatasetPicker && (
        <DatasetPickerModal
          datasets={allDatasets}
          selectedId={selectedDatasetId}
          onSelect={id => {
            setSelectedDatasetId(id)
            setShowDatasetPicker(false)
          }}
          onClose={() => setShowDatasetPicker(false)}
        />
      )}
    </>
  )
}

// ─── Dataset Picker Modal ─────────────────────────────────────────────────────

function DatasetPickerModal({
  datasets,
  selectedId,
  onSelect,
  onClose,
}: {
  datasets: Array<{ id: string; name: string; data_source_name: string | null }>
  selectedId?: string
  onSelect: (id: string) => void
  onClose: () => void
}) {
  const [query, setQuery] = useState('')
  const filtered = datasets.filter(d =>
    d.name.toLowerCase().includes(query.toLowerCase()) ||
    (d.data_source_name || '').toLowerCase().includes(query.toLowerCase())
  )

  return (
    <div
      className="fixed inset-0 z-[60] bg-black/60 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-md flex flex-col overflow-hidden max-h-[70vh]"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-800">Choose Dataset</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="px-4 pt-3 pb-2 shrink-0">
          <div className="flex items-center gap-2 border border-gray-200 rounded-xl px-3 py-2 focus-within:ring-2 focus-within:ring-primary-400 focus-within:border-primary-400 transition-all">
            <Search className="w-4 h-4 text-gray-400 shrink-0" />
            <input
              type="text"
              placeholder="Search datasets…"
              value={query}
              onChange={e => setQuery(e.target.value)}
              className="flex-1 text-sm outline-none bg-transparent text-gray-800 placeholder-gray-400"
              autoFocus
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-1">
          {filtered.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-8">No datasets found.</p>
          )}
          {filtered.map(ds => (
            <button
              key={ds.id}
              onClick={() => onSelect(ds.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-left transition-colors ${
                selectedId === ds.id
                  ? 'bg-primary-100 text-primary-800'
                  : 'hover:bg-gray-50 text-gray-700'
              }`}
            >
              <Database className="w-4 h-4 text-gray-400 shrink-0" />
              <div className="min-w-0 flex-1">
                <div className={`truncate ${selectedId === ds.id ? 'font-semibold' : 'font-medium'}`}>
                  {ds.name}
                </div>
                {ds.data_source_name && (
                  <div className="text-xs text-gray-400 truncate">{ds.data_source_name}</div>
                )}
              </div>
              {selectedId === ds.id && <Check className="w-4 h-4 text-primary-600 shrink-0" />}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Small helpers ────────────────────────────────────────────────────────────

function Section({
  title,
  icon,
  children,
}: {
  title: string
  icon?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-1.5">
        {icon}
        {title}
      </h3>
      {children}
    </div>
  )
}

function InfoCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
      <p className="text-xs text-gray-500 uppercase font-medium mb-1.5">{label}</p>
      {children}
    </div>
  )
}

function KVRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2 text-xs">
      <span className="text-gray-400 shrink-0">{label}:</span>
      <span className="text-gray-700">{value}</span>
    </div>
  )
}

function RolePill({ role }: { role: string }) {
  const cls =
    role === 'subject'   ? 'bg-blue-100 text-blue-700' :
    role === 'object'    ? 'bg-green-100 text-green-700' :
    role === 'condition' ? 'bg-orange-100 text-orange-700' :
    role === 'scope'     ? 'bg-gray-100 text-gray-600' :
                           'bg-gray-100 text-gray-600'
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${cls}`}>{role}</span>
  )
}

function SeverityBadge({ severity }: { severity: string }) {
  const cls =
    severity === 'critical' ? 'bg-red-100 text-red-800' :
    severity === 'high'     ? 'bg-orange-100 text-orange-800' :
    severity === 'medium'   ? 'bg-yellow-100 text-yellow-800' :
                              'bg-gray-100 text-gray-700'
  return (
    <span className={`ml-auto px-2 py-0.5 rounded text-xs font-medium ${cls}`}>{severity}</span>
  )
}

function describeSchedule(s: ScheduleConfig): string {
  if (s.type === 'manual')  return 'Runs on demand only.'
  if (s.type === 'hourly')  return 'Runs every hour.'
  if (s.type === 'daily')   return `Runs daily at ${s.time || '02:00'} UTC.`
  if (s.type === 'weekly') {
    const day = DAYS[s.dayOfWeek ?? 1]
    return `Runs every ${day} at ${s.time || '02:00'} UTC.`
  }
  if (s.type === 'monthly') {
    return `Runs on day ${s.dayOfMonth ?? 1} of every month at ${s.time || '02:00'} UTC.`
  }
  return ''
}
