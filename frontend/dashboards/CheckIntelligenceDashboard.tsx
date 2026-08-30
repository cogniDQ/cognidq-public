import React from 'react';
import { DataTable } from '../src/components/widgets/DataTable';
import { KPICard } from '../src/components/widgets/KPICard';
import { DistributionChart } from '../src/components/widgets/DistributionChart';

// Dummy data
const checkIntelligence = {
  noisyChecks: 12,
  alwaysPassingChecks: 8,
  alwaysFailingChecks: 3,
  duplicateChecks: 5,
  avgCheckEffectiveness: 74,
};

const problematicChecks = [
  {
    check: 'Order Status Value Range',
    issue: 'Flapping',
    failureRate: 45,
    recommendation: 'Threshold likely too strict - failed in 45% of runs',
    action: 'Adjust threshold or review data expectations',
    effectiveness: 25,
  },
  {
    check: 'Product Name Format',
    issue: 'Always Passing',
    failureRate: 0,
    recommendation: 'Check passed 100% of time in last 90 days - may be too lenient',
    action: 'Review check criteria or disable if not valuable',
    effectiveness: 10,
  },
  {
    check: 'Inventory Level Range',
    issue: 'Always Failing',
    failureRate: 92,
    recommendation: 'Failed in 92% of runs - threshold or logic likely misconfigured',
    action: 'Reconfigure check or update expected range',
    effectiveness: 5,
  },
  {
    check: 'Email Format (Regex A)',
    issue: 'Duplicate',
    failureRate: 15,
    recommendation: 'Similar check "Email Format (Regex B)" exists - consider merging',
    action: 'Consolidate duplicate checks',
    effectiveness: 40,
  },
  {
    check: 'Customer ID Not Null',
    issue: 'Noisy',
    failureRate: 38,
    recommendation: 'Result fluctuates significantly - investigate root cause',
    action: 'Stabilize data source or adjust check sensitivity',
    effectiveness: 35,
  },
];

const checkTypeDistribution = [
  { name: 'Effective', value: 825 },
  { name: 'Noisy', value: 78 },
  { name: 'Always Pass', value: 42 },
  { name: 'Always Fail', value: 18 },
  { name: 'Duplicate', value: 12 },
];

export const CheckIntelligenceDashboard: React.FC = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Check Intelligence: Are Our Checks Actually Good? 🌟</h1>

      {/* Key Metrics */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Check Health Metrics</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <KPICard
            title="Noisy Checks"
            value={checkIntelligence.noisyChecks}
            subtitle="Flapping results"
            status="warning"
          />
          <KPICard
            title="Always Passing"
            value={checkIntelligence.alwaysPassingChecks}
            subtitle="Potentially useless"
            status="warning"
          />
          <KPICard
            title="Always Failing"
            value={checkIntelligence.alwaysFailingChecks}
            subtitle="Misconfigured"
            status="error"
          />
          <KPICard
            title="Duplicate Checks"
            value={checkIntelligence.duplicateChecks}
            subtitle="Can be merged"
            status="warning"
          />
          <KPICard
            title="Avg Effectiveness"
            value={`${checkIntelligence.avgCheckEffectiveness}%`}
            subtitle="Overall check quality"
            status={checkIntelligence.avgCheckEffectiveness >= 70 ? 'success' : 'warning'}
          />
        </div>
      </section>

      {/* Distribution */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Check Distribution by Health Status</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <DistributionChart
            data={checkTypeDistribution}
            type="bar"
            dataKey="value"
            nameKey="name"
            title="Checks by Status"
          />
          <DistributionChart
            data={checkTypeDistribution}
            type="pie"
            dataKey="value"
            nameKey="name"
            title="Proportion of Check Issues"
          />
        </div>
      </section>

      {/* Problematic Checks */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Problematic Checks Requiring Attention</h2>
        <DataTable
          data={problematicChecks}
          columns={[
            { key: 'check', label: 'Check Name', width: '20%' },
            {
              key: 'issue',
              label: 'Issue Type',
              render: (value) => (
                <span
                  className={`px-2 py-1 rounded text-xs font-medium ${
                    value === 'Always Failing'
                      ? 'bg-red-500/20 text-red-400'
                      : value === 'Flapping' || value === 'Noisy'
                      ? 'bg-yellow-500/20 text-yellow-400'
                      : 'bg-blue-500/20 text-blue-400'
                  }`}
                >
                  {value}
                </span>
              ),
            },
            {
              key: 'failureRate',
              label: 'Failure Rate',
              render: (value) => (
                <span
                  className={
                    value >= 80
                      ? 'text-red-400'
                      : value >= 40
                      ? 'text-yellow-400'
                      : value === 0
                      ? 'text-blue-400'
                      : 'text-green-400'
                  }
                >
                  {value}%
                </span>
              ),
            },
            { key: 'recommendation', label: 'Analysis', width: '30%' },
            { key: 'action', label: 'Recommended Action', width: '25%' },
            {
              key: 'effectiveness',
              label: 'Effectiveness',
              render: (value) => (
                <div className="flex items-center gap-2">
                  <div className="w-full bg-gray-700 rounded-full h-2 max-w-[80px]">
                    <div
                      className={`h-2 rounded-full ${
                        value >= 70 ? 'bg-green-500' : value >= 40 ? 'bg-yellow-500' : 'bg-red-500'
                      }`}
                      style={{ width: `${value}%` }}
                    ></div>
                  </div>
                  <span className="text-sm">{value}%</span>
                </div>
              ),
            },
          ]}
          searchable
        />
      </section>

      {/* Insights */}
      <section className="bg-purple-900/20 border border-purple-700 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-white mb-2">🧠 Key Insights</h3>
        <ul className="space-y-2 text-sm text-purple-300">
          <li>
            • <strong>Noisy Checks:</strong> 12 checks show inconsistent results - review thresholds and data patterns
          </li>
          <li>
            • <strong>Always Passing:</strong> 8 checks never fail - consider stricter criteria or disable if not adding
            value
          </li>
          <li>
            • <strong>Always Failing:</strong> 3 checks consistently fail - likely misconfigured, fix or remove
          </li>
          <li>
            • <strong>Duplicates:</strong> 5 redundant checks detected - consolidate to reduce noise and overhead
          </li>
          <li>
            • <strong>Recommendation:</strong> Focus on improving check effectiveness - target 85%+ effectiveness rate
          </li>
        </ul>
      </section>
    </div>
  );
};
