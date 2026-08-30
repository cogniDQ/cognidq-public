import React from 'react';
import { TrendChart } from '../src/components/widgets/TrendChart';
import { HeatMap } from '../src/components/widgets/HeatMap';
import { KPICard } from '../src/components/widgets/KPICard';
import { DataTable } from '../src/components/widgets/DataTable';

// Dummy data
const flowMetrics = {
  runsPerDay: 24,
  successRate: 82,
  failureRate: 18,
  mttr: '45 min',
  qualityStabilityIndex: 78,
};

const executionHistory = [
  { date: 'Jan 12', runs: 22, success: 18, partial: 3, failed: 1 },
  { date: 'Jan 13', runs: 25, success: 20, partial: 4, failed: 1 },
  { date: 'Jan 14', runs: 23, success: 19, partial: 2, failed: 2 },
  { date: 'Jan 15', runs: 26, success: 21, partial: 3, failed: 2 },
  { date: 'Jan 16', runs: 24, success: 20, partial: 2, failed: 2 },
];

const heatmapData = [
  { x: 'Mon', y: 'Email Check', value: 95 },
  { x: 'Mon', y: 'ID Uniqueness', value: 100 },
  { x: 'Mon', y: 'Amount Range', value: 98 },
  { x: 'Tue', y: 'Email Check', value: 96 },
  { x: 'Tue', y: 'ID Uniqueness', value: 100 },
  { x: 'Tue', y: 'Amount Range', value: 97 },
  { x: 'Wed', y: 'Email Check', value: 94 },
  { x: 'Wed', y: 'ID Uniqueness', value: 100 },
  { x: 'Wed', y: 'Amount Range', value: 98 },
  { x: 'Thu', y: 'Email Check', value: 93 },
  { x: 'Thu', y: 'ID Uniqueness', value: 100 },
  { x: 'Thu', y: 'Amount Range', value: 99 },
  { x: 'Fri', y: 'Email Check', value: 94 },
  { x: 'Fri', y: 'ID Uniqueness', value: 100 },
  { x: 'Fri', y: 'Amount Range', value: 98 },
];

const alertHistory = [
  {
    date: '2026-01-16 08:15',
    check: 'Email Completeness',
    severity: 'High',
    message: 'Completeness dropped below threshold',
    resolved: false,
  },
  {
    date: '2026-01-15 14:30',
    check: 'Order Amount Range',
    severity: 'Medium',
    message: 'Unusual spike in out-of-range values',
    resolved: true,
  },
  {
    date: '2026-01-15 09:45',
    check: 'Product SKU Format',
    severity: 'Low',
    message: 'Minor format deviations detected',
    resolved: true,
  },
  {
    date: '2026-01-14 16:20',
    check: 'Customer ID Uniqueness',
    severity: 'Critical',
    message: 'Duplicate IDs found',
    resolved: true,
  },
];

export const FlowHistoryDashboard: React.FC = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Flow History & Operational Intelligence</h1>

      {/* Key Metrics */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Key Metrics</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <KPICard
            title="Runs per Day"
            value={flowMetrics.runsPerDay}
            trend={{ value: 8, direction: 'up', label: 'vs last week' }}
            status="success"
          />
          <KPICard
            title="Success Rate"
            value={`${flowMetrics.successRate}%`}
            status={flowMetrics.successRate >= 80 ? 'success' : 'warning'}
          />
          <KPICard
            title="Failure Rate"
            value={`${flowMetrics.failureRate}%`}
            status={flowMetrics.failureRate <= 20 ? 'warning' : 'error'}
          />
          <KPICard title="MTTR" value={flowMetrics.mttr} subtitle="Mean Time to Recovery" status="neutral" />
          <KPICard
            title="Quality Stability"
            value={`${flowMetrics.qualityStabilityIndex}%`}
            subtitle="Consistency score"
            status={flowMetrics.qualityStabilityIndex >= 70 ? 'success' : 'warning'}
          />
        </div>
      </section>

      {/* Execution Timeline */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Execution Timeline</h2>
        <TrendChart
          data={executionHistory}
          lines={[
            { dataKey: 'success', name: 'Success', color: '#10B981' },
            { dataKey: 'partial', name: 'Partial Success', color: '#F59E0B' },
            { dataKey: 'failed', name: 'Failed', color: '#EF4444' },
          ]}
          xAxisKey="date"
          title="Runs by Status (Last 5 Days)"
          height={300}
        />
      </section>

      {/* Check Performance Heatmap */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Check Performance Heatmap (Checks × Time)</h2>
        <HeatMap data={heatmapData} title="Pass Rate % by Check and Day" />
      </section>

      {/* Alert Frequency */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Recent Alerts</h2>
        <DataTable
          data={alertHistory}
          columns={[
            { key: 'date', label: 'Date/Time', width: '20%' },
            { key: 'check', label: 'Check Name', width: '25%' },
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
            { key: 'message', label: 'Message', width: '35%' },
            {
              key: 'resolved',
              label: 'Status',
              render: (value) => (
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
    </div>
  );
};
