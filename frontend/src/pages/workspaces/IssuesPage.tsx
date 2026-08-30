// F031 P05 / F037 P03 — IssuesPage (workspace-scoped, paginated, filterable, sortable)

import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Download, ChevronUp, ChevronDown, Inbox, Plus, FileText, Sparkles } from 'lucide-react'
import toast from 'react-hot-toast'
import { listIssues, exportIssuesCsv } from '../../services/issuesService'
import { loadWorkspaceDemoData } from '../../services/workspaceDemoData'
import IssueCard from '../../components/issues/IssueCard'
import EmptyState from '../../components/common/EmptyState'
import { useTenantScopedPath } from '../../hooks/useTenantScopedPath'
import type { IssueSeverity, IssueStatus, SortColumn, SortDir } from '../../types/issue'

const STATUSES: IssueStatus[] = ['open', 'in_progress', 'resolved', 'closed', 'reopened']
const SEVERITIES: IssueSeverity[] = ['critical', 'major', 'minor', 'informational']

export default function IssuesPage() {
  const { workspace_id } = useParams<{ workspace_id: string }>()
  const { wsPath } = useTenantScopedPath()
  const [searchParams, setSearchParams] = useSearchParams()
  const [exporting, setExporting] = useState(false)

  const page = parseInt(searchParams.get('page') ?? '1', 10)
  const statusFilter = (searchParams.get('status') ?? '') as IssueStatus | ''
  const severityFilter = (searchParams.get('severity') ?? '') as IssueSeverity | ''
  const assigneeFilter = searchParams.get('assignee_id') ?? ''
  const datasetFilter = searchParams.get('dataset_id') ?? ''
  const overdueFilter = searchParams.get('overdue') === 'true'
  const sortBy = (searchParams.get('sort_by') ?? '') as SortColumn | ''
  const sortDir = (searchParams.get('sort_dir') ?? '') as SortDir | ''

  const hasAnyFilter = !!(statusFilter || severityFilter || assigneeFilter || datasetFilter || overdueFilter)

  const queryParams = {
    page,
    page_size: 25,
    ...(statusFilter ? { status: statusFilter } : {}),
    ...(severityFilter ? { severity: severityFilter } : {}),
    ...(assigneeFilter ? { assignee_id: assigneeFilter } : {}),
    ...(datasetFilter ? { dataset_id: datasetFilter } : {}),
    ...(overdueFilter ? { overdue: true } : {}),
    ...(sortBy ? { sort_by: sortBy } : {}),
    ...(sortDir ? { sort_dir: sortDir } : {}),
  }

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['issues', workspace_id, queryParams],
    queryFn: () => listIssues(workspace_id!, queryParams),
    enabled: !!workspace_id,
    staleTime: 30_000,
  })

  const queryClient = useQueryClient()
  const [seeding, setSeeding] = useState(false)
  async function handleLoadSample() {
    if (!workspace_id || seeding) return
    setSeeding(true)
    try {
      await loadWorkspaceDemoData(workspace_id)
      toast.success('Sample data loaded.')
      await queryClient.invalidateQueries({ queryKey: ['issues', workspace_id] })
      refetch()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Failed to load sample data.')
    } finally {
      setSeeding(false)
    }
  }

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('page')
    setSearchParams(next)
  }

  function clearFilters() {
    const next = new URLSearchParams()
    if (sortBy) next.set('sort_by', sortBy)
    if (sortDir) next.set('sort_dir', sortDir)
    setSearchParams(next)
  }

  function toggleSort(col: SortColumn) {
    const next = new URLSearchParams(searchParams)
    if (sortBy === col) {
      // toggle direction, or remove sort on third click
      if (sortDir === 'asc') {
        next.set('sort_dir', 'desc')
      } else {
        next.delete('sort_by')
        next.delete('sort_dir')
      }
    } else {
      next.set('sort_by', col)
      next.set('sort_dir', 'asc')
    }
    next.delete('page')
    setSearchParams(next)
  }

  function sortIndicator(col: SortColumn) {
    if (sortBy !== col) return null
    return sortDir === 'asc'
      ? <ChevronUp className="inline w-3 h-3 ml-0.5" data-testid={`sort-asc-${col}`} />
      : <ChevronDown className="inline w-3 h-3 ml-0.5" data-testid={`sort-desc-${col}`} />
  }

  async function handleExport() {
    if (!workspace_id || exporting) return
    setExporting(true)
    try {
      await exportIssuesCsv(workspace_id, queryParams)
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          to={`/workspaces/${workspace_id}`}
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Workspace
        </Link>
        <h1 className="text-xl font-semibold text-white">Issues</h1>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={statusFilter}
          onChange={(e) => setParam('status', e.target.value)}
          className="rounded-lg border border-gray-600 bg-gray-800 px-3 py-1.5 text-sm text-gray-200"
          data-testid="status-filter"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        <select
          value={severityFilter}
          onChange={(e) => setParam('severity', e.target.value)}
          className="rounded-lg border border-gray-600 bg-gray-800 px-3 py-1.5 text-sm text-gray-200"
          data-testid="severity-filter"
        >
          <option value="">All severities</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        <input
          type="text"
          value={assigneeFilter}
          onChange={(e) => setParam('assignee_id', e.target.value)}
          placeholder="Assignee ID or 'unassigned'"
          className="rounded-lg border border-gray-600 bg-gray-800 px-3 py-1.5 text-sm text-gray-200 w-56"
          data-testid="assignee-filter"
        />

        <input
          type="text"
          value={datasetFilter}
          onChange={(e) => setParam('dataset_id', e.target.value)}
          placeholder="Dataset ID"
          className="rounded-lg border border-gray-600 bg-gray-800 px-3 py-1.5 text-sm text-gray-200 w-56"
          data-testid="dataset-filter"
        />

        <label className="flex items-center gap-1.5 text-sm text-gray-300 cursor-pointer">
          <input
            type="checkbox"
            checked={overdueFilter}
            onChange={(e) => setParam('overdue', e.target.checked ? 'true' : '')}
            className="rounded border-gray-600 bg-gray-800"
            data-testid="overdue-filter"
          />
          Overdue only
        </label>

        {hasAnyFilter && (
          <button
            onClick={clearFilters}
            className="px-3 py-1.5 text-sm text-gray-400 hover:text-white transition-colors"
            data-testid="clear-filters"
          >
            Clear filters
          </button>
        )}

        <button
          onClick={handleExport}
          disabled={exporting}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-600 bg-gray-800 text-sm text-gray-200 hover:bg-gray-700 disabled:opacity-40 transition-colors"
          data-testid="export-csv"
        >
          <Download className="w-4 h-4" />
          {exporting ? 'Exporting…' : 'Export CSV'}
        </button>
      </div>

      {/* Content */}
      {isLoading && (
        <div className="space-y-3" data-testid="issues-skeleton">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-12 rounded-lg bg-gray-700/30 animate-pulse" />
          ))}
        </div>
      )}

      {isError && (
        <EmptyState
          variant="error"
          title="Couldn't load issues"
          description="We hit a snag fetching this workspace's issues. The data couldn't be reached — try again, or check your connection."
          onRetry={() => refetch()}
          testId="issues-error"
        />
      )}

      {data && data.items.length === 0 && (
        hasAnyFilter ? (
          <EmptyState
            icon={Inbox}
            title="No issues match these filters"
            description="Try clearing one of your filters to widen the search."
            primaryAction={{
              label: 'Clear filters',
              onClick: () => setSearchParams(new URLSearchParams()),
            }}
            testId="issues-empty-filtered"
          />
        ) : (
          <EmptyState
            icon={Inbox}
            title="No open issues yet"
            description="Issues are created automatically when a rule fails. Run a flow to start surfacing data-quality problems, or load a small sample dataset to explore the platform."
            primaryAction={{
              label: 'Open Flows',
              to: wsPath(workspace_id ?? '', '/flows'),
              icon: Plus,
            }}
            secondaryAction={{
              label: 'View Rules',
              to: wsPath(workspace_id ?? '', '/rules'),
              icon: FileText,
            }}
            tertiaryAction={{
              label: seeding ? 'Loading…' : 'Load sample data',
              onClick: handleLoadSample,
              icon: Sparkles,
            }}
            testId="issues-empty"
          />
        )
      )}

      {data && data.items.length > 0 && (
        <div className="overflow-x-auto rounded-2xl border border-gray-700 bg-gray-800/60">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-700 text-xs text-gray-400 uppercase tracking-wide">
                <th className="px-4 py-3 cursor-pointer select-none" onClick={() => toggleSort('severity')} data-testid="sort-severity">
                  Severity{sortIndicator('severity')}
                </th>
                <th className="px-4 py-3">Title</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3 cursor-pointer select-none" onClick={() => toggleSort('status')} data-testid="sort-status">
                  Status{sortIndicator('status')}
                </th>
                <th className="px-4 py-3">Assignee</th>
                <th className="px-4 py-3">Dataset</th>
                <th className="px-4 py-3 cursor-pointer select-none" onClick={() => toggleSort('opened_at')} data-testid="sort-opened_at">
                  Opened{sortIndicator('opened_at')}
                </th>
                <th className="px-4 py-3 cursor-pointer select-none" onClick={() => toggleSort('due_at')} data-testid="sort-due_at">
                  Due{sortIndicator('due_at')}
                </th>
                <th className="px-4 py-3">Failures</th>
                <th className="px-4 py-3">Impact</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((issue) => (
                <IssueCard key={issue.id} issue={issue} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {data && data.total > 0 && (
        <div className="flex items-center justify-between text-sm text-gray-400">
          <span>
            Page {data.page} — {data.total} issue{data.total !== 1 ? 's' : ''} total
          </span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => {
                const next = new URLSearchParams(searchParams)
                next.set('page', String(page - 1))
                setSearchParams(next)
              }}
              className="px-3 py-1 rounded border border-gray-600 bg-gray-800 disabled:opacity-40 hover:bg-gray-700 transition-colors"
            >
              Previous
            </button>
            <button
              disabled={!data.has_next}
              onClick={() => {
                const next = new URLSearchParams(searchParams)
                next.set('page', String(page + 1))
                setSearchParams(next)
              }}
              className="px-3 py-1 rounded border border-gray-600 bg-gray-800 disabled:opacity-40 hover:bg-gray-700 transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
