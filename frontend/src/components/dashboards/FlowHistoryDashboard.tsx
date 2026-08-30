import React, { useState, useEffect } from 'react';
import { TrendChart } from '../widgets/TrendChart';
import { HeatMap } from '../widgets/HeatMap';
import { KPICard } from '../widgets/KPICard';
import { DataTable } from '../widgets/DataTable';
import { PeriodSelector } from '../widgets/PeriodSelector';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import {
  getOperationalSummary,
  getOperationalTimeline,
  getCheckHeatmap,
  getRecentAlerts,
  type OperationalSummaryResponse,
  type OperationalTimelineResponse,
  type CheckHeatmapResponse,
  type RecentAlertsResponse,
} from '../../services/kqiService';

export const FlowHistoryDashboard: React.FC = () => {
  const { currentWorkspace } = useWorkspace();
  const [period, setPeriod] = useState('30d');
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<OperationalSummaryResponse | null>(null);
  const [timeline, setTimeline] = useState<OperationalTimelineResponse | null>(null);
  const [heatmap, setHeatmap] = useState<CheckHeatmapResponse | null>(null);
  const [alerts, setAlerts] = useState<RecentAlertsResponse | null>(null);

  useEffect(() => {
    if (!currentWorkspace) return;
    const wsId = currentWorkspace.workspace_id;
    setLoading(true);
    Promise.all([
      getOperationalSummary(wsId, period),
      getOperationalTimeline(wsId, period),
      getCheckHeatmap(wsId, period),
      getRecentAlerts(wsId),
    ])
      .then(([sum, tl, hm, al]) => {
        setSummary(sum);
        setTimeline(tl);
        setHeatmap(hm);
        setAlerts(al);
      })
      .catch((err) => console.error('Failed to load operational KQIs', err))
      .finally(() => setLoading(false));
  }, [currentWorkspace, period]);

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading operational metrics…</div>;
  }

  if (!summary || !summary.has_data) {
    return <div className="flex items-center justify-center h-64 text-gray-500">No operational data available</div>;
  }
  const mttrDisplay = summary.mttr_hours != null
    ? summary.mttr_hours < 1
      ? `${Math.round(summary.mttr_hours * 60)} min`
      : `${summary.mttr_hours.toFixed(1)} hrs`
    : 'N/A';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Flow History & Operational Intelligence</h1>
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      {/* Key Metrics */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Key Metrics</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <KPICard
            title="Runs per Day"
            value={summary.runs_per_day}
            status="success"
          />
          <KPICard
            title="Success Rate"
            value={`${summary.success_rate.toFixed(1)}%`}
            status={summary.success_rate >= 80 ? 'success' : 'warning'}
          />
          <KPICard
            title="Failure Rate"
            value={`${summary.failure_rate.toFixed(1)}%`}
            status={summary.failure_rate <= 20 ? 'warning' : 'error'}
          />
          <KPICard title="MTTR" value={mttrDisplay} subtitle="Mean Time to Recovery" status="neutral" />
          <KPICard
            title="Quality Stability"
            value={summary.quality_stability_index != null ? `${summary.quality_stability_index.toFixed(1)}%` : 'N/A'}
            subtitle="Consistency score"
            status={summary.quality_stability_index != null && summary.quality_stability_index >= 70 ? 'success' : 'warning'}
          />
        </div>
      </section>

      {/* Execution Timeline */}
      {timeline && timeline.data_points && timeline.data_points.length > 0 && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">Execution Timeline</h2>
          <TrendChart
            data={timeline.data_points}
            lines={[
              { dataKey: 'success', name: 'Success', color: '#10B981' },
              { dataKey: 'partial', name: 'Partial Success', color: '#F59E0B' },
              { dataKey: 'failed', name: 'Failed', color: '#EF4444' },
            ]}
            xAxisKey="date"
            title={`Runs by Status (${period})`}
            height={300}
          />
        </section>
      )}

      {/* Check Performance Heatmap */}
      {heatmap && heatmap.has_data && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">Check Performance Heatmap (Checks × Time)</h2>
          <HeatMap data={heatmap.data} title="Pass Rate % by Check and Day" />
        </section>
      )}

      {/* Recent Alerts */}
      {alerts && alerts.has_data && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">Recent Alerts</h2>
          <DataTable
            data={alerts.alerts}
            columns={[
              { key: 'date', label: 'Date/Time', width: '20%' },
              { key: 'check', label: 'Check Name', width: '25%' },
              {
                key: 'severity',
                label: 'Severity',
                render: (value: string) => (
                  <span
                    className={`px-2 py-1 rounded text-xs font-medium ${
                      value === 'Critical'
                        ? 'bg-red-500/20 text-red-400'
                        : value === 'High'
                        ? 'bg-orange-500/20 text-orange-400'
                        : value === 'Medium'
                        ? 'bg-yellow-500/20 text-yellow-400'
                        : 'bg-blue-500/20 text-blue-400'
                    }`}
                  >
                    {value}
                  </span>
                ),
              },
              { key: 'message', label: 'Message', width: '35%' },
              {
                key: 'resolved',
                label: 'Status',
                render: (value: boolean) => (
                  <span
                    className={`px-2 py-1 rounded text-xs font-medium ${
                      value ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                    }`}
                  >
                    {value ? 'Resolved' : 'Active'}
                  </span>
                ),
              },
            ]}
            searchable
          />
        </section>
      )}
    </div>
  );
};
