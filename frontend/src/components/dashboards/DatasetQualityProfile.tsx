import React, { useState, useEffect } from 'react';
import { KPICard } from '../widgets/KPICard';
import { DataTable } from '../widgets/DataTable';
import { GaugeChart } from '../widgets/GaugeChart';
import { PeriodSelector } from '../widgets/PeriodSelector';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import {
  getDatasetProfile,
  type DatasetProfileResponse,
} from '../../services/kqiService';
import { listDataSources } from '../../services/datasource';
import { listDatasets } from '../../services/datasetService';
import type { DataSource } from '../../types/dataSource';
import type { DatasetListItem } from '../../types/dataset';

export const DatasetQualityProfile: React.FC = () => {
  const { currentWorkspace } = useWorkspace();
  const [period, setPeriod] = useState('30d');
  const [selectedSourceId, setSelectedSourceId] = useState('');
  const [datasetId, setDatasetId] = useState('');
  const [loading, setLoading] = useState(false);
  const [profile, setProfile] = useState<DatasetProfileResponse | null>(null);
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [datasets, setDatasets] = useState<DatasetListItem[]>([]);
  const [dsLoading, setDsLoading] = useState(false);
  const [datasetsLoading, setDatasetsLoading] = useState(false);

  // Load available data sources
  useEffect(() => {
    if (!currentWorkspace) return;
    setDsLoading(true);
    listDataSources(currentWorkspace.workspace_id, { status: 'active' })
      .then((resp) =>
        setDataSources(
          (resp.items || []).filter((ds) => ds.last_test_status === 'reachable'),
        ),
      )
      .catch((err) => console.error('Failed to load data sources', err))
      .finally(() => setDsLoading(false));
  }, [currentWorkspace]);

  // Load datasets when data source selection changes
  useEffect(() => {
    if (!currentWorkspace || !selectedSourceId) {
      setDatasets([]);
      setDatasetId('');
      setProfile(null);
      return;
    }
    setDatasetsLoading(true);
    setDatasetId('');
    setProfile(null);
    listDatasets(currentWorkspace.workspace_id, { data_source_id: selectedSourceId })
      .then((resp) => setDatasets(resp.items || []))
      .catch((err) => console.error('Failed to load datasets', err))
      .finally(() => setDatasetsLoading(false));
  }, [currentWorkspace, selectedSourceId]);

  // Load dataset profile when dataset selection changes
  useEffect(() => {
    if (!currentWorkspace || !datasetId) return;
    setLoading(true);
    getDatasetProfile(currentWorkspace.workspace_id, datasetId, period)
      .then(setProfile)
      .catch((err) => console.error('Failed to load dataset profile', err))
      .finally(() => setLoading(false));
  }, [currentWorkspace, datasetId, period]);

  const dimensionKeys = profile ? Object.keys(profile.dimension_scores) : [];
  const columnsWithoutChecks = profile
    ? profile.column_coverage.filter((c) => c.checks_count === 0)
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Dataset Quality Profile</h1>
        <div className="flex items-center gap-4">
          <select
            value={selectedSourceId}
            onChange={(e) => setSelectedSourceId(e.target.value)}
            className="px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500 min-w-[200px]"
          >
            <option value="">{dsLoading ? 'Loading…' : 'Select data source…'}</option>
            {dataSources.map((ds) => (
              <option key={ds.data_source_id} value={ds.data_source_id}>
                {ds.source_name}
              </option>
            ))}
          </select>
          <select
            value={datasetId}
            onChange={(e) => setDatasetId(e.target.value)}
            disabled={!selectedSourceId || datasetsLoading}
            className="px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500 min-w-[200px] disabled:opacity-50"
          >
            <option value="">
              {!selectedSourceId
                ? 'Select data source first…'
                : datasetsLoading
                ? 'Loading datasets…'
                : datasets.length === 0
                ? 'No datasets available'
                : 'Select dataset…'}
            </option>
            {datasets.map((ds) => (
              <option key={ds.dataset_id} value={ds.dataset_id}>
                {ds.dataset_name}
              </option>
            ))}
          </select>
          <PeriodSelector value={period} onChange={setPeriod} />
        </div>
      </div>

      {!datasetId && !loading && (
        <div className="flex items-center justify-center h-64 text-gray-500">
          {!selectedSourceId
            ? 'Select a data source and dataset to view quality profile'
            : datasetsLoading
            ? 'Loading datasets…'
            : 'Select a dataset to view its quality profile'}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center h-64 text-gray-400">Loading dataset profile…</div>
      )}

      {profile && !loading && (
        <>
          {/* Quality Summary */}
          <section>
            <h2 className="text-xl font-bold text-white mb-4">Quality Summary (All Flows Aggregated)</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <GaugeChart value={profile.overall_score} title="Overall Quality Score" label="Data Quality" />
              {dimensionKeys.slice(0, 3).map((dim) => (
                <GaugeChart
                  key={dim}
                  value={profile.dimension_scores[dim]}
                  title={dim.charAt(0).toUpperCase() + dim.slice(1)}
                />
              ))}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <KPICard
                title="Worst Check"
                value={profile.worst_check ? `${profile.worst_check.name} (${profile.worst_check.pass_rate}%)` : 'N/A'}
                status="warning"
                subtitle="Needs attention"
              />
              <KPICard
                title="Most Unstable Column"
                value={profile.most_unstable_column ? profile.most_unstable_column.name : 'N/A'}
                status="warning"
                subtitle={profile.most_unstable_column ? `Variance: ${profile.most_unstable_column.variance}` : 'High variance'}
              />
              <KPICard
                title="Days Since Healthy"
                value={profile.days_since_healthy ?? 'N/A'}
                status="error"
                subtitle="Last 100% pass rate"
              />
            </div>
          </section>

          {/* Check Coverage */}
          {profile.column_coverage.length > 0 && (
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
                data={profile.column_coverage.map((c) => ({
                  column: c.column,
                  checks: c.checks_count,
                  coverage: c.coverage_pct,
                }))}
                columns={[
                  { key: 'column', label: 'Column Name', width: '30%' },
                  { key: 'checks', label: 'Total Checks' },
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
          )}
        </>
      )}
    </div>
  );
};
