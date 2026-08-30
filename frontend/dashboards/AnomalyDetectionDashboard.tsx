import React from 'react';
import { DataTable } from '../src/components/widgets/DataTable';
import { KPICard } from '../src/components/widgets/KPICard';
import { TrendChart } from '../src/components/widgets/TrendChart';
import { ExclamationTriangleIcon, BellAlertIcon } from '@heroicons/react/24/outline';

// Dummy data
const anomalyMetrics = {
  totalAnomalies: 8,
  criticalAnomalies: 2,
  resolvedToday: 5,
  avgDetectionTime: '12 min',
};

const detectedAnomalies = [
  {
    dataset: 'customers',
    column: 'email',
    anomaly: 'Sudden NULL spike',
    severity: 'Critical',
    detected: '2026-01-16 08:05',
    currentValue: '5.9% NULL',
    expectedValue: '< 1% NULL',
    rootCause: 'API integration bug introduced in v2.4.1',
    status: 'Active',
  },
  {
    dataset: 'orders',
    column: 'amount',
    anomaly: 'Volume anomaly',
    severity: 'High',
    detected: '2026-01-16 09:15',
    currentValue: '520K rows',
    expectedValue: '~450K rows',
    rootCause: 'Black Friday sale started - expected behavior',
    status: 'Acknowledged',
  },
  {
    dataset: 'products',
    column: 'price',
    anomaly: 'Distribution drift',
    severity: 'Medium',
    detected: '2026-01-16 10:30',
    currentValue: 'Shifted +15%',
    expectedValue: 'Normal range',
    rootCause: 'Price increase campaign - planned change',
    status: 'Resolved',
  },
  {
    dataset: 'inventory',
    column: 'stock_level',
    anomaly: 'New values appearing',
    severity: 'Low',
    detected: '2026-01-16 11:45',
    currentValue: 'Negative values found',
    expectedValue: '>= 0',
    rootCause: 'Data entry error - manual correction needed',
    status: 'Active',
  },
];

const volumeTrend = [
  { date: 'Jan 10', customers: 122000, orders: 448000, products: 8500 },
  { date: 'Jan 11', customers: 123000, orders: 451000, products: 8500 },
  { date: 'Jan 12', customers: 123500, orders: 449000, products: 8520 },
  { date: 'Jan 13', customers: 124000, orders: 452000, products: 8500 },
  { date: 'Jan 14', customers: 124500, orders: 455000, products: 8480 },
  { date: 'Jan 15', customers: 125000, orders: 457000, products: 7450 },
  { date: 'Jan 16', customers: 125000, orders: 520000, products: 8500 },
];

const suggestedAlerts = [
  {
    signal: 'Email NULL rate > 5%',
    priority: 'P1',
    action: 'Create alert rule with threshold: NULL rate > 3%',
    estimatedImpact: 'Prevent customer communication failures',
  },
  {
    signal: 'Order volume variance > 15%',
    priority: 'P2',
    action: 'Set up anomaly detection for daily volume changes',
    estimatedImpact: 'Early detection of data pipeline issues',
  },
  {
    signal: 'Product count drop > 10%',
    priority: 'P2',
    action: 'Monitor for sudden SKU deletions or import failures',
    estimatedImpact: 'Prevent inventory sync issues',
  },
];

export const AnomalyDetectionDashboard: React.FC = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white flex items-center gap-2">
        <ExclamationTriangleIcon className="w-8 h-8 text-yellow-500" />
        Anomaly & Pattern Detection
      </h1>
      <p className="text-gray-400">Detect issues BEFORE users complain</p>

      {/* Key Metrics */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Detection Summary</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <KPICard
            title="Total Anomalies"
            value={anomalyMetrics.totalAnomalies}
            trend={{ value: 3, direction: 'down', label: 'vs yesterday' }}
            status="warning"
          />
          <KPICard
            title="Critical"
            value={anomalyMetrics.criticalAnomalies}
            status="error"
            icon={<ExclamationTriangleIcon className="w-5 h-5 text-red-500" />}
          />
          <KPICard
            title="Resolved Today"
            value={anomalyMetrics.resolvedToday}
            status="success"
          />
          <KPICard
            title="Avg Detection Time"
            value={anomalyMetrics.avgDetectionTime}
            subtitle="Time to alert"
            status="success"
          />
        </div>
      </section>

      {/* Detected Anomalies */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Detected Anomalies (Last 24h)</h2>
        <DataTable
          data={detectedAnomalies}
          columns={[
            { key: 'dataset', label: 'Dataset' },
            { key: 'column', label: 'Column' },
            {
              key: 'anomaly',
              label: 'Anomaly Type',
              render: (value) => (
                <span className="px-2 py-1 bg-purple-500/20 text-purple-400 rounded text-xs font-medium">
                  {value}
                </span>
              ),
            },
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
            { key: 'detected', label: 'Detected At', width: '15%' },
            { key: 'currentValue', label: 'Current', width: '12%' },
            { key: 'expectedValue', label: 'Expected', width: '12%' },
            { key: 'rootCause', label: 'Root Cause Hypothesis', width: '20%' },
            {
              key: 'status',
              label: 'Status',
              render: (value) => (
                <span
                  className={`px-2 py-1 rounded text-xs font-medium ${
                    value === 'Active'
                      ? 'bg-red-500/20 text-red-400'
                      : value === 'Acknowledged'
                      ? 'bg-yellow-500/20 text-yellow-400'
                      : 'bg-green-500/20 text-green-400'
                  }`}
                >
                  {value}
                </span>
              ),
            },
          ]}
          searchable
        />
      </section>

      {/* Volume Trend */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Volume Anomaly Detection</h2>
        <TrendChart
          data={volumeTrend}
          lines={[
            { dataKey: 'customers', name: 'Customers', color: '#3B82F6' },
            { dataKey: 'orders', name: 'Orders', color: '#10B981' },
            { dataKey: 'products', name: 'Products', color: '#F59E0B' },
          ]}
          xAxisKey="date"
          title="Dataset Volume Trends (Last 7 Days)"
          height={300}
        />
        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-blue-900/20 border border-blue-700 rounded-lg p-4">
            <p className="text-sm text-blue-300">
              <strong>Customers:</strong> Steady growth, no anomalies detected
            </p>
          </div>
          <div className="bg-orange-900/20 border border-orange-700 rounded-lg p-4">
            <p className="text-sm text-orange-300">
              <strong>Orders:</strong> ⚠️ +15% spike detected on Jan 16 (Black Friday)
            </p>
          </div>
          <div className="bg-red-900/20 border border-red-700 rounded-lg p-4">
            <p className="text-sm text-red-300">
              <strong>Products:</strong> 🚨 -12% drop on Jan 15 (schema drift detected)
            </p>
          </div>
        </div>
      </section>

      {/* Suggested Proactive Alerts */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <BellAlertIcon className="w-6 h-6 text-yellow-500" />
          Suggested Proactive Alerts
        </h2>
        <DataTable
          data={suggestedAlerts}
          columns={[
            { key: 'signal', label: 'Signal/Pattern', width: '25%' },
            {
              key: 'priority',
              label: 'Priority',
              render: (value) => (
                <span
                  className={`px-2 py-1 rounded text-xs font-medium ${
                    value === 'P1'
                      ? 'bg-red-500/20 text-red-400'
                      : value === 'P2'
                      ? 'bg-yellow-500/20 text-yellow-400'
                      : 'bg-blue-500/20 text-blue-400'
                  }`}
                >
                  {value}
                </span>
              ),
            },
            { key: 'action', label: 'Recommended Alert Rule', width: '35%' },
            { key: 'estimatedImpact', label: 'Estimated Impact', width: '30%' },
          ]}
          pagination={false}
        />
        <div className="mt-4 flex gap-3">
          <button className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors">
            Create Alert Rules
          </button>
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg font-medium transition-colors">
            Configure Thresholds
          </button>
        </div>
      </section>

      {/* AI Insights */}
      <section className="bg-gradient-to-r from-purple-900/30 to-pink-900/30 border border-purple-700 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-white mb-2">🤖 AI-Powered Insights</h3>
        <ul className="space-y-2 text-sm text-purple-300">
          <li>
            • <strong>Pattern Detected:</strong> Email NULL spikes correlate with API deployments - consider pre-deployment
            validation
          </li>
          <li>
            • <strong>Seasonality:</strong> Order volume increases 10-20% on weekends - adjust baseline expectations
          </li>
          <li>
            • <strong>Drift Alert:</strong> Product price distribution shifted significantly - verify if intentional
          </li>
          <li>
            • <strong>Recommendation:</strong> Enable auto-alerting for critical datasets to reduce MTTR by ~60%
          </li>
        </ul>
      </section>
    </div>
  );
};
