/**
 * Metrics Overview Page - Display key DQ metrics and trends
 */
import React, { useState, useEffect } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import reportingService, {
  OverviewMetrics,
  CategoryBreakdown,
  SourceBreakdown,
} from '../services/reportingService';
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Database,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Activity,
  GitBranch,
  Loader2,
} from 'lucide-react';

const MetricsOverview: React.FC = () => {
  const { currentWorkspace } = useWorkspace();
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<OverviewMetrics | null>(null);
  const [categoryBreakdown, setCategoryBreakdown] = useState<CategoryBreakdown | null>(null);
  const [sourceBreakdown, setSourceBreakdown] = useState<SourceBreakdown | null>(null);
  const [period, setPeriod] = useState('30d');

  useEffect(() => {
    if (currentWorkspace) {
      loadMetrics();
    }
  }, [currentWorkspace, period]);

  const loadMetrics = async () => {
    if (!currentWorkspace) return;

    setLoading(true);
    try {
      const [overviewData, categoryData, sourceData] = await Promise.all([
        reportingService.getOverviewMetrics(currentWorkspace.workspace_id),
        reportingService.getCategoryBreakdown(currentWorkspace.workspace_id, period),
        reportingService.getSourceBreakdown(currentWorkspace.workspace_id, period),
      ]);

      setOverview(overviewData);
      setCategoryBreakdown(categoryData);
      setSourceBreakdown(sourceData);
    } catch (error) {
      console.error('Failed to load metrics:', error);
    } finally {
      setLoading(false);
    }
  };

  const getHealthStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'text-green-400';
      case 'warning':
        return 'text-yellow-400';
      case 'critical':
        return 'text-red-400';
      default:
        return 'text-gray-400';
    }
  };

  const getHealthStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle className="w-5 h-5 text-green-400" />;
      case 'warning':
        return <AlertTriangle className="w-5 h-5 text-yellow-400" />;
      case 'critical':
        return <XCircle className="w-5 h-5 text-red-400" />;
      default:
        return <Activity className="w-5 h-5 text-gray-400" />;
    }
  };

  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      completeness: 'bg-blue-500',
      validity: 'bg-purple-500',
      uniqueness: 'bg-green-500',
      consistency: 'bg-yellow-500',
      timeliness: 'bg-orange-500',
      accuracy: 'bg-pink-500',
    };
    return colors[category] || 'bg-gray-500';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#0F1419]">
        <Loader2 className="w-8 h-8 animate-spin text-blue-400" />
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#0F1419]">
        <div className="text-gray-400">Failed to load metrics</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0F1419] text-white p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold">Data Quality Metrics</h1>
            <p className="text-gray-400 mt-1">
              Overview of your data quality performance
            </p>
          </div>

          {/* Period Selector */}
          <div className="flex gap-2">
            {['7d', '30d', '90d', '1y'].map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-4 py-2 rounded-lg transition-colors ${
                  period === p
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {p === '7d' && '7 Days'}
                {p === '30d' && '30 Days'}
                {p === '90d' && '90 Days'}
                {p === '1y' && '1 Year'}
              </button>
            ))}
          </div>
        </div>

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {/* DQ Score */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <div className="text-gray-400 text-sm">DQ Score</div>
              <BarChart3 className="w-5 h-5 text-blue-400" />
            </div>
            <div className="text-3xl font-bold">{overview.dq_score}%</div>
            <div className="flex items-center mt-2 text-sm">
              {overview.dq_score >= 90 ? (
                <TrendingUp className="w-4 h-4 text-green-400 mr-1" />
              ) : (
                <TrendingDown className="w-4 h-4 text-red-400 mr-1" />
              )}
              <span
                className={
                  overview.dq_score >= 90 ? 'text-green-400' : 'text-red-400'
                }
              >
                {overview.dq_score >= 90 ? 'Excellent' : 'Needs Improvement'}
              </span>
            </div>
          </div>

          {/* Pass Rate */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <div className="text-gray-400 text-sm">Avg Pass Rate</div>
              <CheckCircle className="w-5 h-5 text-green-400" />
            </div>
            <div className="text-3xl font-bold">
              {overview.average_pass_rate}%
            </div>
            <div className="text-sm text-gray-400 mt-2">
              {overview.total_executions} executions
            </div>
          </div>

          {/* Critical Violations */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <div className="text-gray-400 text-sm">Critical Violations</div>
              <AlertTriangle className="w-5 h-5 text-red-400" />
            </div>
            <div className="text-3xl font-bold">
              {overview.critical_violations}
            </div>
            <div className="text-sm text-gray-400 mt-2">Require attention</div>
          </div>

          {/* Total Rules */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <div className="text-gray-400 text-sm">Total Rules</div>
              <GitBranch className="w-5 h-5 text-purple-400" />
            </div>
            <div className="text-3xl font-bold">{overview.total_rules}</div>
            <div className="text-sm text-gray-400 mt-2">Active rules</div>
          </div>
        </div>

        {/* Category Breakdown */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 mb-8">
          <h2 className="text-xl font-bold mb-4">Category Breakdown</h2>
          <div className="space-y-4">
            {categoryBreakdown?.categories.map((cat) => (
              <div key={cat.category}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-3 h-3 rounded-full ${getCategoryColor(
                        cat.category
                      )}`}
                    />
                    <span className="capitalize">{cat.category}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-sm text-gray-400">
                      {cat.total_executions} executions
                    </span>
                    <span className="font-semibold">{cat.pass_rate}%</span>
                  </div>
                </div>
                <div className="w-full bg-gray-700 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${getCategoryColor(
                      cat.category
                    )}`}
                    style={{ width: `${cat.pass_rate}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Source Health */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h2 className="text-xl font-bold mb-4">Data Source Health</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {sourceBreakdown?.sources.map((source) => (
              <div
                key={source.source_id}
                className="bg-gray-900 rounded-lg p-4 border border-gray-700"
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Database className="w-5 h-5 text-gray-400" />
                    <span className="font-semibold">{source.source_name}</span>
                  </div>
                  {getHealthStatusIcon(source.health_status)}
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Pass Rate:</span>
                    <span
                      className={getHealthStatusColor(source.health_status)}
                    >
                      {source.pass_rate}%
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Rules:</span>
                    <span>{source.total_rules}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Executions:</span>
                    <span>{source.total_executions}</span>
                  </div>
                  {source.last_execution && (
                    <div className="text-xs text-gray-500 mt-2">
                      Last run:{' '}
                      {new Date(source.last_execution).toLocaleDateString()}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default MetricsOverview;
