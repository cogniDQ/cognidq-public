import React from 'react';
import { KPICard } from '../src/components/widgets/KPICard';
import { TrendChart } from '../src/components/widgets/TrendChart';
import { DistributionChart } from '../src/components/widgets/DistributionChart';
import { DataTable } from '../src/components/widgets/DataTable';
import { ChartBarIcon, UserGroupIcon, CurrencyDollarIcon } from '@heroicons/react/24/outline';

// Dummy data
const roiMetrics = {
  issuesCaught: 127,
  incidentsAvoided: 34,
  costSaved: 285000,
  mostValuableFlowValue: 95000,
};

const issuesTrend = [
  { date: 'Week 1', caught: 28, avoided: 7, production: 2 },
  { date: 'Week 2', caught: 32, avoided: 9, production: 1 },
  { date: 'Week 3', caught: 35, avoided: 10, production: 0 },
  { date: 'Week 4', caught: 32, avoided: 8, production: 1 },
];

const mostValuableFlows = [
  {
    flow: 'Customer Email Validation',
    issuesCaught: 42,
    avgSeverity: 'High',
    estimatedCost: '$95,000',
    impact: 'Prevented email campaign failures',
  },
  {
    flow: 'Order Amount Integrity Check',
    issuesCaught: 28,
    avgSeverity: 'Critical',
    estimatedCost: '$78,000',
    impact: 'Prevented revenue loss from pricing errors',
  },
  {
    flow: 'Product SKU Validation',
    issuesCaught: 19,
    avgSeverity: 'Medium',
    estimatedCost: '$42,000',
    impact: 'Prevented inventory sync failures',
  },
  {
    flow: 'Customer ID Uniqueness',
    issuesCaught: 15,
    avgSeverity: 'Critical',
    estimatedCost: '$38,000',
    impact: 'Prevented duplicate account issues',
  },
  {
    flow: 'Payment Data Completeness',
    issuesCaught: 23,
    avgSeverity: 'High',
    estimatedCost: '$32,000',
    impact: 'Prevented payment processing failures',
  },
];

const userEngagement = [
  { date: 'Week 1', activeUsers: 12, flowsCreated: 8, checksExecuted: 245 },
  { date: 'Week 2', activeUsers: 15, flowsCreated: 12, checksExecuted: 312 },
  { date: 'Week 3', activeUsers: 18, flowsCreated: 15, checksExecuted: 389 },
  { date: 'Week 4', activeUsers: 22, flowsCreated: 18, checksExecuted: 456 },
];

const featureAdoption = [
  { name: 'Flow Builder', value: 85 },
  { name: 'Rule Engine', value: 78 },
  { name: 'Data Ingestion', value: 62 },
  { name: 'Reporting', value: 71 },
  { name: 'AI Assistant', value: 45 },
];

export const AdoptionValueDashboard: React.FC = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white flex items-center gap-2">
        <ChartBarIcon className="w-8 h-8 text-green-500" />
        Adoption & Value: Platform ROI
      </h1>
      <p className="text-gray-400">Demonstrate the business value of your data quality platform</p>

      {/* ROI Metrics */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Business Impact Metrics</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard
            title="Issues Caught Before Production"
            value={roiMetrics.issuesCaught}
            trend={{ value: 18, direction: 'up', label: 'vs last month' }}
            status="success"
            icon={<ChartBarIcon className="w-5 h-5 text-green-500" />}
          />
          <KPICard
            title="Estimated Incidents Avoided"
            value={roiMetrics.incidentsAvoided}
            trend={{ value: 25, direction: 'up', label: 'vs last month' }}
            status="success"
          />
          <KPICard
            title="Estimated Cost Saved"
            value={`$${(roiMetrics.costSaved / 1000).toFixed(0)}K`}
            subtitle="This month"
            status="success"
            icon={<CurrencyDollarIcon className="w-5 h-5 text-green-500" />}
          />
          <KPICard
            title="Most Valuable Flow"
            value={`$${(roiMetrics.mostValuableFlowValue / 1000).toFixed(0)}K`}
            subtitle="Customer Email Validation"
            status="success"
          />
        </div>
      </section>

      {/* Issues Caught Trend */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Issue Detection Over Time</h2>
        <TrendChart
          data={issuesTrend}
          lines={[
            { dataKey: 'caught', name: 'Issues Caught', color: '#10B981' },
            { dataKey: 'avoided', name: 'Incidents Avoided', color: '#3B82F6' },
            { dataKey: 'production', name: 'Reached Production', color: '#EF4444' },
          ]}
          xAxisKey="date"
          title="Proactive vs Reactive Issue Resolution"
          height={300}
        />
      </section>

      {/* Most Valuable Flows */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Most Valuable Flows</h2>
        <DataTable
          data={mostValuableFlows}
          columns={[
            { key: 'flow', label: 'Flow Name', width: '25%' },
            { key: 'issuesCaught', label: 'Issues Caught' },
            {
              key: 'avgSeverity',
              label: 'Avg Severity',
              render: (value) => (
                <span
                  className={`px-2 py-1 rounded text-xs font-medium ${
                    value === 'Critical'
                      ? 'bg-red-500/20 text-red-400'
                      : value === 'High'
                      ? 'bg-orange-500/20 text-orange-400'
                      : 'bg-yellow-500/20 text-yellow-400'
                  }`}
                >
                  {value}
                </span>
              ),
            },
            {
              key: 'estimatedCost',
              label: 'Est. Cost Saved',
              render: (value) => <span className="text-green-400 font-semibold">{value}</span>,
            },
            { key: 'impact', label: 'Business Impact', width: '30%' },
          ]}
        />
      </section>

      {/* User Engagement */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <UserGroupIcon className="w-6 h-6" />
          User Engagement & Activity
        </h2>
        <TrendChart
          data={userEngagement}
          lines={[
            { dataKey: 'activeUsers', name: 'Active Users', color: '#8B5CF6' },
            { dataKey: 'flowsCreated', name: 'Flows Created', color: '#3B82F6' },
            { dataKey: 'checksExecuted', name: 'Checks Executed', color: '#10B981' },
          ]}
          xAxisKey="date"
          title="Platform Usage Growth"
          height={300}
        />
      </section>

      {/* Feature Adoption */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Feature Adoption Rates</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <DistributionChart
            data={featureAdoption}
            type="bar"
            dataKey="value"
            nameKey="name"
            title="Adoption by Feature (%)"
          />
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
            <h3 className="text-md font-semibold text-white mb-4">Feature Usage Details</h3>
            <div className="space-y-3">
              {featureAdoption.map((feature) => (
                <div key={feature.name}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-gray-300">{feature.name}</span>
                    <span className="text-sm text-white font-medium">{feature.value}%</span>
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full ${
                        feature.value >= 70 ? 'bg-green-500' : feature.value >= 50 ? 'bg-yellow-500' : 'bg-red-500'
                      }`}
                      style={{ width: `${feature.value}%` }}
                    ></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ROI Summary */}
      <section className="bg-gradient-to-r from-green-900/30 to-blue-900/30 border border-green-700 rounded-lg p-6">
        <h3 className="text-xl font-semibold text-white mb-4">💰 ROI Summary</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <h4 className="text-sm font-medium text-gray-300 mb-3">This Month</h4>
            <ul className="space-y-2 text-sm text-green-300">
              <li>• <strong>127 issues</strong> caught before reaching production</li>
              <li>• <strong>34 incidents</strong> prevented (estimated)</li>
              <li>• <strong>$285K saved</strong> in incident costs</li>
              <li>• <strong>22 active users</strong> leveraging the platform</li>
              <li>• <strong>456 checks</strong> executed automatically</li>
            </ul>
          </div>
          <div>
            <h4 className="text-sm font-medium text-gray-300 mb-3">Key Achievements</h4>
            <ul className="space-y-2 text-sm text-blue-300">
              <li>• <strong>85% adoption</strong> of Flow Builder feature</li>
              <li>• <strong>78% adoption</strong> of Rule Engine</li>
              <li>• <strong>18% growth</strong> in active users (vs last month)</li>
              <li>• <strong>86% reduction</strong> in production issues</li>
              <li>• <strong>5 high-value flows</strong> preventing $285K+ in costs</li>
            </ul>
          </div>
        </div>
      </section>

      {/* Next Steps */}
      <section className="bg-purple-900/20 border border-purple-700 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-white mb-2">🎯 Growth Opportunities</h3>
        <ul className="space-y-2 text-sm text-purple-300">
          <li>• Increase AI Assistant adoption (currently 45%) through training sessions</li>
          <li>• Expand Data Ingestion usage (62%) by automating more data sources</li>
          <li>• Target 95%+ issue prevention rate by adding proactive anomaly detection</li>
          <li>• Aim for $350K+ monthly cost savings by onboarding 10 more critical datasets</li>
        </ul>
      </section>
    </div>
  );
};
