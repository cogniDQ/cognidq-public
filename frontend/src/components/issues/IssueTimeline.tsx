import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { MessageSquare, Activity } from 'lucide-react'
import {
  addIssueComment,
  getIssueTimeline,
  type IssueTimelineEntry,
} from '../../services/issuesService'

interface Props {
  workspaceId: string
  issueId: string
}

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

function entryLabel(entry: IssueTimelineEntry): string {
  if (entry.entry_type === 'comment') return 'commented'
  if (typeof entry.content === 'object' && entry.content) {
    const c = entry.content as Record<string, unknown>
    if (typeof c.action === 'string') return c.action.replace(/_/g, ' ')
  }
  return entry.entry_type
}

function entryBody(entry: IssueTimelineEntry): string {
  if (entry.entry_type === 'comment' && typeof entry.content === 'object' && entry.content) {
    const c = entry.content as Record<string, unknown>
    if (typeof c.body === 'string') return c.body
  }
  if (typeof entry.content === 'string') return entry.content
  if (typeof entry.content === 'object' && entry.content) {
    const c = entry.content as Record<string, unknown>
    const summary = (c.summary ?? c.message ?? c.detail) as string | undefined
    if (summary) return summary
  }
  return ''
}

export default function IssueTimeline({ workspaceId, issueId }: Props) {
  const qc = useQueryClient()
  const [draft, setDraft] = useState('')

  const queryKey = ['issue-timeline', workspaceId, issueId]
  const { data, isLoading, isError } = useQuery({
    queryKey,
    queryFn: () => getIssueTimeline(workspaceId, issueId),
    staleTime: 10_000,
  })

  const addComment = useMutation({
    mutationFn: (body: string) => addIssueComment(workspaceId, issueId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey })
      setDraft('')
      toast.success('Comment posted')
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      toast.error(detail ?? 'Failed to add comment')
    },
  })

  return (
    <div className="rounded-2xl border border-edge bg-surface-raised p-4" data-testid="issue-timeline">
      <div className="mb-3 flex items-center gap-2">
        <Activity className="h-4 w-4 text-brand" />
        <h3 className="text-sm font-medium text-content">Activity &amp; comments</h3>
      </div>

      {/* Comment composer */}
      <div className="mb-4 rounded-lg border border-edge bg-surface p-3">
        <label htmlFor="new-comment" className="sr-only">
          Add a comment
        </label>
        <textarea
          id="new-comment"
          data-testid="comment-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            // Ctrl/Cmd+Enter posts the comment.
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && draft.trim() && !addComment.isPending) {
              e.preventDefault()
              addComment.mutate(draft.trim())
            }
          }}
          rows={2}
          cols={40}
          maxLength={5000}
          placeholder="Add a comment…"
          aria-describedby="comment-counter"
          className="block w-full resize-y bg-transparent text-sm text-content placeholder:text-content-subtle focus:outline-none"
        />
        <div className="mt-2 flex items-center justify-between">
          <span id="comment-counter" className="text-xs text-content-subtle" aria-live="polite">
            {draft.length}/5000
          </span>
          <button
            data-testid="comment-submit"
            disabled={!draft.trim() || addComment.isPending}
            onClick={() => addComment.mutate(draft.trim())}
            className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-brand-hover disabled:opacity-50"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            {addComment.isPending ? 'Posting…' : 'Comment'}
          </button>
        </div>
      </div>

      {/* Timeline */}
      {isLoading ? (
        <div className="space-y-3" aria-busy="true">
          <div className="h-12 animate-pulse rounded-lg bg-surface" />
          <div className="h-12 animate-pulse rounded-lg bg-surface" />
        </div>
      ) : isError ? (
        <p className="text-sm text-danger">Failed to load timeline.</p>
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-content-muted">No activity yet. Be the first to comment.</p>
      ) : (
        <ol className="space-y-3" data-testid="timeline-list">
          {data.items.map((entry) => {
            const isComment = entry.entry_type === 'comment'
            const body = entryBody(entry)
            return (
              <li
                key={entry.id}
                className={`rounded-lg border p-3 ${
                  isComment ? 'border-edge bg-surface' : 'border-edge-subtle bg-surface'
                }`}
                data-testid={`timeline-entry-${entry.entry_type}`}
              >
                <div className="flex items-baseline justify-between gap-2 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-content">
                      {entry.actor_name ?? (isComment ? 'Someone' : 'System')}
                    </span>
                    <span className="text-content-muted">{entryLabel(entry)}</span>
                  </div>
                  <span className="text-content-subtle">{formatTime(entry.timestamp)}</span>
                </div>
                {body ? (
                  <p className="mt-1.5 whitespace-pre-wrap text-sm text-content">{body}</p>
                ) : null}
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
