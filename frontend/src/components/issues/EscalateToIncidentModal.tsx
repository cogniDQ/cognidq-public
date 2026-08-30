import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { AlertTriangle, X } from 'lucide-react'
import {
  createIncident,
  type IncidentPriority,
  type IncidentSeverity,
} from '../../services/incidentsService'
import { useTenantScopedPath } from '../../hooks/useTenantScopedPath'

interface Props {
  workspaceId: string
  issueId: string
  defaultTitle: string
  defaultSeverity: IncidentSeverity
  defaultImpactSummary?: string | null
  open: boolean
  onClose: () => void
}

const SEVERITIES: IncidentSeverity[] = ['critical', 'major', 'minor', 'informational']
const PRIORITIES: IncidentPriority[] = ['P1', 'P2', 'P3', 'P4']

const PRIORITY_BY_SEVERITY: Record<IncidentSeverity, IncidentPriority> = {
  critical: 'P1',
  major: 'P2',
  minor: 'P3',
  informational: 'P4',
}

export default function EscalateToIncidentModal({
  workspaceId,
  issueId,
  defaultTitle,
  defaultSeverity,
  defaultImpactSummary,
  open,
  onClose,
}: Props) {
  const navigate = useNavigate()
  const { wsPath } = useTenantScopedPath()
  const qc = useQueryClient()
  const [title, setTitle] = useState(defaultTitle)
  const [severity, setSeverity] = useState<IncidentSeverity>(defaultSeverity)
  const [priority, setPriority] = useState<IncidentPriority>(
    PRIORITY_BY_SEVERITY[defaultSeverity] ?? 'P2',
  )
  const [impact, setImpact] = useState(defaultImpactSummary ?? '')
  const titleInputRef = useRef<HTMLInputElement | null>(null)
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const previouslyFocused = useRef<HTMLElement | null>(null)

  // Focus management: autofocus the title input on open, restore focus on close.
  useEffect(() => {
    if (!open) return
    previouslyFocused.current = document.activeElement as HTMLElement | null
    // Defer to allow render before focusing.
    const t = setTimeout(() => titleInputRef.current?.focus(), 0)
    return () => {
      clearTimeout(t)
      previouslyFocused.current?.focus?.()
    }
  }, [open])

  // ESC closes; basic focus-trap (Tab/Shift+Tab cycle inside dialog).
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key === 'Tab' && dialogRef.current) {
        const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        )
        if (focusables.length === 0) return
        const first = focusables[0]
        const last = focusables[focusables.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const mutation = useMutation({
    mutationFn: () =>
      createIncident(workspaceId, {
        title: title.trim(),
        severity,
        priority,
        impact_summary: impact.trim() || undefined,
        issue_ids: [issueId],
      }),
    onSuccess: (incident) => {
      qc.invalidateQueries({ queryKey: ['incidents', workspaceId] })
      qc.invalidateQueries({ queryKey: ['issue', workspaceId, issueId] })
      toast.success('Incident created')
      onClose()
      navigate(wsPath(workspaceId, `/incidents?incident=${incident.id}`))
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      toast.error(detail ?? 'Failed to escalate issue')
    },
  })

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="escalate-title"
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-t-2xl border border-edge bg-surface-raised p-4 shadow-2xl sm:rounded-2xl sm:p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-warning" />
            <h2 id="escalate-title" className="text-lg font-semibold text-content">
              Escalate to incident
            </h2>
          </div>
          <button
            aria-label="Close"
            onClick={onClose}
            className="rounded-md p-1 text-content-muted hover:bg-surface hover:text-content"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="mb-4 text-sm text-content-muted">
          Create a new incident that links this issue. You can attach more issues from the
          incident page.
        </p>

        <div className="space-y-3">
          <div>
            <label htmlFor="incident-title" className="block text-xs font-medium text-content-muted">
              Title
            </label>
            <input
              id="incident-title"
              ref={titleInputRef}
              data-testid="incident-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              className="mt-1 w-full rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-content focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="incident-severity" className="block text-xs font-medium text-content-muted">
                Severity
              </label>
              <select
                id="incident-severity"
                value={severity}
                onChange={(e) => {
                  const s = e.target.value as IncidentSeverity
                  setSeverity(s)
                  setPriority(PRIORITY_BY_SEVERITY[s] ?? priority)
                }}
                className="mt-1 w-full rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-content focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              >
                {SEVERITIES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="incident-priority" className="block text-xs font-medium text-content-muted">
                Priority
              </label>
              <select
                id="incident-priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value as IncidentPriority)}
                className="mt-1 w-full rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-content focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label htmlFor="incident-impact" className="block text-xs font-medium text-content-muted">
              Impact summary (optional)
            </label>
            <textarea
              id="incident-impact"
              value={impact}
              onChange={(e) => setImpact(e.target.value)}
              maxLength={2000}
              rows={3}
              className="mt-1 w-full resize-y rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-content focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            />
          </div>
        </div>

        <div className="mt-6 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-edge px-3 py-1.5 text-sm font-medium text-content-muted hover:bg-surface hover:text-content"
          >
            Cancel
          </button>
          <button
            data-testid="escalate-submit"
            disabled={!title.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
            className="rounded-lg bg-warning px-4 py-1.5 text-sm font-semibold text-white transition-colors hover:opacity-90 disabled:opacity-50"
          >
            {mutation.isPending ? 'Creating…' : 'Create incident'}
          </button>
        </div>
      </div>
    </div>
  )
}
