import React from 'react';
import { KPICard } from '../src/components/widgets/KPICard';
import { TrendChart } from '../src/components/widgets/TrendChart';
import { DataTable } from '../src/components/widgets/DataTable';
import { GaugeChart } from '../src/components/widgets/GaugeChart';
import { CircleStackIcon, UserIcon, ShieldCheckIcon } from '@heroicons/react/24/outline';

// Dummy data for a single dataset
const datasetIdentity = {
  name: 'customers',
  owner: 'Data Team',
  domain: 'Customer Management',
  criticality: 'High',
  upstreamSystems: ['Salesforce', 'Web Portal', 'Mobile App'],
  downstreamConsumers: ['Analytics Dashboard', 'Email Campaign System', 'Billing Service'],
};

const qualitySummary = {
  overallScore: 87,
  completeness: 94,
  validity: 92,
  uniqueness: 100,
  consistency: 85,
  timeliness: 78,
  worstCheck: 'Email Completeness (94.1%)',
  mostUnstableColumn: 'phone_number',
  daysSinceHealthy: 2,
};

const qualityTrend = [
  { date: 'Jan 10', completeness: 99, validity: 93, uniqueness: 100, consistency: 86 },
  { date: 'Jan 11', completeness: 99, validity: 92, uniqueness: 100, consistency: 85 },
  { date: 'Jan 12', completeness: 98, validity: 93, uniqueness: 100, consistency: 87 },
  { date: 'Jan 13', completeness: 98, validity: 91, uniqueness: 100, consistency: 84 },
  { date: 'Jan 14', completeness: 97, validity: 92, uniqueness: 100, consistency: 86 },
  { date: 'Jan 15', completeness: 96, validity: 92, uniqueness: 100, consistency: 85 },
  { date: 'Jan 16', completeness: 94, validity: 92, uniqueness: 100, consistency: 85 },
];

const checkCoverage = [
  { column: 'customer_id', checks: 3, businessRules: 1, thresholds: true, coverage: 100 },
  { column: 'email', checks: 5, businessRules: 2, thresholds: true, coverage: 100 },
  { column: 'phone_number', checks: 2, businessRules: 0, thresholds: true, coverage: 60 },
  { column: 'created_at', checks: 2, businessRules: 1, thresholds: true, coverage: 80 },
  { column: 'last_login', checks: 1, businessRules: 0, thresholds: false, coverage: 40 },
  { column: 'address', checks: 0, businessRules: 0, thresholds: false, coverage: 0 },
  { column: 'city', checks: 0, businessRules: 0, thresholds: false, coverage: 0 },
  { column: 'country', checks: 1, businessRules: 0, thresholds: false, coverage: 30 },
];

export const DatasetQualityProfile: React.FC = () => {
  const columnsWithoutChecks = checkCoverage.filter((c) => c.checks === 0);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Dataset Quality Profile: {datasetIdentity.name}</h1>

      {/* Dataset Identity */}
      <section className="bg-gradient-to-r from-purple-900/30 to-blue-900/30 border border-purple-700 rounded-lg p-6">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <CircleStackIcon className="w-6 h-6" />
          Dataset Identity
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div>
            <p className="text-sm text-gray-400 mb-1">Owner</p>
            <p className="text-lg font-semibold text-white flex items-center gap-2">
              <UserIcon className="w-5 h-5" />
              {datasetIdentity.owner}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-400 mb-1">Domain</p>
            <p className="text-lg font-semibold text-white">{datasetIdentity.domain}</p>
          </div>
          <div>
            <p className="text-sm text-gray-400 mb-1">Criticality</p>
            <p className="text-lg font-semibold text-orange-400 flex items-center gap-2">
              <ShieldCheckIcon className="w-5 h-5" />
              {datasetIdentity.criticality}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-400 mb-1">Upstream Systems</p>
            <div className="flex flex-wrap gap-2">
              {datasetIdentity.upstreamSystems.map((sys) => (
                <span key={sys} className="px-2 py-1 bg-blue-500/20 text-blue-400 rounded text-xs">
                  {sys}
                </span>
              ))}
            </div>
          </div>
          <div className="md:col-span-2">
            <p className="text-sm text-gray-400 mb-1">Downstream Consumers</p>
            <div className="flex flex-wrap gap-2">
              {datasetIdentity.downstreamConsumers.map((con) => (
                <span key={con} className="px-2 py-1 bg-green-500/20 text-green-400 rounded text-xs">
                  {con}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Quality Summary */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Quality Summary (All Flows Aggregated)</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <GaugeChart value={qualitySummary.overallScore} title="Overall Quality Score" label="Data Quality" />
          <GaugeChart value={qualitySummary.completeness} title="Completeness" />
          <GaugeChart value={qualitySummary.validity} title="Validity" />
          <GaugeChart value={qualitySummary.uniqueness} title="Uniqueness" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <KPICard
            title="Worst Check"
            value={qualitySummary.worstCheck}
            status="warning"
            subtitle="Needs attention"
          />
          <KPICard
            title="Most Unstable Column"
            value={qualitySummary.mostUnstableColumn}
            status="warning"
            subtitle="High variance"
          />
          <KPICard
            title="Days Since Healthy"
            value={qualitySummary.daysSinceHealthy}
            status="error"
            subtitle="Last 100% pass rate"
          />
        </div>
      </section>

      {/* Quality Trend by Dimension */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Quality Trend by Dimension</h2>
        <TrendChart
          data={qualityTrend}
          lines={[
            { dataKey: 'completeness', name: 'Completeness', color: '#3B82F6' },
            { dataKey: 'validity', name: 'Validity', color: '#10B981' },
            { dataKey: 'uniqueness', name: 'Uniqueness', color: '#8B5CF6' },
            { dataKey: 'consistency', name: 'Consistency', color: '#F59E0B' },
          ]}
          xAxisKey="date"
          title="Quality Scores Over Time (Last 7 Days)"
          height={350}
        />
      </section>

      {/* Check Coverage */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Check Coverage by Column</h2>
        {columnsWithoutChecks.length > 0 && (
          <div className="bg-yellow-900/20 border border-yellow-700 rounded-lg p-4 mb-4">
            <p className="text-sm text-yellow-300 flex items-center gap-2">
              ⚠️ <strong>Warning:</strong> {columnsWithoutChecks.length} column(s) have no quality checks:{' '}
              {columnsWithoutChecks.map((c) => c.column).join(', ')}
            </p>
          </div>
        )}
        <DataTable
          data={checkCoverage}
          columns={[
            { key: 'column', label: 'Column Name', width: '25%' },
            { key: 'checks', label: 'Total Checks' },
            { key: 'businessRules', label: 'Business Rules' },
            {
              key: 'thresholds',
              label: 'Has Thresholds',
              render: (value) => (
                <span className={value ? 'text-green-400' : 'text-red-400'}>{value ? 'Yes' : 'No'}</span>
              ),
            },
            {
              key: 'coverage',
              label: 'Coverage %',
              render: (value) => (
                <div className="flex items-center gap-2">
                  <div className="w-full bg-gray-700 rounded-full h-2 max-w-[100px]">
                    <div
                      className={`h-2 rounded-full ${
                        value >= 80 ? 'bg-green-500' : value >= 50 ? 'bg-yellow-500' : 'bg-red-500'
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

      {/* Recommendations */}
      <section className="bg-blue-900/20 border border-blue-700 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-white mb-2">💡 Recommendations</h3>
        <ul className="space-y-2 text-sm text-blue-300">
          <li>• Add completeness and validity checks for 'address', 'city' columns</li>
          <li>• Investigate declining completeness trend (99% → 94% in 7 days)</li>
          <li>• Review 'phone_number' column - high instability detected</li>
          <li>• Define thresholds for 'last_login', 'country' checks</li>
        </ul>
      </section>
    </div>
  );
};
