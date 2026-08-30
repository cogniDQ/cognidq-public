import React from 'react';
import { DataTable } from '../src/components/widgets/DataTable';
import { KPICard } from '../src/components/widgets/KPICard';
import { TrendChart } from '../src/components/widgets/TrendChart';
import { GaugeChart } from '../src/components/widgets/GaugeChart';

// Dummy data
const slaMetrics = {
  complianceRate: 87,
  breachesThisMonth: 8,
  avgBreachDuration: '3.2 hours',
  mttr: '2.1 hours',
};

const breachesByDomain = [
  { name: 'Customer Management', value: 3 },
  { name: 'Order Processing', value: 2 },
  { name: 'Inventory', value: 2 },
  { name: 'Finance', value: 1 },
];

const incidents = [
  {
    id: 'INC-2026-012',
    title: 'Email completeness below threshold',
    dataset: 'customers',
    severity: 'Critical',
    created: '2026-01-16 08:15',
    assigned: 'Data Team',
    status: 'Mitigating',
    slaTarget: '4 hours',
    timeElapsed: '2h 15m',
    mitigatedAt: null,
    resolvedAt: null,
  },
  {
    id: 'INC-2026-011',
    title: 'Order volume anomaly detected',
    dataset: 'orders',
    severity: 'High',
    created: '2026-01-15 14:30',
    assigned: 'Platform Team',
    status: 'Resolved',
    slaTarget: '8 hours',
    timeElapsed: '5h 45m',
    mitigatedAt: '2026-01-15 16:45',
    resolvedAt: '2026-01-15 20:15',
  },
  {
    id: 'INC-2026-010',
    title: 'Product SKU format violations',
    dataset: 'products',
    severity: 'Medium',
    created: '2026-01-15 09:00',
    assigned: 'Catalog Team',
    status: 'Resolved',
    slaTarget: '24 hours',
    timeElapsed: '18h 30m',
    mitigatedAt: '2026-01-15 12:00',
    resolvedAt: '2026-01-16 03:30',
  },
  {
    id: 'INC-2026-009',
    title: 'Duplicate customer IDs found',
    dataset: 'customers',
    severity: 'Critical',
    created: '2026-01-14 16:20',
    assigned: 'Data Team',
    status: 'Resolved',
    slaTarget: '4 hours',
    timeElapsed: '3h 10m',
    mitigatedAt: '2026-01-14 17:00',
    resolvedAt: '2026-01-14 19:30',
  },
];

const slaComplianceTrend = [
  { date: 'Week 1', compliance: 92, breaches: 3 },
  { date: 'Week 2', compliance: 89, breaches: 5 },
  { date: 'Week 3', compliance: 91, breaches: 4 },
  { date: 'Week 4', compliance: 87, breaches: 8 },
];

export const IncidentSLADashboard: React.FC = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Incident & SLA Management</h1>
      <p className="text-gray-400">Enterprise accountability and incident tracking</p>

      {/* Key Metrics */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">SLA Performance</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <GaugeChart value={slaMetrics.complianceRate} title="SLA Compliance Rate" label="Overall" />
          <KPICard
            title="Breaches This Month"
            value={slaMetrics.breachesThisMonth}
            trend={{ value: 15, direction: 'down', label: 'vs last month' }}
            status={slaMetrics.breachesThisMonth <= 5 ? 'success' : 'warning'}
          />
          <KPICard title="Avg Breach Duration" value={slaMetrics.avgBreachDuration} status="warning" />
          <KPICard
            title="Mean Time to Recovery"
            value={slaMetrics.mttr}
            subtitle="MTTR"
            status="success"
          />
        </div>
      </section>

      {/* Breaches by Domain */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">SLA Breaches by Domain</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
            <h3 className="text-md font-semibold text-white mb-4">Breach Distribution</h3>
            <div className="space-y-3">
              {breachesByDomain.map((domain) => (
                <div key={domain.name}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-gray-300">{domain.name}</span>
                    <span className="text-sm text-white font-medium">{domain.value} breaches</span>
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-2">
                    <div
                      className="bg-red-500 h-2 rounded-full"
                      style={{ width: `${(domain.value / 8) * 100}%` }}
                    ></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
            <h3 className="text-md font-semibold text-white mb-4">Top Affected Areas</h3>
            <ul className="space-y-2 text-sm">
              <li className="flex items-center justify-between">
                <span className="text-gray-300">Customer Management</span>
                <span className="px-2 py-1 bg-red-500/20 text-red-400 rounded text-xs">3 breaches</span>
              </li>
              <li className="flex items-center justify-between">
                <span className="text-gray-300">Order Processing</span>
                <span className="px-2 py-1 bg-orange-500/20 text-orange-400 rounded text-xs">2 breaches</span>
              </li>
              <li className="flex items-center justify-between">
                <span className="text-gray-300">Inventory</span>
                <span className="px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded text-xs">2 breaches</span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* Compliance Trend */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">SLA Compliance Trend</h2>
        <TrendChart
          data={slaComplianceTrend}
          lines={[
            { dataKey: 'compliance', name: 'Compliance Rate (%)', color: '#10B981' },
            { dataKey: 'breaches', name: 'Breaches', color: '#EF4444' },
          ]}
          xAxisKey="date"
          title="Monthly SLA Performance"
          height={300}
        />
      </section>

      {/* Incident Lifecycle */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Active & Recent Incidents</h2>
        <DataTable
          data={incidents}
          columns={[
            { key: 'id', label: 'Incident ID', width: '12%' },
            { key: 'title', label: 'Title', width: '20%' },
            { key: 'dataset', label: 'Dataset' },
            {
              key: 'severity',
              label: 'Severity',
              render: (value) => (
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
            { key: 'created', label: 'Created', width: '15%' },
            { key: 'assigned', label: 'Assigned To' },
            {
              key: 'status',
              label: 'Status',
              render: (value) => (
                <span
                  className={`px-2 py-1 rounded text-xs font-medium ${
                    value === 'Resolved'
                      ? 'bg-green-500/20 text-green-400'
                      : value === 'Mitigating'
                      ? 'bg-yellow-500/20 text-yellow-400'
                      : value === 'Assigned'
                      ? 'bg-blue-500/20 text-blue-400'
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
              render: (value, row) => (
                <span className={row.status === 'Resolved' ? 'text-green-400' : 'text-yellow-400'}>
                  {value}
                </span>
              ),
            },
          ]}
          searchable
        />
      </section>

      {/* Lifecycle Metrics */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Incident Lifecycle Metrics</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <KPICard title="Created (30d)" value={12} status="neutral" />
          <KPICard title="Assigned (Avg)" value="15 min" subtitle="Time to assignment" status="success" />
          <KPICard title="Mitigated (Avg)" value="2.3 hours" subtitle="Time to mitigation" status="success" />
          <KPICard title="Resolved (Avg)" value="4.8 hours" subtitle="Time to resolution" status="success" />
        </div>
      </section>

      {/* Insights */}
      <section className="bg-blue-900/20 border border-blue-700 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-white mb-2">📊 Key Insights</h3>
        <ul className="space-y-2 text-sm text-blue-300">
          <li>• <strong>SLA Compliance:</strong> 87% - slightly below 90% target, needs improvement</li>
          <li>• <strong>Customer Management:</strong> Most breaches (3) - prioritize data quality improvements</li>
          <li>• <strong>MTTR Improvement:</strong> Down to 2.1 hours (from 3.5 hours last month) - good progress</li>
          <li>• <strong>Recommendation:</strong> Implement proactive alerts to catch issues before SLA breach</li>
        </ul>
      </section>
    </div>
  );
};
