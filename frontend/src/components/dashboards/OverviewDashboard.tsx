import React, { useState, useEffect } from 'react';
import { KPICard } from '../widgets/KPICard';
import { TrendChart } from '../widgets/TrendChart';
import { DistributionChart } from '../widgets/DistributionChart';
import { GaugeChart } from '../widgets/GaugeChart';
import { PeriodSelector } from '../widgets/PeriodSelector';
import {
  CircleStackIcon,
  PlayCircleIcon,
  CheckBadgeIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import {
  getCoverageInventory,
  getCheckInventory,
  getGovernanceMaturity,
  getCoverageTrend,
  type CoverageInventoryResponse,
  type CheckInventoryResponse,
  type GovernanceMaturityResponse,
  type CoverageTrendResponse,
} from '../../services/kqiService';

export const OverviewDashboard: React.FC = () => {
  const { currentWorkspace } = useWorkspace();
  const [period, setPeriod] = useState('30d');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inventory, setInventory] = useState<CoverageInventoryResponse | null>(null);
  const [checks, setChecks] = useState<CheckInventoryResponse | null>(null);
  const [maturity, setMaturity] = useState<GovernanceMaturityResponse | null>(null);
  const [trend, setTrend] = useState<CoverageTrendResponse | null>(null);

  useEffect(() => {
    if (!currentWorkspace) return;
    const wsId = currentWorkspace.workspace_id;
    setLoading(true);
    setError(null);
    Promise.all([
      getCoverageInventory(wsId),
      getCheckInventory(wsId),
      getGovernanceMaturity(wsId),
      getCoverageTrend(wsId, period),
    ])
      .then(([inv, chk, mat, trd]) => {
        setInventory(inv);
        setChecks(chk);
        setMaturity(mat);
        setTrend(trd);
      })
      .catch((err) => {
        console.error('Failed to load coverage KQIs', err);
        setError(err?.response?.data?.detail || err?.message || 'Failed to load metrics');
      })
      .finally(() => setLoading(false));
  }, [currentWorkspace, period]);

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading coverage metrics…</div>;
  }

  if (error) {
    return <div className="flex items-center justify-center h-64 text-red-400">Error: {error}</div>;
  }

  if (!inventory || !checks || !maturity) {
    return <div className="flex items-center justify-center h-64 text-gray-500">No data available</div>;
  }

  const totalDs = inventory.total_datasets || 1;
  const totalFlows = inventory.total_flows || 1;
  const totalChecks = checks.total_checks || 1;
  const dimensionData = (checks.checks_by_dimension || []).map((d) => ({ name: d.dimension, value: d.count }));
  return (
    <div className="space-y-6">
      {/* Period selector */}
      <div className="flex justify-end">
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      {/* Coverage & Inventory */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <CircleStackIcon className="w-6 h-6" />
          Coverage & Inventory
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard
            title="Total Datasets"
            value={inventory.total_datasets}
            status="neutral"
            icon={<CircleStackIcon className="w-5 h-5" />}
          />
          <KPICard
            title="Datasets Analyzed"
            value={inventory.datasets_analyzed}
            subtitle={`${inventory.datasets_analyzed_pct}% of total`}
            status="success"
          />
          <KPICard
            title="Analyzed (Last 24h)"
            value={inventory.datasets_analyzed_24h}
            status="success"
          />
          <KPICard
            title="Without Flows"
            value={inventory.datasets_without_flows}
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
          <KPICard title="Total Flows" value={inventory.total_flows} status="neutral" />
          <KPICard
            title="Active Flows"
            value={inventory.active_flows}
            subtitle={`${inventory.active_flows_pct}% active`}
            status="success"
          />
          <KPICard
            title="Paused Flows"
            value={inventory.paused_flows}
            status="warning"
          />
          <KPICard
            title="Failed Flows"
            value={inventory.failed_flows}
            status="error"
          />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <KPICard
            title="Avg Datasets per Flow"
            value={inventory.avg_datasets_per_flow}
            status="neutral"
          />
          <KPICard
            title="Avg Checks per Flow"
            value={inventory.avg_checks_per_flow}
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
          <KPICard title="Total Checks" value={checks.total_checks} status="neutral" />
          <KPICard
            title="Standard Checks"
            value={checks.standard_checks}
            subtitle={`${checks.standard_checks_pct}% of total`}
            status="success"
          />
          <KPICard
            title="Custom Business Rules"
            value={checks.custom_checks}
            subtitle={`${totalChecks > 0 ? ((checks.custom_checks / totalChecks) * 100).toFixed(0) : 0}% of total`}
            status="neutral"
          />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <DistributionChart
            data={dimensionData}
            type="bar"
            dataKey="value"
            nameKey="name"
            title="Checks by Dimension"
            height={300}
          />
          <DistributionChart
            data={dimensionData}
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
            value={maturity.datasets_with_owner_pct}
            title="Datasets with Owner"
            label="Ownership Coverage"
          />
          <GaugeChart
            value={maturity.datasets_with_criticality_pct}
            title="With Criticality"
            label="Risk Classification"
          />
          <GaugeChart
            value={maturity.datasets_with_domain_pct}
            title="With Domain"
            label="Domain Assignment"
          />
          <GaugeChart
            value={maturity.datasets_with_thresholds_pct}
            title="With Thresholds"
            label="Threshold Definition"
          />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
          <KPICard
            title="Checks with SLA"
            value={`${maturity.checks_with_sla_pct}%`}
            status={maturity.checks_with_sla_pct >= 80 ? 'success' : 'warning'}
          />
        </div>
      </section>

      {/* High-Level Trends */}
      {trend && trend.has_data && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">High-Level Trends</h2>
          <TrendChart
            data={trend.data_points}
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
      )}

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
