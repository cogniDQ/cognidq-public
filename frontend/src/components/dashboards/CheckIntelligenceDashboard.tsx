import React, { useState, useEffect } from 'react';
import { DataTable } from '../widgets/DataTable';
import { KPICard } from '../widgets/KPICard';
import { DistributionChart } from '../widgets/DistributionChart';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import {
  getCheckIntelligence,
  getProblematicChecks,
  type CheckIntelligenceSummaryResponse,
  type ProblematicChecksResponse,
} from '../../services/kqiService';

export const CheckIntelligenceDashboard: React.FC = () => {
  const { currentWorkspace } = useWorkspace();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<CheckIntelligenceSummaryResponse | null>(null);
  const [problematic, setProblematic] = useState<ProblematicChecksResponse | null>(null);

  useEffect(() => {
    if (!currentWorkspace) return;
    const wsId = currentWorkspace.workspace_id;
    setLoading(true);
    Promise.all([
      getCheckIntelligence(wsId),
      getProblematicChecks(wsId),
    ])
      .then(([sum, prob]) => {
        setSummary(sum);
        setProblematic(prob);
      })
      .catch((err) => console.error('Failed to load check intelligence KQIs', err))
      .finally(() => setLoading(false));
  }, [currentWorkspace]);

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading check intelligence…</div>;
  }

  if (!summary || !summary.has_data) {
    return <div className="flex items-center justify-center h-64 text-gray-500">No check data available</div>;
  }

  const distributionData = summary.health_distribution.map((d) => ({
    name: d.status === 'always_pass' ? 'Always Pass' :
          d.status === 'always_fail' ? 'Always Fail' :
          d.status.charAt(0).toUpperCase() + d.status.slice(1),
    value: d.count,
  }));
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Check Intelligence: Are Our Checks Actually Good?</h1>

      {/* Key Metrics */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Check Health Metrics</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <KPICard
            title="Noisy Checks"
            value={summary.noisy_checks_count}
            subtitle="Flapping results"
            status="warning"
          />
          <KPICard
            title="Always Passing"
            value={summary.always_passing_count}
            subtitle="Potentially useless"
            status="warning"
          />
          <KPICard
            title="Always Failing"
            value={summary.always_failing_count}
            subtitle="Misconfigured"
            status="error"
          />
          <KPICard
            title="Duplicate Checks"
            value={summary.duplicate_checks_count}
            subtitle="Can be merged"
            status="warning"
          />
          <KPICard
            title="Effectiveness"
            value={`${summary.effectiveness_score}%`}
            subtitle="Overall check quality"
            status={summary.effectiveness_score >= 70 ? 'success' : 'warning'}
          />
        </div>
      </section>

      {/* Distribution */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Check Distribution by Health Status</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <DistributionChart
            data={distributionData}
            type="bar"
            dataKey="value"
            nameKey="name"
            title="Checks by Status"
          />
          <DistributionChart
            data={distributionData}
            type="pie"
            dataKey="value"
            nameKey="name"
            title="Proportion of Check Issues"
          />
        </div>
      </section>

      {/* Problematic Checks */}
      {problematic && problematic.checks.length > 0 && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">Problematic Checks Requiring Attention</h2>
          <DataTable
            data={problematic.checks.map((c) => ({
              check: c.check_name,
              flow: c.flow_name,
              issue: c.classification,
              flipRate: c.flip_rate != null ? `${(c.flip_rate * 100).toFixed(0)}%` : '—',
              passRate: c.pass_rate_30d != null ? `${c.pass_rate_30d.toFixed(1)}%` : '—',
              recommendation: c.recommendation,
            }))}
            columns={[
              { key: 'check', label: 'Check Name', width: '20%' },
              { key: 'flow', label: 'Flow', width: '15%' },
              {
                key: 'issue',
                label: 'Issue Type',
                render: (value) => (
                  <span
                    className={`px-2 py-1 rounded text-xs font-medium ${
                      value === 'always_fail'
                        ? 'bg-red-500/20 text-red-400'
                        : value === 'noisy'
                        ? 'bg-yellow-500/20 text-yellow-400'
                        : value === 'always_pass'
                        ? 'bg-blue-500/20 text-blue-400'
                        : 'bg-purple-500/20 text-purple-400'
                    }`}
                  >
                    {value}
                  </span>
                ),
              },
              { key: 'flipRate', label: 'Flip Rate' },
              { key: 'passRate', label: 'Pass Rate (30d)' },
              { key: 'recommendation', label: 'Recommendation', width: '30%' },
            ]}
            searchable
          />
        </section>
      )}
    </div>
  );
};
