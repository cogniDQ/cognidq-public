/**
 * F083 — Quality Reports Page
 *
 * Workspace-scoped dashboard showing real issue and incident reporting data
 * from the F050 /reports endpoints. Two-tab layout: Issues | Incidents.
 *
 * Distinct from the global Reports page (mock flow dashboards).
 * Route: /hub/ws/:workspace_id/quality-reports
 */

import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Download, AlertCircle, TrendingDown, Clock, ShieldAlert } from 'lucide-react';
import {
  getIssueSummary,
  getIncidentSummary,
  buildIssueExportUrl,
  buildIncidentExportUrl,
  type IssueDashboardSummary,
  type IncidentDashboardSummary,
} from '../../services/qualityReportsService';

// ─────────────────────────────────────────────────────────────────────────────
// Shared sub-components
// ─────────────────────────────────────────────────────────────────────────────

interface KpiCardProps {
  label: string;
  value: number | string;
  sub?: string;
  accent?: 'red' | 'yellow' | 'green' | 'blue' | 'purple';
}

function KpiCard({ label, value, sub, accent = 'blue' }: KpiCardProps) {
  const accentClass: Record<string, string> = {
    red:    'text-red-400 bg-red-500/10 border-red-500/20',
    yellow: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20',
    green:  'text-green-400 bg-green-500/10 border-green-500/20',
    blue:   'text-blue-400 bg-blue-500/10 border-blue-500/20',
    purple: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
  };
  return (
    <div className={`rounded-xl border px-5 py-4 ${accentClass[accent]}`}>
      <p className="text-xs font-medium uppercase tracking-wider opacity-70">{label}</p>
      <p className="mt-1 text-3xl font-bold">{value}</p>
      {sub && <p className="mt-0.5 text-xs opacity-60">{sub}</p>}
    </div>
  );
}

interface BreakdownRowProps {
  label: string;
  items: { label: string; value: number; color: string }[];
}

function BreakdownRow({ label, items }: BreakdownRowProps) {
  const total = items.reduce((s, i) => s + i.value, 0);
  return (
    <div className="rounded-xl border border-dark-600 bg-dark-800 px-5 py-4">
      <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-3">{label}</p>
      <div className="flex gap-4 flex-wrap">
        {items.map(item => (
          <div key={item.label} className="flex items-center gap-2">
            <span className={`inline-block w-2.5 h-2.5 rounded-full ${item.color}`} />
            <span className="text-sm text-gray-300">{item.label}</span>
            <span className="text-sm font-semibold text-white">{item.value}</span>
            {total > 0 && (
              <span className="text-xs text-gray-500">
                ({Math.round((item.value / total) * 100)}%)
              </span>
            )}
          </div>
        ))}
        {total === 0 && <span className="text-sm text-gray-500">No data</span>}
      </div>
    </div>
  );
}

interface ResolutionStatsCardProps {
  avgHours: number;
  medianHours: number;
  p95Hours: number;
  totalResolved: number;
}

function ResolutionStatsCard({ avgHours, medianHours, p95Hours, totalResolved }: ResolutionStatsCardProps) {
  const fmt = (h: number) =>
    h < 1 ? `${Math.round(h * 60)}m` : `${h.toFixed(1)}h`;

  return (
    <div className="rounded-xl border border-dark-600 bg-dark-800 px-5 py-4">
      <div className="flex items-center gap-2 mb-3">
        <Clock className="w-4 h-4 text-gray-400" />
        <p className="text-xs font-medium uppercase tracking-wider text-gray-400">
          Resolution Time ({totalResolved} resolved)
        </p>
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <p className="text-xs text-gray-500">Avg</p>
          <p className="text-lg font-semibold text-white">{fmt(avgHours)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Median</p>
          <p className="text-lg font-semibold text-white">{fmt(medianHours)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">P95</p>
          <p className="text-lg font-semibold text-white">{fmt(p95Hours)}</p>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Issues tab
// ─────────────────────────────────────────────────────────────────────────────

interface IssuesTabProps {
  data: IssueDashboardSummary;
  workspaceId: string;
}

function IssuesTab({ data, workspaceId }: IssuesTabProps) {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const totalIssues =
    data.status_counts.open + data.status_counts.resolved + data.status_counts.closed;

  const handleExport = async () => {
    if (exporting) return;
    setExporting(true);
    setExportError(null);
    try {
      const url = buildIssueExportUrl(workspaceId);
      const token = localStorage.getItem('access_token');
      const response = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error(`Export failed: ${response.status}`);
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = `issue-summary-${workspaceId}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(objectUrl);
    } catch {
      setExportError('Export failed. Please try again.');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="issues-tab">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => { void handleExport(); }}
          disabled={exporting}
          className="flex items-center gap-1.5 rounded-lg border border-dark-600 px-3 py-1.5 text-sm text-gray-300 hover:text-white disabled:opacity-50 transition-colors"
        >
          <Download className="w-4 h-4" aria-hidden="true" />
          {exporting ? 'Exporting…' : 'Export CSV'}
        </button>
      </div>

      {exportError && (
        <p className="text-sm text-red-400">{exportError}</p>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <KpiCard label="Total Issues" value={totalIssues} accent="blue" />
        <KpiCard label="Open" value={data.status_counts.open} accent="yellow" />
        <KpiCard label="Overdue" value={data.overdue_count} accent="red" />
        <KpiCard label="Resolved" value={data.status_counts.resolved} accent="green" />
      </div>

      {/* Status breakdown */}
      <BreakdownRow
        label="By Status"
        items={[
          { label: 'Open',     value: data.status_counts.open,     color: 'bg-yellow-400' },
          { label: 'Resolved', value: data.status_counts.resolved, color: 'bg-green-400' },
          { label: 'Closed',   value: data.status_counts.closed,   color: 'bg-gray-400'  },
        ]}
      />

      {/* Severity breakdown */}
      <BreakdownRow
        label="By Severity"
        items={[
          { label: 'Critical', value: data.severity_counts.critical, color: 'bg-red-500'    },
          { label: 'Major',    value: data.severity_counts.major,    color: 'bg-orange-400' },
          { label: 'Minor',    value: data.severity_counts.minor,    color: 'bg-yellow-400' },
          { label: 'Info',     value: data.severity_counts.info,     color: 'bg-blue-400'   },
        ]}
      />

      {/* Resolution stats */}
      <ResolutionStatsCard
        avgHours={data.resolution_stats.avg_hours}
        medianHours={data.resolution_stats.median_hours}
        p95Hours={data.resolution_stats.p95_hours}
        totalResolved={data.resolution_stats.total_resolved}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Incidents tab
// ─────────────────────────────────────────────────────────────────────────────

interface IncidentsTabProps {
  data: IncidentDashboardSummary;
  workspaceId: string;
}

function IncidentsTab({ data, workspaceId }: IncidentsTabProps) {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const totalIncidents =
    data.status_counts.open +
    data.status_counts.acknowledged +
    data.status_counts.resolved +
    data.status_counts.closed;

  const handleExport = async () => {
    if (exporting) return;
    setExporting(true);
    setExportError(null);
    try {
      const url = buildIncidentExportUrl(workspaceId);
      const token = localStorage.getItem('access_token');
      const response = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error(`Export failed: ${response.status}`);
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = `incident-summary-${workspaceId}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(objectUrl);
    } catch {
      setExportError('Export failed. Please try again.');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="incidents-tab">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => { void handleExport(); }}
          disabled={exporting}
          className="flex items-center gap-1.5 rounded-lg border border-dark-600 px-3 py-1.5 text-sm text-gray-300 hover:text-white disabled:opacity-50 transition-colors"
        >
          <Download className="w-4 h-4" aria-hidden="true" />
          {exporting ? 'Exporting…' : 'Export CSV'}
        </button>
      </div>

      {exportError && (
        <p className="text-sm text-red-400">{exportError}</p>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <KpiCard label="Total Incidents" value={totalIncidents} accent="blue" />
        <KpiCard label="Open" value={data.status_counts.open} accent="yellow" />
        <KpiCard
          label="SLA Breaches"
          value={data.sla_breach_count}
          accent={data.sla_breach_count > 0 ? 'red' : 'green'}
        />
        <KpiCard label="Resolved" value={data.status_counts.resolved} accent="green" />
      </div>

      {/* Status breakdown */}
      <BreakdownRow
        label="By Status"
        items={[
          { label: 'Open',         value: data.status_counts.open,         color: 'bg-yellow-400' },
          { label: 'Acknowledged', value: data.status_counts.acknowledged, color: 'bg-blue-400'   },
          { label: 'Resolved',     value: data.status_counts.resolved,     color: 'bg-green-400'  },
          { label: 'Closed',       value: data.status_counts.closed,       color: 'bg-gray-400'   },
        ]}
      />

      {/* Severity breakdown */}
      <BreakdownRow
        label="By Severity"
        items={[
          { label: 'Critical', value: data.severity_counts.critical, color: 'bg-red-500'    },
          { label: 'Major',    value: data.severity_counts.major,    color: 'bg-orange-400' },
          { label: 'Minor',    value: data.severity_counts.minor,    color: 'bg-yellow-400' },
          { label: 'Info',     value: data.severity_counts.info,     color: 'bg-blue-400'   },
        ]}
      />

      {/* Priority breakdown */}
      <BreakdownRow
        label="By Priority"
        items={[
          { label: 'P1', value: data.priority_counts.p1, color: 'bg-red-600'    },
          { label: 'P2', value: data.priority_counts.p2, color: 'bg-orange-500' },
          { label: 'P3', value: data.priority_counts.p3, color: 'bg-yellow-500' },
          { label: 'P4', value: data.priority_counts.p4, color: 'bg-gray-400'   },
        ]}
      />

      {/* Resolution stats */}
      <ResolutionStatsCard
        avgHours={data.resolution_stats.avg_hours}
        medianHours={data.resolution_stats.median_hours}
        p95Hours={data.resolution_stats.p95_hours}
        totalResolved={data.resolution_stats.total_resolved}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

type Tab = 'issues' | 'incidents';

export default function QualityReportsPage() {
  const { workspace_id } = useParams<{ workspace_id: string }>();

  const [activeTab, setActiveTab] = useState<Tab>('issues');
  const [issueSummary, setIssueSummary] = useState<IssueDashboardSummary | null>(null);
  const [incidentSummary, setIncidentSummary] = useState<IncidentDashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspace_id) return;
    setLoading(true);
    setError(null);

    Promise.all([
      getIssueSummary(workspace_id),
      getIncidentSummary(workspace_id),
    ])
      .then(([issues, incidents]) => {
        setIssueSummary(issues);
        setIncidentSummary(incidents);
      })
      .catch(() => {
        setError('Failed to load quality reports. Please try again.');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [workspace_id]);

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'issues',    label: 'Issues',    icon: <AlertCircle className="w-4 h-4" /> },
    { id: 'incidents', label: 'Incidents', icon: <ShieldAlert className="w-4 h-4" /> },
  ];

  return (
    <div className="space-y-6" data-testid="quality-reports-page">
      {/* Header */}
      <div className="flex items-center gap-3">
        <TrendingDown className="w-6 h-6 text-blue-400" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-white">Quality Reports</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            Issue and incident metrics for this workspace
          </p>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400"
        >
          <AlertCircle className="w-5 h-5 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-dark-600">
        {tabs.map(tab => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-gray-400 hover:text-white'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="space-y-4" data-testid="reports-loading">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-24 rounded-xl bg-dark-700 animate-pulse" />
            ))}
          </div>
          <div className="h-16 rounded-xl bg-dark-700 animate-pulse" />
          <div className="h-16 rounded-xl bg-dark-700 animate-pulse" />
          <div className="h-20 rounded-xl bg-dark-700 animate-pulse" />
        </div>
      ) : (
        <>
          {activeTab === 'issues' && issueSummary && workspace_id && (
            <IssuesTab data={issueSummary} workspaceId={workspace_id} />
          )}
          {activeTab === 'incidents' && incidentSummary && workspace_id && (
            <IncidentsTab data={incidentSummary} workspaceId={workspace_id} />
          )}
        </>
      )}
    </div>
  );
}
