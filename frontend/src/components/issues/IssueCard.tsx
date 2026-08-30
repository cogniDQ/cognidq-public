// F031 P05 / F033 P03 — IssueCard component

import { Link } from 'react-router-dom'
import SeverityBadge from './SeverityBadge'
import { useTenantScopedPath } from '../../hooks/useTenantScopedPath'
import type { IssueListItem } from '../../types/issue'

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function isDueOverdue(dueAt: string): boolean {
  return new Date(dueAt).getTime() < Date.now()
}

interface IssueCardProps {
  issue: IssueListItem
}

export default function IssueCard({ issue }: IssueCardProps) {
  const overdue = issue.due_at ? isDueOverdue(issue.due_at) && !['closed', 'resolved'].includes(issue.status) : false
  const { wsPath } = useTenantScopedPath()

  return (
    <tr
      className={`border-b border-gray-700/50 hover:bg-gray-800/40 transition-colors ${overdue ? 'bg-red-900/20' : ''}`}
      data-testid="issue-card"
    >
      <td className="px-4 py-3">
        <SeverityBadge severity={issue.severity} />
      </td>
      <td className="px-4 py-3 text-sm text-gray-200 max-w-xs truncate">
        <Link
          to={wsPath(issue.workspace_id, `/issues/${issue.id}`)}
          className="text-orange-400 hover:text-orange-300 transition-colors"
          data-testid="issue-title-link"
        >
          {issue.title}
        </Link>
      </td>
      <td className="px-4 py-3 text-sm text-gray-400">{issue.issue_type}</td>
      <td className="px-4 py-3 text-sm text-gray-400">{issue.status}</td>
      <td className="px-4 py-3 text-sm text-gray-400" data-testid="assignee-cell">
        {issue.assignee_display_name ?? <span className="text-gray-600">Unassigned</span>}
      </td>
      <td className="px-4 py-3 text-sm text-gray-400" data-testid="dataset-cell">
        {issue.dataset_name ?? <span className="text-gray-600">—</span>}
      </td>
      <td className="px-4 py-3 text-sm text-gray-400">
        {issue.opened_at ? relativeTime(issue.opened_at) : '—'}
      </td>
      <td className="px-4 py-3 text-sm">
        {issue.due_at ? (
          <span className={overdue ? 'text-red-400' : 'text-gray-400'}>
            {overdue && <span className="inline-block mr-1 px-1.5 py-0.5 text-xs font-semibold bg-red-500/20 text-red-400 rounded" data-testid="overdue-badge">OVERDUE</span>}
            {new Date(issue.due_at).toLocaleString()}
          </span>
        ) : (
          <span className="text-gray-600">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-sm text-gray-400">
        {issue.failure_count ?? '—'}
      </td>
      <td className="px-4 py-3 text-sm text-gray-400 max-w-xs truncate">
        {issue.impact_summary ?? '—'}
      </td>
    </tr>
  )
}
