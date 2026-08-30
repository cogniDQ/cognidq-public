import React from 'react';
import { KPICard } from '../src/components/widgets/KPICard';
import { TrendChart } from '../src/components/widgets/TrendChart';
import { DistributionChart } from '../src/components/widgets/DistributionChart';
import { GaugeChart } from '../src/components/widgets/GaugeChart';
import {
  CircleStackIcon,
  PlayCircleIcon,
  CheckBadgeIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline';

// Dummy data
const coverageData = {
  totalDatasets: 156,
  datasetsAnalyzed: 142,
  datasetsLast24h: 89,
  datasetsLast7d: 125,
  datasetsLast30d: 142,
  datasetsWithFlows: 128,
  datasetsWithoutFlows: 14,
};

const flowData = {
  totalFlows: 78,
  activeFlows: 65,
  pausedFlows: 8,
  failedFlows: 5,
  avgDatasetsPerFlow: 2.3,
  avgChecksPerFlow: 12.5,
};

const checksData = {
  totalChecks: 975,
  byDimension: [
    { name: 'Completeness', value: 285 },
    { name: 'Validity', value: 220 },
    { name: 'Uniqueness', value: 165 },
    { name: 'Consistency', value: 145 },
    { name: 'Timeliness', value: 98 },
    { name: 'Custom', value: 62 },
  ],
  standardChecks: 913,
  customChecks: 62,
};

const governanceData = {
  datasetsWithOwner: 89,
  datasetsWithCriticality: 76,
  datasetsWithDomain: 82,
  datasetsWithThresholds: 71,
  checksWithSLA: 68,
  checksWithSeverity: 85,
  checksWithOwner: 72,
};

const trendData = [
  { date: 'Week 1', datasets: 120, flows: 58, checks: 720 },
  { date: 'Week 2', datasets: 128, flows: 62, checks: 806 },
  { date: 'Week 3', datasets: 135, flows: 68, checks: 850 },
  { date: 'Week 4', datasets: 142, flows: 78, checks: 975 },
];

export const OverviewDashboard: React.FC = () => {
  return (
    <div className="space-y-6">
      {/* Coverage & Inventory */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <CircleStackIcon className="w-6 h-6" />
          Coverage & Inventory
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard
            title="Total Datasets"
            value={coverageData.totalDatasets}
            status="neutral"
            icon={<CircleStackIcon className="w-5 h-5" />}
          />
          <KPICard
            title="Datasets Analyzed"
            value={coverageData.datasetsAnalyzed}
            subtitle={`${((coverageData.datasetsAnalyzed / coverageData.totalDatasets) * 100).toFixed(1)}% of total`}
            status="success"
          />
          <KPICard
            title="Analyzed (Last 24h)"
            value={coverageData.datasetsLast24h}
            trend={{ value: 12, direction: 'up', label: 'vs yesterday' }}
            status="success"
          />
          <KPICard
            title="Without Flows"
            value={coverageData.datasetsWithoutFlows}
            status="warning"
            icon={<span className="text-yellow-500">⚠️</span>}
          />
        </div>
      </section>

      {/* Flow Inventory */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <PlayCircleIcon className="w-6 h-6" />
          Flow Inventory
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard title="Total Flows" value={flowData.totalFlows} status="neutral" />
          <KPICard
            title="Active Flows"
            value={flowData.activeFlows}
            subtitle={`${((flowData.activeFlows / flowData.totalFlows) * 100).toFixed(0)}% active`}
            status="success"
          />
          <KPICard
            title="Paused Flows"
            value={flowData.pausedFlows}
            status="warning"
          />
          <KPICard
            title="Failed Flows"
            value={flowData.failedFlows}
            status="error"
          />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <KPICard
            title="Avg Datasets per Flow"
            value={flowData.avgDatasetsPerFlow}
            status="neutral"
          />
          <KPICard
            title="Avg Checks per Flow"
            value={flowData.avgChecksPerFlow}
            status="neutral"
          />
        </div>
      </section>

      {/* Checks Inventory */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <CheckBadgeIcon className="w-6 h-6" />
          Checks Inventory
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
          <KPICard title="Total Checks" value={checksData.totalChecks} status="neutral" />
          <KPICard
            title="Standard Checks"
            value={checksData.standardChecks}
            subtitle={`${((checksData.standardChecks / checksData.totalChecks) * 100).toFixed(0)}% of total`}
            status="success"
          />
          <KPICard
            title="Custom Business Rules"
            value={checksData.customChecks}
            subtitle={`${((checksData.customChecks / checksData.totalChecks) * 100).toFixed(0)}% of total`}
            status="neutral"
          />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <DistributionChart
            data={checksData.byDimension}
            type="bar"
            dataKey="value"
            nameKey="name"
            title="Checks by Dimension"
            height={300}
          />
          <DistributionChart
            data={checksData.byDimension}
            type="pie"
            dataKey="value"
            nameKey="name"
            title="Distribution by Type"
            height={300}
          />
        </div>
      </section>

      {/* Governance Maturity */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <ShieldCheckIcon className="w-6 h-6" />
          Governance Maturity
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <GaugeChart
            value={governanceData.datasetsWithOwner}
            title="Datasets with Owner"
            label="Ownership Coverage"
          />
          <GaugeChart
            value={governanceData.datasetsWithCriticality}
            title="With Criticality"
            label="Risk Classification"
          />
          <GaugeChart
            value={governanceData.datasetsWithDomain}
            title="With Domain"
            label="Domain Assignment"
          />
          <GaugeChart
            value={governanceData.datasetsWithThresholds}
            title="With Thresholds"
            label="Threshold Definition"
          />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
          <KPICard
            title="Checks with SLA"
            value={`${governanceData.checksWithSLA}%`}
            status={governanceData.checksWithSLA >= 80 ? 'success' : 'warning'}
          />
          <KPICard
            title="Checks with Severity"
            value={`${governanceData.checksWithSeverity}%`}
            status={governanceData.checksWithSeverity >= 80 ? 'success' : 'warning'}
          />
          <KPICard
            title="Checks with Owner"
            value={`${governanceData.checksWithOwner}%`}
            status={governanceData.checksWithOwner >= 80 ? 'success' : 'warning'}
          />
        </div>
      </section>

      {/* High-Level Trends */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">High-Level Trends</h2>
        <TrendChart
          data={trendData}
          lines={[
            { dataKey: 'datasets', name: 'Datasets Analyzed', color: '#3B82F6' },
            { dataKey: 'flows', name: 'Flow Executions', color: '#10B981' },
            { dataKey: 'checks', name: 'Checks Executed', color: '#F59E0B' },
          ]}
          xAxisKey="date"
          title="Coverage Growth Over Time"
          height={350}
        />
      </section>

      {/* Note */}
      <div className="bg-blue-900/20 border border-blue-700 rounded-lg p-4">
        <p className="text-sm text-blue-300">
          📌 <strong>Note:</strong> This dashboard focuses on coverage & adoption metrics. For quality scores and
          detailed issue analysis, refer to the Flow Execution Report and Dataset Quality Profile dashboards.
        </p>
      </div>
    </div>
  );
};
