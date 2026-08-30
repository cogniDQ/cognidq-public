// F033 P03 + F035 P04 — IssueDetailPage with mutation controls

import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { ArrowLeft, AlertTriangle, Eye } from 'lucide-react'
import { getIssue, updateIssue } from '../../services/issuesService'
import SeverityBadge from '../../components/issues/SeverityBadge'
import IssueTimeline from '../../components/issues/IssueTimeline'
import EscalateToIncidentModal from '../../components/issues/EscalateToIncidentModal'
import EvidencePanel from '../../components/issues/EvidencePanel'
import FaultyRecordsModal from '../../components/common/FaultyRecordsModal'
import type { IssueStatus, IssueUpdatePayload } from '../../types/issue'
import { ALLOWED_TRANSITIONS, RESOLUTION_REQUIRED_STATUSES } from '../../types/issue'

const INCIDENT_SEVERITY_FOR_ISSUE: Record<string, 'critical' | 'major' | 'minor' | 'informational'> = {
  critical: 'critical',
  major: 'major',
  high: 'major',
  minor: 'minor',
  low: 'minor',
  medium: 'minor',
  informational: 'informational',
}

function slaLabel(dueAt: string | null): { text: string; tone: 'overdue' | 'soon' | 'ok' } | null {
  if (!dueAt) return null
  const now = Date.now()
  const due = new Date(dueAt).getTime()
  const diffH = (due - now) / 3_600_000
  if (diffH < 0) return { text: `Overdue by ${Math.abs(Math.round(diffH))}h`, tone: 'overdue' }
  if (diffH < 24) return { text: `Due in ${Math.round(diffH)}h`, tone: 'soon' }
  if (diffH < 72) return { text: `Due in ${Math.round(diffH / 24)}d`, tone: 'soon' }
  return { text: `Due in ${Math.round(diffH / 24)}d`, tone: 'ok' }
}

const STATUS_STYLES: Record<string, string> = {
  open: 'text-blue-400 bg-blue-400/10 border-blue-400/30',
  in_progress: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30',
  resolved: 'text-green-400 bg-green-400/10 border-green-400/30',
  closed: 'text-gray-400 bg-gray-400/10 border-gray-400/30',
  reopened: 'text-orange-400 bg-orange-400/10 border-orange-400/30',
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

function isDueOverdue(dueAt: string | null): boolean {
  if (!dueAt) return false
  return new Date(dueAt).getTime() < Date.now()
}

export default function IssueDetailPage() {
  const { workspace_id, issue_id } = useParams<{
    workspace_id: string
    issue_id: string
  }>()

  const qc = useQueryClient()
  const queryKey = ['issue', workspace_id, issue_id]

  const { data: issue, isLoading, isError } = useQuery({
    queryKey,
    queryFn: () => getIssue(workspace_id!, issue_id!),
    enabled: !!workspace_id && !!issue_id,
    staleTime: 30_000,
  })

  // F035 — mutation state
  const [dueAtInput, setDueAtInput] = useState('')
  const [resolutionInput, setResolutionInput] = useState('')
  const [pendingStatus, setPendingStatus] = useState<IssueStatus | null>(null)
  const [escalateOpen, setEscalateOpen] = useState(false)
  const [faultyOpen, setFaultyOpen] = useState(false)

  const mutation = useMutation({
    mutationFn: (payload: IssueUpdatePayload) =>
      updateIssue(workspace_id!, issue_id!, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey })
      qc.invalidateQueries({ queryKey: ['issues', workspace_id] })
      toast.success('Issue updated')
      setPendingStatus(null)
      setResolutionInput('')
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      toast.error(detail ?? 'Failed to update issue')
    },
  })

  function handleStatusChange(newStatus: IssueStatus) {
    if (RESOLUTION_REQUIRED_STATUSES.has(newStatus) && !issue?.resolution_summary) {
      setPendingStatus(newStatus)
      return
    }
    mutation.mutate({ status: newStatus })
  }

  function handleResolutionSubmit() {
    if (!resolutionInput.trim() || !pendingStatus) return
    mutation.mutate({ status: pendingStatus, resolution_summary: resolutionInput.trim() })
  }

  function handleDueDateSave() {
    mutation.mutate({ due_at: dueAtInput || null })
  }

  function handleUnassign() {
    mutation.mutate({ assignee_id: null })
  }

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse" data-testid="issue-detail-loading">
        <div className="h-8 w-64 rounded-lg bg-gray-800" />
        <div className="h-48 rounded-2xl bg-gray-800/60" />
        <div className="grid grid-cols-2 gap-4">
          <div className="h-32 rounded-2xl bg-gray-800/60" />
          <div className="h-32 rounded-2xl bg-gray-800/60" />
        </div>
      </div>
    )
  }

  if (isError || !issue) {
    return (
      <div data-testid="issue-detail-error">
        <Link
          to={`/workspaces/${workspace_id}/issues`}
          className="mb-4 flex items-center gap-1 text-sm text-gray-400 hover:text-white"
        >
          <ArrowLeft className="w-4 h-4" /> Back to issues
        </Link>
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400 text-sm">
          Issue not found.
        </div>
      </div>
    )
  }

  const statusStyle = STATUS_STYLES[issue.status] ?? STATUS_STYLES.open

  return (
    <div className="space-y-6" data-testid="issue-detail">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          to={`/workspaces/${workspace_id}/issues`}
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Issues
        </Link>
        <SeverityBadge severity={issue.severity} />
        <h1 className="text-xl font-semibold text-white">{issue.title}</h1>
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${statusStyle}`}
          data-testid="status-badge"
        >
          {issue.status}
        </span>
        {(() => {
          const sla = slaLabel(issue.due_at)
          if (!sla) return null
          const tone =
            sla.tone === 'overdue'
              ? 'bg-danger-soft text-danger ring-danger/30'
              : sla.tone === 'soon'
              ? 'bg-warning-soft text-warning ring-warning/30'
              : 'bg-success-soft text-success ring-success/30'
          return (
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${tone}`}
              data-testid="sla-pill"
            >
              {sla.tone === 'overdue' ? <AlertTriangle className="h-3 w-3" /> : null}
              {sla.text}
            </span>
          )
        })()}
        <div className="flex-1" />
        {issue.status !== 'resolved' && issue.status !== 'closed' ? (
          <button
            data-testid="escalate-btn"
            onClick={() => setEscalateOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-warning/40 bg-warning-soft px-3 py-1.5 text-xs font-semibold text-warning transition-colors hover:bg-warning hover:text-white"
          >
            <AlertTriangle className="h-3.5 w-3.5" />
            Escalate to incident
          </button>
        ) : null}
      </div>

      {/* F035 — Mutation Panel */}
      <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-4 space-y-4" data-testid="mutation-panel">
        <h3 className="text-sm font-medium text-gray-300">Actions</h3>

        {/* Status Transition */}
        <div data-testid="status-transition">
          <span className="text-xs text-gray-400 block mb-1">Transition Status</span>
          <div className="flex flex-wrap gap-2">
            {ALLOWED_TRANSITIONS[issue.status]?.map((target) => (
              <button
                key={target}
                data-testid={`transition-${target}`}
                disabled={mutation.isPending}
                onClick={() => handleStatusChange(target)}
                className="px-3 py-1 rounded-lg text-xs font-medium border border-gray-600 bg-gray-900 text-gray-300 hover:bg-gray-700 hover:text-white transition-colors disabled:opacity-50"
              >
                {target.replace('_', ' ')}
              </button>
            ))}
          </div>
        </div>

        {/* Resolution Summary (shown when resolving/closing without pre-existing summary) */}
        {pendingStatus && (
          <div data-testid="resolution-prompt">
            <label htmlFor="resolution-summary" className="text-xs text-gray-400 block mb-1">
              Resolution Summary (required for {pendingStatus.replace('_', ' ')})
            </label>
            <textarea
              id="resolution-summary"
              data-testid="resolution-input"
              value={resolutionInput}
              onChange={(e) => setResolutionInput(e.target.value)}
              maxLength={5000}
              rows={3}
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="Describe the resolution..."
            />
            <div className="flex gap-2 mt-2">
              <button
                data-testid="resolution-submit"
                disabled={mutation.isPending || !resolutionInput.trim()}
                onClick={handleResolutionSubmit}
                className="px-3 py-1 rounded-lg text-xs font-medium bg-purple-600 text-white hover:bg-purple-500 transition-colors disabled:opacity-50"
              >
                {mutation.isPending ? 'Saving…' : 'Submit'}
              </button>
              <button
                data-testid="resolution-cancel"
                onClick={() => { setPendingStatus(null); setResolutionInput('') }}
                className="px-3 py-1 rounded-lg text-xs font-medium border border-gray-600 text-gray-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Due Date */}
        <div data-testid="due-date-control">
          <label htmlFor="due-at-input" className="text-xs text-gray-400 block mb-1">Due Date</label>
          <div className="flex gap-2">
            <input
              id="due-at-input"
              data-testid="due-at-input"
              type="date"
              value={dueAtInput}
              onChange={(e) => setDueAtInput(e.target.value)}
              className="bg-gray-900 border border-gray-600 rounded-lg px-3 py-1 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <button
              data-testid="due-at-save"
              disabled={mutation.isPending}
              onClick={handleDueDateSave}
              className="px-3 py-1 rounded-lg text-xs font-medium border border-gray-600 text-gray-300 hover:text-white transition-colors disabled:opacity-50"
            >
              Save
            </button>
          </div>
        </div>

        {/* Unassign */}
        {issue.assignee && (
          <div>
            <button
              data-testid="unassign-btn"
              disabled={mutation.isPending}
              onClick={handleUnassign}
              className="px-3 py-1 rounded-lg text-xs font-medium border border-gray-600 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
            >
              Unassign {issue.assignee.display_name}
            </button>
          </div>
        )}
      </div>

      {/* Resolution Summary Display */}
      {issue.resolution_summary && (
        <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-4" data-testid="resolution-card">
          <h3 className="text-sm font-medium text-gray-400 mb-2">Resolution Summary</h3>
          <p className="text-gray-200 text-sm">{issue.resolution_summary}</p>
        </div>
      )}

      {/* Timestamps & Impact */}
      <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-4 space-y-3">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-400">Opened</span>
            <p className="text-gray-200">{formatDate(issue.opened_at)}</p>
          </div>
          <div>
            <span className="text-gray-400">Due</span>
            <p className={isDueOverdue(issue.due_at) ? 'text-red-400 font-medium' : 'text-gray-200'} data-testid="due-date">
              {formatDate(issue.due_at)}
              {isDueOverdue(issue.due_at) && <span className="ml-1 text-xs" data-testid="overdue-indicator">OVERDUE</span>}
            </p>
          </div>
          <div>
            <span className="text-gray-400">Resolved</span>
            <p className="text-gray-200">{formatDate(issue.resolved_at)}</p>
          </div>
          <div>
            <span className="text-gray-400">Closed</span>
            <p className="text-gray-200">{formatDate(issue.closed_at)}</p>
          </div>
        </div>
        {issue.impact_summary && (
          <div>
            <span className="text-gray-400 text-sm">Impact</span>
            <p className="text-gray-200 text-sm">{issue.impact_summary}</p>
          </div>
        )}
        <div className="grid grid-cols-3 gap-4 text-sm pt-2 border-t border-gray-700">
          <div>
            <span className="text-gray-400">Failures</span>
            <p className="text-gray-200 font-medium">{issue.failure_count ?? '—'}</p>
          </div>
          <div>
            <span className="text-gray-400">Rows Scanned</span>
            <p className="text-gray-200 font-medium">{issue.rows_scanned ?? '—'}</p>
          </div>
          <div>
            <span className="text-gray-400">Pass Rate</span>
            <p className="text-gray-200 font-medium">
              {issue.pass_rate != null ? `${issue.pass_rate}%` : '—'}
            </p>
          </div>
        </div>
      </div>

      {/* Context Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Rule Card */}
        <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-4" data-testid="rule-card">
          <h3 className="text-sm font-medium text-gray-400 mb-2">Rule</h3>
          {issue.rule ? (
            <div className="space-y-1 text-sm">
              <p className="text-gray-200 font-medium">
                <Link
                  to={`/workspaces/${workspace_id}/rules`}
                  className="text-orange-400 hover:text-orange-300 transition-colors"
                  data-testid="rule-link"
                >
                  {issue.rule.name}
                </Link>
              </p>
              <p className="text-gray-400">Category: {issue.rule.category ?? '—'}</p>
              <p className="text-gray-400">Severity: {issue.rule.severity ?? '—'}</p>
              <p className="text-gray-400">Target: {issue.rule.target_table ?? '—'}</p>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">Rule not available</p>
          )}
        </div>

        {/* Dataset Card */}
        <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-4" data-testid="dataset-card">
          <h3 className="text-sm font-medium text-gray-400 mb-2">Dataset</h3>
          {issue.dataset ? (
            <div className="space-y-1 text-sm">
              <p className="text-gray-200 font-medium">
                <Link
                  to={`/workspaces/${workspace_id}/datasets`}
                  className="text-orange-400 hover:text-orange-300 transition-colors"
                  data-testid="dataset-link"
                >
                  {issue.dataset.dataset_name}
                </Link>
              </p>
              <p className="text-gray-400">Domain: {issue.dataset.business_domain ?? '—'}</p>
              <p className="text-gray-400">Criticality: {issue.dataset.criticality ?? '—'}</p>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">Dataset not available</p>
          )}
        </div>

        {/* Execution Card */}
        <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-4" data-testid="execution-card">
          <h3 className="text-sm font-medium text-gray-400 mb-2">Flow Execution</h3>
          {issue.flow_execution ? (
            <div className="space-y-1 text-sm">
              <p className="text-gray-200 font-medium">{issue.flow_execution.flow_name ?? 'Unknown flow'}</p>
              <p className="text-gray-400">Status: {issue.flow_execution.status ?? '—'}</p>
              <p className="text-gray-400">Started: {formatDate(issue.flow_execution.started_at)}</p>
              <p className="text-gray-400">
                Nodes: {issue.flow_execution.nodes_total ?? 0} total,{' '}
                {issue.flow_execution.nodes_passed ?? 0} passed,{' '}
                {issue.flow_execution.nodes_failed ?? 0} failed
              </p>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">Execution not available</p>
          )}
        </div>

        {/* Node Result Card */}
        <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-4" data-testid="node-result-card">
          <h3 className="text-sm font-medium text-gray-400 mb-2">Node Result</h3>
          {issue.node_result ? (
            <div className="space-y-1 text-sm">
              <p className="text-gray-200 font-medium">{issue.node_result.node_id}</p>
              <p className="text-gray-400">Type: {issue.node_result.node_type ?? '—'}</p>
              <p className="text-gray-400">Status: {issue.node_result.status ?? '—'}</p>
              <p className="text-gray-400">
                Rows: {issue.node_result.rows_scanned ?? 0} scanned,{' '}
                {issue.node_result.rows_passed ?? 0} passed,{' '}
                {issue.node_result.rows_failed ?? 0} failed
              </p>
              <p className="text-gray-400">
                Pass Rate: {issue.node_result.pass_rate != null ? `${issue.node_result.pass_rate}%` : '—'}
              </p>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">Node result not available</p>
          )}
        </div>
      </div>

      {/* Assignee */}
      <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-4" data-testid="assignee-card">
        <h3 className="text-sm font-medium text-gray-400 mb-2">Assignee</h3>
        {issue.assignee ? (
          <div className="text-sm">
            <p className="text-gray-200 font-medium">{issue.assignee.display_name}</p>
            <p className="text-gray-400">{issue.assignee.email}</p>
          </div>
        ) : (
          <p className="text-gray-500 text-sm">Unassigned</p>
        )}
      </div>

      {/* F036 — Comments + activity timeline */}
      <IssueTimeline workspaceId={workspace_id!} issueId={issue_id!} />

      {/* Sprint 4.2 — Evidence panel (SQL + violations + sample) */}
      {issue.node_result ? <EvidencePanel nodeResult={issue.node_result} /> : null}

      {/* F034 — open the captured (masked) failing-record sample */}
      {(issue.failure_count ?? issue.node_result?.rows_failed ?? 0) > 0 && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => setFaultyOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-1.5 text-sm text-red-300 hover:bg-red-500/20"
            data-testid="issue-view-faulty-records"
          >
            <Eye className="w-4 h-4" /> View faulty records
          </button>
        </div>
      )}

      <FaultyRecordsModal
        workspaceId={workspace_id!}
        source={
          faultyOpen
            ? {
                kind: 'issue',
                issueId: issue_id!,
                title: `Faulty records · ${issue.title}`,
                subtitle: [
                  issue.dataset?.dataset_name ?? issue.node_result?.dataset ?? null,
                  issue.rule?.name ?? null,
                  issue.failure_count != null
                    ? `${issue.failure_count.toLocaleString()} failed rows`
                    : null,
                ]
                  .filter(Boolean)
                  .join(' · '),
              }
            : null
        }
        onClose={() => setFaultyOpen(false)}
      />

      {/* Escalate to incident modal */}
      <EscalateToIncidentModal
        workspaceId={workspace_id!}
        issueId={issue_id!}
        defaultTitle={issue.title}
        defaultSeverity={INCIDENT_SEVERITY_FOR_ISSUE[issue.severity] ?? 'major'}
        defaultImpactSummary={issue.impact_summary}
        open={escalateOpen}
        onClose={() => setEscalateOpen(false)}
      />
    </div>
  )
}
