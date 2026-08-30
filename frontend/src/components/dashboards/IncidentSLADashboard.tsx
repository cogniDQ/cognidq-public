import React, { useState, useEffect } from 'react';
import { DataTable } from '../widgets/DataTable';
import { KPICard } from '../widgets/KPICard';
import { TrendChart } from '../widgets/TrendChart';
import { GaugeChart } from '../widgets/GaugeChart';
import { PeriodSelector } from '../widgets/PeriodSelector';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import {
  getIncidentSLAMetrics,
  getIncidentSLABreaches,
  getIncidentSLAComplianceTrend,
  getIncidentSLAList,
  type IncidentSLAMetricsResponse,
  type IncidentSLABreachesResponse,
  type IncidentSLAComplianceTrendResponse,
  type IncidentSLAListResponse,
} from '../../services/kqiService';

export const IncidentSLADashboard: React.FC = () => {
  const { currentWorkspace } = useWorkspace();
  const [period, setPeriod] = useState('30d');
  const [loading, setLoading] = useState(true);
  const [metrics, setMetrics] = useState<IncidentSLAMetricsResponse | null>(null);
  const [breaches, setBreaches] = useState<IncidentSLABreachesResponse | null>(null);
  const [trend, setTrend] = useState<IncidentSLAComplianceTrendResponse | null>(null);
  const [incidents, setIncidents] = useState<IncidentSLAListResponse | null>(null);

  useEffect(() => {
    if (!currentWorkspace) return;
    const wsId = currentWorkspace.workspace_id;
    setLoading(true);
    Promise.all([
      getIncidentSLAMetrics(wsId, period),
      getIncidentSLABreaches(wsId, period),
      getIncidentSLAComplianceTrend(wsId),
      getIncidentSLAList(wsId, period),
    ])
      .then(([m, b, t, i]) => {
        setMetrics(m);
        setBreaches(b);
        setTrend(t);
        setIncidents(i);
      })
      .catch((err) => console.error('Failed to load incident SLA data', err))
      .finally(() => setLoading(false));
  }, [currentWorkspace, period]);

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading incident SLA metrics…</div>;
  }

  if (!metrics || !metrics.has_data) {
    return <div className="flex items-center justify-center h-64 text-gray-500">No incident data available for this period</div>;
  }

  const mttrDisplay = metrics.mttr_hours < 1
    ? `${Math.round(metrics.mttr_hours * 60)} min`
    : `${metrics.mttr_hours.toFixed(1)} hrs`;

  const breachDurationDisplay = metrics.avg_breach_duration_hours < 1
    ? `${Math.round(metrics.avg_breach_duration_hours * 60)} min`
    : `${metrics.avg_breach_duration_hours.toFixed(1)} hrs`;

  const maxBreach = breaches?.distribution.length
    ? Math.max(...breaches.distribution.map((d) => d.value))
    : 1;

  const incidentRows = (incidents?.items ?? []).map((inc) => ({
    ...inc,
    slaTarget: `${inc.sla_target_hours}h`,
    timeElapsed:
      inc.elapsed_hours < 1
        ? `${Math.round(inc.elapsed_hours * 60)} min`
        : `${inc.elapsed_hours.toFixed(1)}h`,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Incident & SLA Management</h1>
          <p className="text-gray-400">Enterprise accountability and incident tracking</p>
        </div>
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      {/* Key Metrics */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">SLA Performance</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <GaugeChart value={metrics.compliance_rate} title="SLA Compliance Rate" label="Overall" />
          <KPICard
            title="Breaches"
            value={metrics.breaches_count}
            status={metrics.breaches_count <= 5 ? 'success' : 'warning'}
          />
          <KPICard title="Avg Breach Duration" value={breachDurationDisplay} status="warning" />
          <KPICard
            title="Mean Time to Recovery"
            value={mttrDisplay}
            subtitle="MTTR"
            status="success"
          />
        </div>
      </section>

      {/* Breaches by Severity */}
      {breaches && breaches.has_data && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">SLA Breaches by Severity</h2>
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
            <h3 className="text-md font-semibold text-white mb-4">Breach Distribution</h3>
            <div className="space-y-3">
              {breaches.distribution.map((item) => (
                <div key={item.name}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-gray-300">{item.name}</span>
                    <span className="text-sm text-white font-medium">{item.value} breaches</span>
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-2">
                    <div
                      className="bg-red-500 h-2 rounded-full"
                      style={{ width: `${(item.value / maxBreach) * 100}%` }}
                    ></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Compliance Trend */}
      {trend && trend.has_data && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">SLA Compliance Trend</h2>
          <TrendChart
            data={trend.trend}
            lines={[
              { dataKey: 'compliance', name: 'Compliance Rate (%)', color: '#10B981' },
              { dataKey: 'breaches', name: 'Breaches', color: '#EF4444' },
            ]}
            xAxisKey="date"
            title="Weekly SLA Performance"
            height={300}
          />
        </section>
      )}

      {/* Incident List */}
      {incidents && incidents.has_data && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">Active & Recent Incidents</h2>
          <DataTable
            data={incidentRows}
            columns={[
              { key: 'id', label: 'Incident ID', width: '15%' },
              { key: 'title', label: 'Title', width: '22%' },
              {
                key: 'severity',
                label: 'Severity',
                render: (value: string) => (
                  <span
                    className={`px-2 py-1 rounded text-xs font-medium ${
                      value === 'Critical'
                        ? 'bg-red-500/20 text-red-400'
                        : value === 'Major'
                        ? 'bg-orange-500/20 text-orange-400'
                        : value === 'Minor'
                        ? 'bg-yellow-500/20 text-yellow-400'
                        : 'bg-blue-500/20 text-blue-400'
                    }`}
                  >
                    {value}
                  </span>
                ),
              },
              {
                key: 'status',
                label: 'Status',
                render: (value: string) => (
                  <span
                    className={`px-2 py-1 rounded text-xs font-medium ${
                      value === 'Resolved' || value === 'Closed'
                        ? 'bg-green-500/20 text-green-400'
                        : value === 'Acknowledged'
                        ? 'bg-yellow-500/20 text-yellow-400'
                        : 'bg-red-500/20 text-red-400'
                    }`}
                  >
                    {value}
                  </span>
                ),
              },
              { key: 'slaTarget', label: 'SLA Target' },
              {
                key: 'timeElapsed',
                label: 'Time Elapsed',
                render: (value: string, row: Record<string, unknown>) => (
                  <span className={(row.breached as boolean) ? 'text-red-400 font-medium' : 'text-green-400'}>
                    {value}
                  </span>
                ),
              },
            ]}
            searchable
          />
        </section>
      )}

      {/* Lifecycle Metrics */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Incident Lifecycle Metrics</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <KPICard title="Total Incidents" value={metrics.total_incidents} status="neutral" />
          <KPICard title="Resolved" value={metrics.resolved_count} status="success" />
          <KPICard title="Open" value={metrics.open_count} status={metrics.open_count > 0 ? 'warning' : 'success'} />
          <KPICard
            title="Compliance Rate"
            value={`${metrics.compliance_rate}%`}
            status={metrics.compliance_rate >= 90 ? 'success' : 'warning'}
          />
        </div>
      </section>
    </div>
  );
};
