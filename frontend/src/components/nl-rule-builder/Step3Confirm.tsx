import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, FlaskConical, AlertTriangle, CheckCircle2 } from 'lucide-react'
import type { ParseRuleResponse, NLRuleDraft, TestPreviewResponse } from '@/types/nlRuleBuilder'
import type { ScheduleConfig } from './ParseResultModal'
import CompiledConfigPreview from './CompiledConfigPreview'
import ContextPanel from './ContextPanel'
import { testParseOnSample } from '@/services/nlRuleBuilderService'

interface Dataset {
  id: string
  name: string
  dataset_id?: string
  data_source_name?: string
}

interface Step3ConfirmProps {
  parseResult: ParseRuleResponse
  draft: NLRuleDraft
  onDraftChange: (partial: Partial<NLRuleDraft>) => void
  datasets: Dataset[]
  onSubmitProposal: (datasetId?: string, schedule?: ScheduleConfig) => void
  isSubmitting: boolean
  onBack: () => void
}

export default function Step3Confirm({
  parseResult,
  draft,
  onDraftChange,
  datasets,
  onSubmitProposal,
  isSubmitting,
  onBack,
}: Step3ConfirmProps) {
  const configs = parseResult.check_configs ?? []
  const hasConfigs = configs.length > 0
  const { workspace_id } = useParams<{ workspace_id: string }>()

  // Spec §12 / §16 — Submit must be blocked unless the proposal is
  // convertible into a valid DQ flow.
  const flowValid = parseResult.validation?.dq_flow_convertible !== false
  const blockSubmit = !flowValid
  const validationErrors = parseResult.validation?.errors ?? []
  const refinementMessage = parseResult.refinement?.message ?? null

  // E3 — test-on-sample state
  const [testIndex, setTestIndex] = useState(0)
  const [testLoading, setTestLoading] = useState(false)
  const [testError, setTestError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<TestPreviewResponse | null>(null)

  const canTest =
    !!workspace_id && !!parseResult.parse_result_id && hasConfigs

  async function runTest() {
    if (!workspace_id || !parseResult.parse_result_id) return
    setTestLoading(true)
    setTestError(null)
    setTestResult(null)
    try {
      const res = await testParseOnSample(
        workspace_id,
        parseResult.parse_result_id,
        { check_index: testIndex, sample_size: 50, violation_limit: 10 },
      )
      setTestResult(res)
    } catch (err: any) {
      setTestError(
        err?.response?.data?.detail ?? err?.message ?? 'Test failed',
      )
    } finally {
      setTestLoading(false)
    }
  }

  return (
    <div className="space-y-6" data-testid="step3-confirm">
      {/* Rule summary header */}
      {parseResult.parsed_rule && (
        <div className="rounded-lg border border-dark-700 bg-dark-800/50 px-4 py-3 text-sm text-gray-300">
          <span className="font-semibold">Rule Type:</span>{' '}
          <span>{parseResult.parsed_rule.rule_type}</span>
          {' — '}
          <span className="font-semibold">Subject:</span>{' '}
          <span>{parseResult.parsed_rule.subject.raw_text}</span>
        </div>
      )}

      {/* Compiled check config preview */}
      <div>
        <h3 className="text-sm font-semibold text-gray-100 mb-2">Check Configurations</h3>
        <CompiledConfigPreview configs={configs} />
      </div>

      {/* Dataset assignment */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-100 mb-3">Dataset Assignment</h3>
        <ContextPanel
          draft={draft}
          onChange={onDraftChange}
          datasets={datasets}
        />
      </div>

      {/* E3 — Test on sample */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-100 flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-primary-400" />
            Test on sample data
          </h3>
          {configs.length > 1 && (
            <select
              value={testIndex}
              onChange={(e) => setTestIndex(Number(e.target.value))}
              className="bg-dark-800 border border-dark-700 text-xs text-gray-200 rounded px-2 py-1"
              data-testid="test-check-select"
            >
              {configs.map((c, i) => (
                <option key={i} value={i}>
                  #{i + 1} — {c.rule_name || `${c.check_dimension}/${c.check_subtype}`}
                </option>
              ))}
            </select>
          )}
        </div>
        <div className="flex items-center gap-3 mb-3">
          <button
            type="button"
            onClick={runTest}
            disabled={!canTest || testLoading}
            className="btn btn-secondary flex items-center gap-2 text-sm"
            data-testid="run-test-btn"
          >
            {testLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <FlaskConical className="w-4 h-4" />
            )}
            Run test
          </button>
          {!parseResult.parse_result_id && (
            <span className="text-xs text-gray-500">
              Save the parse to enable testing.
            </span>
          )}
        </div>

        {testError && (
          <div
            role="alert"
            className="rounded border border-red-500/40 bg-red-900/20 text-sm text-red-300 px-3 py-2"
          >
            {testError}
          </div>
        )}

        {testResult && (
          <div className="space-y-3" data-testid="test-result-panel">
            {testResult.status === 'success' && testResult.statistics ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Stat label="Total rows" value={testResult.statistics.total_rows} />
                <Stat
                  label="Passed"
                  value={testResult.statistics.rows_passed}
                  tone="good"
                />
                <Stat
                  label="Failed"
                  value={testResult.statistics.rows_failed}
                  tone={testResult.statistics.rows_failed > 0 ? 'bad' : 'good'}
                />
                <Stat
                  label="Pass rate"
                  value={`${testResult.statistics.pass_rate.toFixed(1)}%`}
                />
              </div>
            ) : (
              <div
                role="alert"
                className="rounded border border-red-500/40 bg-red-900/20 text-sm text-red-300 px-3 py-2 flex items-start gap-2"
              >
                <AlertTriangle className="w-4 h-4 mt-0.5" />
                <span>{testResult.error_message || 'Test reported an error'}</span>
              </div>
            )}

            {testResult.expression && (
              <div className="rounded border border-dark-700 bg-dark-900 px-3 py-2">
                <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">
                  Expression
                </div>
                <code className="text-xs text-gray-200 break-all">
                  {testResult.expression}
                </code>
              </div>
            )}

            {testResult.warnings.length > 0 && (
              <ul className="text-xs text-yellow-300 list-disc list-inside space-y-0.5">
                {testResult.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}

            {testResult.violations.length > 0 ? (
              <div>
                <div className="text-xs font-semibold text-gray-300 mb-1">
                  Example violating rows ({testResult.violations.length})
                </div>
                <div className="rounded border border-dark-700 overflow-x-auto">
                  <table className="text-xs w-full">
                    <thead className="bg-dark-800 text-gray-400">
                      <tr>
                        {Object.keys(testResult.violations[0]).slice(0, 8).map((k) => (
                          <th key={k} className="px-2 py-1 text-left">{k}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {testResult.violations.slice(0, 10).map((row, ri) => (
                        <tr key={ri} className="odd:bg-dark-900/50">
                          {Object.keys(testResult.violations[0]).slice(0, 8).map((k) => (
                            <td key={k} className="px-2 py-1 font-mono text-gray-300">
                              {String(row[k] ?? '')}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : testResult.status === 'success' ? (
              <div className="text-xs text-green-400 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                No violations found in sample.
              </div>
            ) : null}
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex gap-3 flex-wrap">
        <button
          onClick={onBack}
          className="btn btn-secondary"
          data-testid="step3-back-btn"
        >
          Back
        </button>

        <button
          onClick={() => onSubmitProposal(draft.dataset_id || undefined)}
          disabled={!hasConfigs || isSubmitting || blockSubmit}
          className="btn btn-primary flex items-center gap-2"
          data-testid="submit-proposal-btn"
          title={
            blockSubmit
              ? refinementMessage ??
                'Rule proposal cannot be converted to a valid DQ flow yet.'
              : undefined
          }
        >
          {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
          Submit as Proposal
        </button>
      </div>

      {/* Validation / refinement banner — surfaced near Submit per spec §16. */}
      {blockSubmit && (
        <div
          className="rounded-lg border border-amber-800 bg-dark-800 px-4 py-3 text-sm text-amber-300"
          role="alert"
          data-testid="proposal-blocked-banner"
        >
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <div className="space-y-1">
              <div className="font-medium">
                {refinementMessage ??
                  'This rule proposal cannot be saved yet — refine it before submitting.'}
              </div>
              {validationErrors.length > 0 && (
                <ul className="list-disc pl-5 text-xs text-amber-200/80">
                  {validationErrors.map((err, idx) => (
                    <li key={idx}>{err}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: string | number
  tone?: 'good' | 'bad'
}) {
  const toneClass =
    tone === 'good'
      ? 'text-green-400'
      : tone === 'bad'
      ? 'text-red-400'
      : 'text-gray-100'
  return (
    <div className="rounded border border-dark-700 bg-dark-900 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`text-base font-semibold ${toneClass}`}>{value}</div>
    </div>
  )
}
