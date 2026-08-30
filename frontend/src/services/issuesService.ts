// F031 P05 — Issue API client functions

import { api } from './api'
import type { IssuePage, IssueDetail, IssueListParams, IssueUpdatePayload } from '../types/issue'

const base = (workspaceId: string) => `/workspaces/${workspaceId}/issues`

// ─── F036 — Comments + Timeline types ─────────────────────────────────────

export interface IssueComment {
  id: string
  issue_id: string
  author_id: string | null
  author_name: string | null
  body: string
  created_at: string | null
}

export interface IssueTimelineEntry {
  entry_type: 'comment' | 'system' | string
  id: string
  timestamp: string | null
  actor_id: string | null
  actor_name: string | null
  content: Record<string, unknown> | string | null
}

export interface IssueTimelinePage {
  items: IssueTimelineEntry[]
  total: number
  page: number
  page_size: number
  has_next: boolean
}

export async function addIssueComment(
  workspaceId: string,
  issueId: string,
  body: string,
): Promise<IssueComment> {
  const res = await api.post<IssueComment>(
    `${base(workspaceId)}/${issueId}/comments`,
    { body },
  )
  return res.data
}

export async function getIssueTimeline(
  workspaceId: string,
  issueId: string,
  page = 1,
  pageSize = 50,
): Promise<IssueTimelinePage> {
  const res = await api.get<IssueTimelinePage>(
    `${base(workspaceId)}/${issueId}/timeline`,
    { params: { page, page_size: pageSize } },
  )
  return res.data
}

export async function listIssues(
  workspaceId: string,
  params: IssueListParams = {},
): Promise<IssuePage> {
  const res = await api.get<IssuePage>(base(workspaceId), { params })
  return res.data
}

export async function getIssue(
  workspaceId: string,
  issueId: string,
): Promise<IssueDetail> {
  const res = await api.get<IssueDetail>(`${base(workspaceId)}/${issueId}`)
  return res.data
}

export async function updateIssue(
  workspaceId: string,
  issueId: string,
  payload: IssueUpdatePayload,
): Promise<IssueDetail> {
  const res = await api.patch<IssueDetail>(`${base(workspaceId)}/${issueId}`, payload)
  return res.data
}

// F034 — captured failing-record sample for an issue (masked, up to 50 rows)
export interface IssueSamplesResponse {
  issue_id: string
  workspace_id: string
  captured_at: string | null
  sample_count: number
  masking_applied: boolean
  masking_threshold: string | null
  rows: Array<Record<string, unknown>>
}

export async function getIssueSamples(
  workspaceId: string,
  issueId: string,
): Promise<IssueSamplesResponse> {
  const res = await api.get<IssueSamplesResponse>(
    `${base(workspaceId)}/${issueId}/samples`,
  )
  return res.data
}

// F037 — CSV export (triggers browser download via Blob)
export async function exportIssuesCsv(
  workspaceId: string,
  params: IssueListParams = {},
): Promise<void> {
  const { page: _page, page_size: _page_size, ...filterParams } = params
  const res = await api.get(`${base(workspaceId)}/export`, {
    params: filterParams,
    responseType: 'blob',
  })
  const blob = new Blob([res.data], { type: 'text/csv; charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const cd = res.headers['content-disposition'] ?? ''
  const match = cd.match(/filename="?([^"]+)"?/)
  a.download = match ? match[1] : 'issues_export.csv'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
