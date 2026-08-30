import React, { useState, useEffect, useCallback } from 'react';
import { DataTable } from '../widgets/DataTable';
import { KPICard } from '../widgets/KPICard';
import { TrendChart } from '../widgets/TrendChart';
import { PeriodSelector } from '../widgets/PeriodSelector';
import { ExclamationTriangleIcon, BellAlertIcon } from '@heroicons/react/24/outline';
import { Activity, PlayCircle } from 'lucide-react';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import { useTenantScopedPath } from '../../hooks/useTenantScopedPath';
import EmptyState from '../common/EmptyState';
import {
  getAnomalySummary,
  getDetectedAnomalies,
  getAnomalyVolumeTrend,
  getAnomalySuggestions,
  AnomalySummaryResponse,
  DetectedAnomaliesResponse,
  VolumeTrendResponse,
  AnomalySuggestionsResponse,
} from '../../services/kqiService';

export const AnomalyDetectionDashboard: React.FC = () => {
  const { currentWorkspace } = useWorkspace();
  const { wsPath } = useTenantScopedPath();
  const [period, setPeriod] = useState('30d');
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<AnomalySummaryResponse | null>(null);
  const [anomalies, setAnomalies] = useState<DetectedAnomaliesResponse | null>(null);
  const [volumeTrend, setVolumeTrend] = useState<VolumeTrendResponse | null>(null);
  const [suggestions, setSuggestions] = useState<AnomalySuggestionsResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadData = useCallback(() => {
    if (!currentWorkspace) return;
    const wsId = currentWorkspace.workspace_id;
    setLoading(true);
    setLoadError(null);
    Promise.all([
      getAnomalySummary(wsId, period),
      getDetectedAnomalies(wsId, period),
      getAnomalyVolumeTrend(wsId, period),
      getAnomalySuggestions(wsId, period),
    ])
      .then(([s, a, v, sg]) => {
        setSummary(s);
        setAnomalies(a);
        setVolumeTrend(v);
        setSuggestions(sg);
      })
      .catch((err) => {
        console.error('Failed to load anomaly detection data', err);
        setLoadError(err?.message ?? 'Failed to load anomaly detection data.');
      })
      .finally(() => setLoading(false));
  }, [currentWorkspace, period]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading…</div>;
  }

  if (loadError) {
    return (
      <EmptyState
        variant="error"
        title="Couldn't load anomaly detection"
        description={loadError}
        onRetry={loadData}
        testId="anomaly-error"
      />
    );
  }

  if (!summary || !summary.has_data) {
    return (
      <EmptyState
        icon={Activity}
        title="No execution data for anomaly detection"
        description="Anomaly detection learns from past flow runs. Run a few quality checks to build a baseline — patterns and outliers will appear here once enough history exists."
        primaryAction={currentWorkspace ? {
          label: 'Open Flows',
          to: wsPath(currentWorkspace.workspace_id, '/flows'),
          icon: PlayCircle,
        } : undefined}
        testId="anomaly-empty"
      />
    );
  }

  const anomalyList = anomalies?.anomalies || [];
  const trends = volumeTrend?.trends || [];
  const suggestionList = suggestions?.suggestions || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <ExclamationTriangleIcon className="w-8 h-8 text-yellow-500" />
            Anomaly & Pattern Detection
          </h1>
          <p className="text-gray-400">Detect issues BEFORE users complain</p>
        </div>
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      {/* Key Metrics */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">Detection Summary</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <KPICard
            title="Total Anomalies"
            value={summary.total_anomalies}
            status={summary.total_anomalies > 0 ? 'warning' : 'success'}
          />
          <KPICard
            title="Critical"
            value={summary.critical_anomalies}
            status={summary.critical_anomalies > 0 ? 'error' : 'neutral'}
            icon={<ExclamationTriangleIcon className="w-5 h-5 text-red-500" />}
          />
          <KPICard
            title="High"
            value={summary.high_anomalies}
            status={summary.high_anomalies > 0 ? 'warning' : 'neutral'}
          />
          <KPICard
            title="Medium / Low"
            value={summary.medium_anomalies + summary.low_anomalies}
            status="neutral"
          />
        </div>
      </section>

      {/* Detected Anomalies */}
      {anomalyList.length > 0 && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">Detected Anomalies</h2>
          <DataTable
            data={anomalyList}
            columns={[
              { key: 'dataset', label: 'Dataset' },
              { key: 'column', label: 'Column' },
              {
                key: 'anomaly',
                label: 'Anomaly',
                render: (value: string) => (
                  <span className="px-2 py-1 bg-purple-500/20 text-purple-400 rounded text-xs font-medium">
                    {value}
                  </span>
                ),
              },
              {
                key: 'severity',
                label: 'Severity',
                render: (value: string) => (
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
              {
                key: 'detected',
                label: 'Detected',
                render: (v: string | null) =>
                  v ? new Date(v).toLocaleString() : '—',
              },
              { key: 'current_value', label: 'Current' },
              { key: 'expected_value', label: 'Expected' },
              { key: 'deviation', label: 'Deviation' },
              {
                key: 'status',
                label: 'Status',
                render: (value: string) => (
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
      )}

      {anomalyList.length === 0 && (
        <section className="bg-green-900/20 border border-green-700 rounded-lg p-6 text-center">
          <p className="text-green-400 font-medium">No anomalies detected in the selected period.</p>
          <p className="text-gray-400 text-sm mt-1">All execution metrics are within expected ranges.</p>
        </section>
      )}

      {/* Volume Trend */}
      {trends.length > 0 && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">Execution Volume Trends</h2>
          <TrendChart
            data={trends}
            lines={[
              { dataKey: 'total_executions', name: 'Total', color: '#3B82F6' },
              { dataKey: 'successful_executions', name: 'Successful', color: '#10B981' },
              { dataKey: 'failed_executions', name: 'Failed', color: '#EF4444' },
            ]}
            xAxisKey="date"
            title="Daily Execution Volume"
            height={300}
          />
        </section>
      )}

      {/* Suggested Actions */}
      {suggestionList.length > 0 && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
            <BellAlertIcon className="w-6 h-6 text-yellow-500" />
            Suggested Actions
          </h2>
          <DataTable
            data={suggestionList}
            columns={[
              { key: 'signal', label: 'Signal/Pattern', width: '25%' },
              {
                key: 'priority',
                label: 'Priority',
                render: (value: string) => (
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
              { key: 'action', label: 'Recommended Action', width: '35%' },
              { key: 'estimated_impact', label: 'Estimated Impact', width: '30%' },
            ]}
            pagination={false}
          />
        </section>
      )}
    </div>
  );
};
