/**
 * F4 — Alerts KQI dashboard.
 *
 * Surfaces key quality indicators for the alerts subsystem in a single panel:
 * status mix, hourly volume, top firing rules, and per-channel health.
 * Renders inside AlertsPage as the "Dashboard" tab.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  RefreshCw,
  TrendingUp,
} from 'lucide-react'
import {
  getNotificationEventMetrics,
  type NotificationEventMetrics,
} from '@/services/notificationEventsService'

interface AlertsDashboardProps {
  workspaceId: string
}

const WINDOW_OPTIONS: Array<{ label: string; value: number }> = [
  { label: '1 hr', value: 1 },
  { label: '24 hrs', value: 24 },
  { label: '7 days', value: 168 },
]

function formatPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`
}

function formatDate(s: string | null): string {
  if (!s) return '—'
  try {
    return new Date(s).toLocaleString()
  } catch {
    return s
  }
}

function maxBucketCount(buckets: NotificationEventMetrics['hourly_buckets']): number {
  return buckets.reduce((m, b) => Math.max(m, b.count), 0)
}

function StatTile({
  icon,
  label,
  value,
  tone,
  testId,
}: {
  icon: React.ReactNode
  label: string
  value: string
  tone?: 'green' | 'red' | 'amber' | 'blue'
  testId?: string
}) {
  const toneClass = {
    green: 'border-green-700/60 bg-green-900/20 text-green-300',
    red: 'border-red-700/60 bg-red-900/20 text-red-300',
    amber: 'border-amber-700/60 bg-amber-900/20 text-amber-300',
    blue: 'border-blue-700/60 bg-blue-900/20 text-blue-300',
  }[tone ?? 'blue']
  return (
    <div
      className={`rounded border ${toneClass} p-4`}
      data-testid={testId}
    >
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide opacity-80">
        {icon}
        <span>{label}</span>
      </div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
    </div>
  )
}

export default function AlertsDashboard({ workspaceId }: AlertsDashboardProps) {
  const [windowHours, setWindowHours] = useState<number>(24)

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['alerts-metrics', workspaceId, windowHours],
    queryFn: () =>
      getNotificationEventMetrics(workspaceId, { window_hours: windowHours, top_n: 5 }),
    enabled: !!workspaceId,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  if (isLoading) {
    return (
      <p className="text-sm text-gray-500" data-testid="alerts-dashboard-loading">
        Loading alerts metrics…
      </p>
    )
  }

  if (isError || !data) {
    return (
      <div className="rounded border border-red-800 bg-red-900/20 p-4 text-sm text-red-300">
        <p>Failed to load alerts metrics.</p>
        <button
          onClick={() => refetch()}
          className="mt-2 rounded bg-red-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600"
        >
          Retry
        </button>
      </div>
    )
  }

  const max = maxBucketCount(data.hourly_buckets) || 1

  return (
    <div className="space-y-6" data-testid="alerts-dashboard">
      {/* Window picker + refresh */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1 rounded border border-gray-700 bg-gray-900 p-1">
          {WINDOW_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setWindowHours(opt.value)}
              className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                windowHours === opt.value
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
              data-testid={`alerts-window-${opt.value}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1 rounded border border-gray-700 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-800 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* KPI tiles */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <StatTile
          icon={<Activity className="h-4 w-4" />}
          label="Total events"
          value={String(data.total)}
          tone="blue"
          testId="kpi-total"
        />
        <StatTile
          icon={<CheckCircle2 className="h-4 w-4" />}
          label="Sent"
          value={String(data.status_counts.sent ?? 0)}
          tone="green"
          testId="kpi-sent"
        />
        <StatTile
          icon={<AlertTriangle className="h-4 w-4" />}
          label="Failed"
          value={String(data.status_counts.failed ?? 0)}
          tone="red"
          testId="kpi-failed"
        />
        <StatTile
          icon={<Clock className="h-4 w-4" />}
          label="Pending / Retrying"
          value={String(
            (data.status_counts.pending ?? 0) + (data.status_counts.retrying ?? 0),
          )}
          tone="amber"
          testId="kpi-pending"
        />
      </div>

      {/* Rate strip */}
      <div className="grid gap-3 grid-cols-3">
        <div className="rounded border border-gray-700 bg-gray-900 p-3">
          <div className="text-[11px] uppercase tracking-wide text-gray-500">
            Success rate
          </div>
          <div className="mt-1 text-lg font-semibold text-green-400">
            {formatPct(data.success_rate)}
          </div>
        </div>
        <div className="rounded border border-gray-700 bg-gray-900 p-3">
          <div className="text-[11px] uppercase tracking-wide text-gray-500">
            Failure rate
          </div>
          <div className="mt-1 text-lg font-semibold text-red-400">
            {formatPct(data.failure_rate)}
          </div>
        </div>
        <div className="rounded border border-gray-700 bg-gray-900 p-3">
          <div className="text-[11px] uppercase tracking-wide text-gray-500">
            Retry rate
          </div>
          <div className="mt-1 text-lg font-semibold text-amber-400">
            {formatPct(data.retry_rate)}
          </div>
        </div>
      </div>

      {/* Hourly chart (bar sparkline) */}
      <div
        className="rounded border border-gray-700 bg-gray-900 p-4"
        data-testid="alerts-hourly-chart"
      >
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp className="h-4 w-4 text-blue-400" />
          <h3 className="text-sm font-semibold text-white">
            Events per hour
          </h3>
          <span className="text-[11px] text-gray-500">
            window: last {windowHours}h · {data.hourly_buckets.length} buckets
          </span>
        </div>
        <div className="flex items-end gap-0.5 h-24">
          {data.hourly_buckets.map((b, i) => {
            const h = (b.count / max) * 100
            return (
              <div
                key={i}
                className="flex-1 min-w-[2px] bg-blue-600/70 hover:bg-blue-500 transition-colors"
                style={{ height: `${Math.max(2, h)}%` }}
                title={`${b.hour} — ${b.count} event(s)`}
                data-testid={`alerts-bucket-${i}`}
              />
            )
          })}
        </div>
      </div>

      {/* Top firing rules */}
      <div
        className="rounded border border-gray-700 bg-gray-900 p-4"
        data-testid="alerts-top-rules"
      >
        <h3 className="text-sm font-semibold text-white mb-3">
          Top firing rules
        </h3>
        {data.top_firing_rules.length === 0 ? (
          <p className="text-xs text-gray-500">No rules fired in this window.</p>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-left text-gray-500">
              <tr>
                <th className="py-1 pr-2">Rule</th>
                <th className="py-1 pr-2 text-right">Fired</th>
                <th className="py-1">Last fired</th>
              </tr>
            </thead>
            <tbody>
              {data.top_firing_rules.map((r) => (
                <tr key={r.rule_id} className="border-t border-gray-800">
                  <td className="py-1.5 pr-2 text-gray-200 truncate">{r.name}</td>
                  <td className="py-1.5 pr-2 text-right text-blue-300 font-mono">
                    {r.fired_count}
                  </td>
                  <td className="py-1.5 text-gray-400">
                    {formatDate(r.last_fired_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Channel health */}
      <div
        className="rounded border border-gray-700 bg-gray-900 p-4"
        data-testid="alerts-channel-health"
      >
        <h3 className="text-sm font-semibold text-white mb-3">
          Channel health
        </h3>
        {data.channel_health.length === 0 ? (
          <p className="text-xs text-gray-500">No channels delivered events in this window.</p>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-left text-gray-500">
              <tr>
                <th className="py-1 pr-2">Channel</th>
                <th className="py-1 pr-2">Type</th>
                <th className="py-1 pr-2 text-right">Sent</th>
                <th className="py-1 pr-2 text-right">Failed</th>
                <th className="py-1 pr-2 text-right">Success %</th>
                <th className="py-1 pr-2">Last success</th>
                <th className="py-1">Last failure</th>
              </tr>
            </thead>
            <tbody>
              {data.channel_health.map((c) => (
                <tr key={c.channel_id} className="border-t border-gray-800">
                  <td className="py-1.5 pr-2 text-gray-200 truncate">{c.name}</td>
                  <td className="py-1.5 pr-2 text-gray-400">{c.channel_type ?? '—'}</td>
                  <td className="py-1.5 pr-2 text-right text-green-300 font-mono">
                    {c.sent_count}
                  </td>
                  <td className="py-1.5 pr-2 text-right text-red-300 font-mono">
                    {c.failed_count}
                  </td>
                  <td className="py-1.5 pr-2 text-right text-blue-300 font-mono">
                    {formatPct(c.success_pct)}
                  </td>
                  <td className="py-1.5 pr-2 text-gray-400">
                    {formatDate(c.last_success_at)}
                  </td>
                  <td className="py-1.5 text-gray-400">
                    {formatDate(c.last_failure_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
