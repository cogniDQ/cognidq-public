import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { KPICard } from '../widgets/KPICard';
import { TrendChart } from '../widgets/TrendChart';
import { DataTable } from '../widgets/DataTable';
import { PeriodSelector } from '../widgets/PeriodSelector';
import { ChartBarIcon, CurrencyDollarIcon, Cog6ToothIcon } from '@heroicons/react/24/outline';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import { useAuth } from '../../contexts/AuthContext';
import { useWorkspacePermissions } from '../../hooks/useWorkspacePermissions';
import { getActorId } from '../../utils/jwt';
import {
  getBusinessValueSummary,
  getTopFlows,
  type BusinessValueSummaryResponse,
  type TopFlowsResponse,
} from '../../services/kqiService';

export const AdoptionValueDashboard: React.FC = () => {
  const { currentWorkspace } = useWorkspace();
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const actorId = getActorId(token) ?? undefined;
  const { can } = useWorkspacePermissions(currentWorkspace?.workspace_id, actorId);
  const canConfigureCosts = can('settings:read');

  const [period, setPeriod] = useState('30d');
  const [loading, setLoading] = useState(true);
  const [valueSummary, setValueSummary] = useState<BusinessValueSummaryResponse | null>(null);
  const [topFlows, setTopFlows] = useState<TopFlowsResponse | null>(null);

  useEffect(() => {
    if (!currentWorkspace) return;
    const wsId = currentWorkspace.workspace_id;
    setLoading(true);
    Promise.all([
      getBusinessValueSummary(wsId, period),
      getTopFlows(wsId, period),
    ])
      .then(([val, flows]) => {
        setValueSummary(val);
        setTopFlows(flows);
      })
      .catch((err) => console.error('Failed to load business value KQIs', err))
      .finally(() => setLoading(false));
  }, [currentWorkspace, period]);

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading business value metrics…</div>;
  }

  if (!valueSummary || !valueSummary.has_data) {
    return <div className="flex items-center justify-center h-64 text-gray-500">No business value data available</div>;
  }

  const costDisplay = valueSummary.estimated_cost_saved_usd >= 1000
    ? `$${(valueSummary.estimated_cost_saved_usd / 1000).toFixed(0)}K`
    : `$${valueSummary.estimated_cost_saved_usd.toFixed(0)}`;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <ChartBarIcon className="w-8 h-8 text-green-500" />
            Adoption & Value: Platform ROI
          </h1>
          <p className="text-gray-400">Business value delivered by data quality flows</p>
        </div>
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      {/* ROI Metrics */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-white">Business Impact Metrics</h2>
          {canConfigureCosts && currentWorkspace && (
            <Link
              to={`/workspaces/${currentWorkspace.workspace_id}/settings`}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-dark-600 hover:bg-dark-700 text-gray-400 hover:text-white text-sm transition-colors"
            >
              <Cog6ToothIcon className="w-4 h-4" />
              Configure Cost Model
            </Link>
          )}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <KPICard
            title="Issues Caught"
            value={valueSummary.issues_caught}
            status="success"
            icon={<ChartBarIcon className="w-5 h-5 text-green-500" />}
          />
          <KPICard
            title="Incidents Avoided"
            value={valueSummary.estimated_incidents_avoided}
            status="success"
          />
          <KPICard
            title="Estimated Cost Saved"
            value={costDisplay}
            subtitle={`Last ${period}`}
            status="success"
            icon={<CurrencyDollarIcon className="w-5 h-5 text-green-500" />}
          />
        </div>
      </section>

      {/* Issues Trend */}
      {valueSummary.issues_caught_trend.length > 0 && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">Issues Caught Over Time</h2>
          <TrendChart
            data={valueSummary.issues_caught_trend}
            lines={[
              { dataKey: 'count', name: 'Issues Caught', color: '#10B981' },
            ]}
            xAxisKey="date"
            title="Daily Issue Detection"
            height={300}
          />
        </section>
      )}

      {/* Top Flows */}
      {topFlows && topFlows.flows.length > 0 && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">Most Valuable Flows</h2>
          <DataTable
            data={topFlows.flows.map((f) => ({
              flow: f.flow_name,
              issuesCaught: f.issues_caught,
              critical: f.critical_issues,
              value: `$${f.estimated_value_usd >= 1000 ? (f.estimated_value_usd / 1000).toFixed(0) + 'K' : f.estimated_value_usd.toFixed(0)}`,
            }))}
            columns={[
              { key: 'flow', label: 'Flow Name', width: '40%' },
              { key: 'issuesCaught', label: 'Issues Caught' },
              { key: 'critical', label: 'Critical' },
              {
                key: 'value',
                label: 'Est. Value',
                render: (value) => <span className="text-green-400 font-semibold">{value}</span>,
              },
            ]}
          />
        </section>
      )}
    </div>
  );
};
