import React, { useState } from 'react';
import { DataTable } from '../src/components/widgets/DataTable';
import { KPICard } from '../src/components/widgets/KPICard';
import { Sparkline } from '../src/components/widgets/Sparkline';
import {
  PlayCircleIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';

// Dummy data for a flow execution
const flowRunHeader = {
  flowName: 'Customer Data Quality Validation',
  runId: 'exec-2026-01-16-001',
  trigger: 'Scheduled',
  startTime: '2026-01-16 08:00:00',
  duration: '2m 34s',
  status: 'Partial Success',
  actor: 'system',
};

const datasetsInvolved = [
  {
    dataset: 'customers',
    source: 'PostgreSQL - Production',
    rowsAnalyzed: 125000,
    schemaVersion: 'v2.3',
    status: 'Success',
    volumeChange: '+2.3%',
    schemaDrift: false,
  },
  {
    dataset: 'orders',
    source: 'PostgreSQL - Production',
    rowsAnalyzed: 450000,
    schemaVersion: 'v1.8',
    status: 'Success',
    volumeChange: '+5.1%',
    schemaDrift: false,
  },
  {
    dataset: 'products',
    source: 'PostgreSQL - Production',
    rowsAnalyzed: 8500,
    schemaVersion: 'v3.0',
    status: 'Warning',
    volumeChange: '-12.4%',
    schemaDrift: true,
  },
];

const checksApplied = [
  {
    check: 'Email Completeness',
    type: 'Completeness',
    dataset: 'customers',
    column: 'email',
    threshold: '≥ 95%',
    result: 'Failed',
    actualValue: '94.1%',
    previousValue: '99.8%',
    trend: [99.5, 99.7, 99.8, 99.6, 99.4, 94.1],
  },
  {
    check: 'Email Format Validation',
    type: 'Validity',
    dataset: 'customers',
    column: 'email',
    threshold: '≥ 99%',
    result: 'Passed',
    actualValue: '99.6%',
    previousValue: '99.5%',
    trend: [99.3, 99.4, 99.5, 99.6, 99.6, 99.6],
  },
  {
    check: 'Customer ID Uniqueness',
    type: 'Uniqueness',
    dataset: 'customers',
    column: 'customer_id',
    threshold: '100%',
    result: 'Passed',
    actualValue: '100%',
    previousValue: '100%',
    trend: [100, 100, 100, 100, 100, 100],
  },
  {
    check: 'Order Amount Range',
    type: 'Validity',
    dataset: 'orders',
    column: 'amount',
    threshold: '0-10000',
    result: 'Warning',
    actualValue: '98.2%',
    previousValue: '99.1%',
    trend: [99.0, 99.1, 99.1, 99.0, 98.8, 98.2],
  },
  {
    check: 'Product SKU Format',
    type: 'Conformity',
    dataset: 'products',
    column: 'sku',
    threshold: 'ABC-##### pattern',
    result: 'Passed',
    actualValue: '100%',
    previousValue: '100%',
    trend: [100, 100, 100, 100, 100, 100],
  },
];

const runMetrics = {
  totalChecks: 5,
  passedChecks: 3,
  warningChecks: 1,
  failedChecks: 1,
  skippedChecks: 0,
  passRate: 60,
};

const failureDetails = {
  check: 'Email Completeness',
  rule: 'At least 95% of customer records must have a non-null email address',
  reason:
    'The completeness rate dropped from 99.8% to 94.1%, indicating that 5.9% of records now have null email values.',
  sampleRows: [
    { customer_id: 'C-10234', name: 'John Doe', email: null, created_at: '2026-01-15' },
    { customer_id: 'C-10567', name: 'Jane Smith', email: null, created_at: '2026-01-15' },
    { customer_id: 'C-10892', name: 'Bob Johnson', email: null, created_at: '2026-01-15' },
  ],
  businessImpact: 'High - Email campaigns cannot reach 5.9% of customers (~7,375 records)',
};

export const FlowExecutionReport: React.FC = () => {
  const [selectedFailure, setSelectedFailure] = useState<any>(null);

  return (
    <div className="space-y-6">
      {/* Flow Run Header */}
      <section className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 border border-blue-700 rounded-lg p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-white mb-2">{flowRunHeader.flowName}</h1>
            <div className="flex items-center gap-4 text-sm text-gray-300">
              <span className="flex items-center gap-1">
                <PlayCircleIcon className="w-4 h-4" />
                Run ID: {flowRunHeader.runId}
              </span>
              <span>Trigger: {flowRunHeader.trigger}</span>
              <span>Actor: {flowRunHeader.actor}</span>
            </div>
          </div>
          <div
            className={`px-4 py-2 rounded-full text-sm font-medium ${
              flowRunHeader.status === 'Success'
                ? 'bg-green-500/20 text-green-400'
                : flowRunHeader.status === 'Partial Success'
                ? 'bg-yellow-500/20 text-yellow-400'
                : 'bg-red-500/20 text-red-400'
            }`}
          >
            {flowRunHeader.status}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-gray-400">Start Time</p>
            <p className="text-lg font-semibold text-white">{flowRunHeader.startTime}</p>
          </div>
          <div>
            <p className="text-sm text-gray-400">Duration</p>
            <p className="text-lg font-semibold text-white">{flowRunHeader.duration}</p>
          </div>
        </div>
      </section>

      {/* Datasets Involved */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">📦 Datasets Involved</h2>
        <DataTable
          data={datasetsInvolved}
          columns={[
            { key: 'dataset', label: 'Dataset' },
            { key: 'source', label: 'Source' },
            {
              key: 'rowsAnalyzed',
              label: 'Rows Analyzed',
              render: (value) => value.toLocaleString(),
            },
            { key: 'schemaVersion', label: 'Schema Version' },
            {
              key: 'status',
              label: 'Status',
              render: (value) => (
                <span
                  className={`px-2 py-1 rounded text-xs font-medium ${
                    value === 'Success'
                      ? 'bg-green-500/20 text-green-400'
                      : value === 'Warning'
                      ? 'bg-yellow-500/20 text-yellow-400'
                      : 'bg-red-500/20 text-red-400'
                  }`}
                >
                  {value}
                </span>
              ),
            },
            {
              key: 'volumeChange',
              label: 'Volume Change',
              render: (value) => (
                <span className={value.startsWith('+') ? 'text-green-400' : 'text-red-400'}>
                  {value}
                </span>
              ),
            },
            {
              key: 'schemaDrift',
              label: 'Schema Drift',
              render: (value) =>
                value ? (
                  <span className="text-yellow-400 flex items-center gap-1">
                    <ExclamationTriangleIcon className="w-4 h-4" /> Yes
                  </span>
                ) : (
                  <span className="text-gray-400">No</span>
                ),
            },
          ]}
        />
      </section>

      {/* Run-Level Metrics */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">📊 Run-Level Metrics</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <KPICard title="Total Checks" value={runMetrics.totalChecks} status="neutral" />
          <KPICard
            title="Passed"
            value={runMetrics.passedChecks}
            status="success"
            icon={<CheckCircleIcon className="w-5 h-5 text-green-500" />}
          />
          <KPICard
            title="Warnings"
            value={runMetrics.warningChecks}
            status="warning"
            icon={<ExclamationTriangleIcon className="w-5 h-5 text-yellow-500" />}
          />
          <KPICard
            title="Failed"
            value={runMetrics.failedChecks}
            status="error"
            icon={<XCircleIcon className="w-5 h-5 text-red-500" />}
          />
          <KPICard title="Skipped" value={runMetrics.skippedChecks} status="neutral" />
          <KPICard
            title="Pass Rate"
            value={`${runMetrics.passRate}%`}
            status={runMetrics.passRate >= 80 ? 'success' : runMetrics.passRate >= 60 ? 'warning' : 'error'}
          />
        </div>
      </section>

      {/* Checks Applied */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">🧪 Checks Applied</h2>
        <DataTable
          data={checksApplied}
          columns={[
            { key: 'check', label: 'Check Name', width: '20%' },
            { key: 'type', label: 'Type' },
            { key: 'dataset', label: 'Dataset' },
            { key: 'column', label: 'Column' },
            { key: 'threshold', label: 'Threshold' },
            {
              key: 'result',
              label: 'Result',
              render: (value) => (
                <span
                  className={`px-2 py-1 rounded text-xs font-medium ${
                    value === 'Passed'
                      ? 'bg-green-500/20 text-green-400'
                      : value === 'Warning'
                      ? 'bg-yellow-500/20 text-yellow-400'
                      : 'bg-red-500/20 text-red-400'
                  }`}
                >
                  {value}
                </span>
              ),
            },
            { key: 'actualValue', label: 'Actual Value' },
            {
              key: 'trend',
              label: 'Trend',
              render: (value, row) => (
                <div className="flex items-center gap-2">
                  <Sparkline data={value} color={row.result === 'Failed' ? '#EF4444' : '#10B981'} />
                  <span className="text-xs text-gray-400">{row.previousValue}</span>
                </div>
              ),
            },
          ]}
          searchable
        />
      </section>

      {/* Failure Deep Dive */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">🧬 Failure Deep Dive</h2>
        <div className="bg-red-900/20 border border-red-700 rounded-lg p-6">
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-white mb-2">{failureDetails.check}</h3>
            <p className="text-sm text-gray-300 mb-4">
              <strong>Rule:</strong> {failureDetails.rule}
            </p>
            <div className="bg-gray-800 border border-gray-700 rounded p-4 mb-4">
              <p className="text-sm text-gray-300">
                <strong>Why it failed:</strong> {failureDetails.reason}
              </p>
            </div>
            <div className="bg-orange-900/20 border border-orange-700 rounded p-4 mb-4">
              <p className="text-sm text-orange-300">
                <strong>Business Impact:</strong> {failureDetails.businessImpact}
              </p>
            </div>
          </div>
          <div>
            <h4 className="text-md font-semibold text-white mb-2">Sample Faulty Rows</h4>
            <DataTable
              data={failureDetails.sampleRows}
              columns={[
                { key: 'customer_id', label: 'Customer ID' },
                { key: 'name', label: 'Name' },
                {
                  key: 'email',
                  label: 'Email',
                  render: (value) => (
                    <span className="text-red-400">{value === null ? 'NULL' : value}</span>
                  ),
                },
                { key: 'created_at', label: 'Created At' },
              ]}
              pagination={false}
            />
          </div>
        </div>
      </section>

      {/* Actions */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">🛠️ Actions</h2>
        <div className="flex flex-wrap gap-3">
          <button className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium flex items-center gap-2 transition-colors">
            <ArrowPathIcon className="w-5 h-5" />
            Re-run Flow
          </button>
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg font-medium transition-colors">
            Disable Check
          </button>
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg font-medium transition-colors">
            Adjust Threshold
          </button>
          <button className="px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg font-medium transition-colors">
            Create Issue
          </button>
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg font-medium transition-colors">
            Notify Owner
          </button>
        </div>
      </section>
    </div>
  );
};
