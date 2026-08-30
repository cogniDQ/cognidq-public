import React, { useState, useEffect } from 'react';
import { DataTable } from '../widgets/DataTable';
import { KPICard } from '../widgets/KPICard';
import { Sparkline } from '../widgets/Sparkline';
import {
  PlayCircleIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  ChevronLeftIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import flowService, { FlowExecution, FlowNodeResult, ExecutionStatus } from '../../services/flow';

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    completed: 'bg-green-500/20 text-green-400',
    running: 'bg-blue-500/20 text-blue-400',
    pending: 'bg-gray-500/20 text-gray-400',
    failed: 'bg-red-500/20 text-red-400',
    cancelled: 'bg-yellow-500/20 text-yellow-400',
  };
  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${colors[status] || 'bg-gray-500/20 text-gray-400'}`}>
      {status}
    </span>
  );
}

export const FlowExecutionReport: React.FC = () => {
  const { currentWorkspace } = useWorkspace();
  const [loading, setLoading] = useState(true);
  const [executions, setExecutions] = useState<FlowExecution[]>([]);
  const [selectedExecution, setSelectedExecution] = useState<FlowExecution | null>(null);
  const [nodeResults, setNodeResults] = useState<FlowNodeResult[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    if (!currentWorkspace) return;
    setLoading(true);
    flowService
      .listAllExecutions(currentWorkspace.workspace_id, { page_size: 25 })
      .then(setExecutions)
      .catch((err) => console.error('Failed to load executions', err))
      .finally(() => setLoading(false));
  }, [currentWorkspace]);

  const selectExecution = async (execution: FlowExecution) => {
    if (!currentWorkspace) return;
    const wsId = currentWorkspace.workspace_id;
    setDetailLoading(true);
    try {
      const [detail, nodes] = await Promise.all([
        flowService.getExecution(wsId, execution.id),
        flowService.getNodeResults(wsId, execution.id),
      ]);
      setSelectedExecution(detail);
      setNodeResults(nodes.sort((a, b) => a.execution_order - b.execution_order));
    } catch (err) {
      console.error('Failed to load execution detail', err);
    } finally {
      setDetailLoading(false);
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading…</div>;
  }

  if (executions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-500">
        <PlayCircleIcon className="w-12 h-12 mb-2" />
        <p>No flow executions found. Run a flow to see results here.</p>
      </div>
    );
  }

  if (detailLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        Loading execution detail…
      </div>
    );
  }

  /* ---- Execution List View ---- */
  if (!selectedExecution) {
    return (
      <div className="space-y-6">
        <h2 className="text-xl font-bold text-white">Recent Flow Executions</h2>
        <DataTable
          data={executions}
          columns={[
            {
              key: 'id',
              label: 'Execution ID',
              render: (v: string) => (
                <span className="font-mono text-xs">{v?.substring(0, 8)}…</span>
              ),
            },
            {
              key: 'status',
              label: 'Status',
              render: (v: string) => <StatusBadge status={v} />,
            },
            { key: 'trigger', label: 'Trigger' },
            {
              key: 'started_at',
              label: 'Started',
              render: (v: string) => (v ? new Date(v).toLocaleString() : '—'),
            },
            {
              key: 'duration_seconds',
              label: 'Duration',
              render: (v: number, row: FlowExecution) => {
                const dur = v ?? row.execution_time_seconds;
                return dur != null ? formatDuration(dur) : '—';
              },
            },
            {
              key: 'nodes_executed',
              label: 'Nodes',
              render: (_: any, row: FlowExecution) => (
                <span>
                  <span className="text-green-400">{row.nodes_passed}</span>
                  {row.nodes_failed > 0 && (
                    <span className="text-red-400">/{row.nodes_failed}F</span>
                  )}
                  <span className="text-gray-400">/{row.nodes_executed}</span>
                </span>
              ),
            },
            {
              key: 'actions',
              label: '',
              render: (_: any, row: FlowExecution) => (
                <button
                  onClick={() => selectExecution(row)}
                  className="text-blue-400 hover:text-blue-300 text-sm font-medium"
                >
                  View Detail →
                </button>
              ),
            },
          ]}
          searchable
        />
      </div>
    );
  }

  /* ---- Detail View ---- */
  const exec = selectedExecution;
  const summary = exec.result_summary || {};
  const datasets: any[] = summary.datasets || [];
  const checksSummary = summary.checks_summary || {};
  const checksResults: any[] = checksSummary.results || [];
  const historicalContext: any[] = summary.historical_context || [];
  const failedChecks = checksResults.filter((c: any) => c.result === 'failed');

  // Use check-level metrics when available, fall back to node counts
  const totalChecks = checksSummary.total ?? exec.nodes_executed;
  const passedChecks = checksSummary.passed ?? exec.nodes_passed;
  const warningChecks = checksSummary.warning ?? 0;
  const failedCount = checksSummary.failed ?? exec.nodes_failed;
  const skippedChecks = checksSummary.skipped ?? exec.nodes_skipped;
  const passRate =
    totalChecks > 0
      ? Math.round(((passedChecks) / totalChecks) * 100)
      : 0;

  const statusLabel =
    exec.status === ExecutionStatus.COMPLETED && failedCount === 0
      ? 'Success'
      : exec.status === ExecutionStatus.COMPLETED && failedCount > 0
        ? 'Partial Success'
        : exec.status === ExecutionStatus.FAILED
          ? 'Failed'
          : exec.status;

  // Build a lookup for historical trend data
  const trendLookup: Record<string, any> = {};
  historicalContext.forEach((h: any) => {
    trendLookup[h.check_name] = h;
  });

  return (
    <div className="space-y-6">
      {/* Back button */}
      <button
        onClick={() => {
          setSelectedExecution(null);
          setNodeResults([]);
        }}
        className="flex items-center gap-1 text-blue-400 hover:text-blue-300 text-sm"
      >
        <ChevronLeftIcon className="w-4 h-4" />
        Back to Executions
      </button>

      {/* Flow Run Header */}
      <section className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 border border-blue-700 rounded-lg p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-white mb-2">
              {exec.flow_name || summary.flow_name || `Flow ${exec.flow_id.substring(0, 8)}…`}
            </h1>
            <div className="flex items-center gap-4 text-sm text-gray-300">
              <span className="flex items-center gap-1">
                <PlayCircleIcon className="w-4 h-4" />
                Run ID: {exec.id.substring(0, 12)}…
              </span>
              <span>Trigger: {exec.trigger}</span>
              {(exec.executed_by_name || exec.triggered_by) && (
                <span>Actor: {exec.executed_by_name || exec.triggered_by}</span>
              )}
            </div>
          </div>
          <div
            className={`px-4 py-2 rounded-full text-sm font-medium ${
              statusLabel === 'Success'
                ? 'bg-green-500/20 text-green-400'
                : statusLabel === 'Partial Success'
                  ? 'bg-yellow-500/20 text-yellow-400'
                  : 'bg-red-500/20 text-red-400'
            }`}
          >
            {statusLabel}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-gray-400">Start Time</p>
            <p className="text-lg font-semibold text-white">
              {exec.started_at ? new Date(exec.started_at).toLocaleString() : '—'}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-400">Duration</p>
            <p className="text-lg font-semibold text-white">
              {exec.duration_seconds != null
                ? formatDuration(exec.duration_seconds)
                : exec.execution_time_seconds != null
                  ? formatDuration(exec.execution_time_seconds)
                  : '—'}
            </p>
          </div>
        </div>
      </section>

      {/* Datasets Involved */}
      {datasets.length > 0 && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">📦 Datasets Involved</h2>
          <DataTable
            data={datasets}
            columns={[
              { key: 'name', label: 'Dataset' },
              { key: 'source', label: 'Source' },
              {
                key: 'rows_analyzed',
                label: 'Rows Analyzed',
                render: (v: number) => v != null ? v.toLocaleString() : '—',
              },
              { key: 'schema_version', label: 'Schema Version', render: (v: string) => v || '—' },
              {
                key: 'status',
                label: 'Status',
                render: (v: string) => (
                  <span
                    className={`px-2 py-1 rounded text-xs font-medium ${
                      v === 'success'
                        ? 'bg-green-500/20 text-green-400'
                        : v === 'warning'
                          ? 'bg-yellow-500/20 text-yellow-400'
                          : 'bg-red-500/20 text-red-400'
                    }`}
                  >
                    {v}
                  </span>
                ),
              },
              {
                key: 'volume_change',
                label: 'Volume Change',
                render: (v: any) => {
                  if (!v) return <span className="text-gray-500">—</span>;
                  const pct = typeof v === 'object' ? v.change_percent : v;
                  const formatted = typeof pct === 'number'
                    ? `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`
                    : String(pct);
                  return (
                    <span className={formatted.startsWith('+') || formatted.startsWith('0') ? 'text-green-400' : 'text-red-400'}>
                      {formatted}
                    </span>
                  );
                },
              },
              {
                key: 'schema_drift',
                label: 'Schema Drift',
                render: (v: boolean) =>
                  v ? (
                    <span className="text-yellow-400 flex items-center gap-1">
                      <ExclamationTriangleIcon className="w-4 h-4" /> Yes
                    </span>
                  ) : (
                    <span className="text-gray-400">No</span>
                  ),
              },
            ]}
          />
        </section>
      )}

      {/* Run-Level Metrics */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">📊 Run-Level Metrics</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <KPICard title="Total Checks" value={totalChecks} status="neutral" />
          <KPICard
            title="Passed"
            value={passedChecks}
            status="success"
            icon={<CheckCircleIcon className="w-5 h-5 text-green-500" />}
          />
          <KPICard
            title="Warnings"
            value={warningChecks}
            status="warning"
            icon={<ExclamationTriangleIcon className="w-5 h-5 text-yellow-500" />}
          />
          <KPICard
            title="Failed"
            value={failedCount}
            status={failedCount > 0 ? 'error' : 'neutral'}
            icon={<XCircleIcon className="w-5 h-5 text-red-500" />}
          />
          <KPICard title="Skipped" value={skippedChecks} status="neutral" />
          <KPICard
            title="Pass Rate"
            value={`${passRate}%`}
            status={passRate >= 80 ? 'success' : passRate >= 60 ? 'warning' : 'error'}
          />
        </div>
      </section>

      {/* Checks Applied */}
      {checksResults.length > 0 && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">🧪 Checks Applied</h2>
          <DataTable
            data={checksResults}
            columns={[
              { key: 'check_name', label: 'Check Name', width: '18%' },
              { key: 'check_type', label: 'Type' },
              { key: 'dataset', label: 'Dataset' },
              { key: 'column', label: 'Column', render: (v: string) => v || '—' },
              { key: 'threshold', label: 'Threshold', render: (v: string) => v || '—' },
              {
                key: 'result',
                label: 'Result',
                render: (v: string) => (
                  <span
                    className={`px-2 py-1 rounded text-xs font-medium ${
                      v === 'passed'
                        ? 'bg-green-500/20 text-green-400'
                        : v === 'warning'
                          ? 'bg-yellow-500/20 text-yellow-400'
                          : 'bg-red-500/20 text-red-400'
                    }`}
                  >
                    {v}
                  </span>
                ),
              },
              {
                key: 'actual_value',
                label: 'Actual Value',
                render: (v: any) =>
                  v != null
                    ? typeof v === 'number'
                      ? `${v.toFixed(1)}%`
                      : String(v)
                    : '—',
              },
              {
                key: 'check_name',
                label: 'Trend',
                render: (_: any, row: any) => {
                  const hist = trendLookup[row.check_name];
                  if (hist && hist.previous_result != null && hist.current_result != null) {
                    const trendData = [hist.previous_result, hist.current_result];
                    return (
                      <div className="flex items-center gap-2">
                        <Sparkline
                          data={trendData}
                          color={row.result === 'failed' ? '#EF4444' : row.result === 'warning' ? '#F59E0B' : '#10B981'}
                        />
                        <span className="text-xs text-gray-400">{hist.comparison}</span>
                      </div>
                    );
                  }
                  return <span className="text-gray-500 text-xs">—</span>;
                },
              },
            ]}
            searchable
          />
        </section>
      )}

      {/* Fallback: Node Results (if no checks available) */}
      {checksResults.length === 0 && nodeResults.length > 0 && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">🧪 Node Results</h2>
          <DataTable
            data={nodeResults}
            columns={[
              { key: 'execution_order', label: '#', width: '5%' },
              {
                key: 'node_id',
                label: 'Node',
                render: (v: string, row: FlowNodeResult) => {
                  const label = row.result_data?.node_label;
                  return <span className="font-medium">{label || v}</span>;
                },
              },
              {
                key: 'status',
                label: 'Status',
                render: (v: string) => <StatusBadge status={v} />,
              },
              {
                key: 'execution_time_seconds',
                label: 'Duration',
                render: (v: number) => (v != null ? formatDuration(v) : '—'),
              },
              {
                key: 'result_data',
                label: 'Summary',
                render: (v: Record<string, any> | undefined) => {
                  if (!v) return <span className="text-gray-500">—</span>;
                  const parts: string[] = [];
                  if (v.rows_analyzed != null || v.rows_scanned != null)
                    parts.push(`${Number(v.rows_analyzed ?? v.rows_scanned).toLocaleString()} rows`);
                  if (v.pass_rate != null) parts.push(`${v.pass_rate}% pass`);
                  if (v.check_type) parts.push(v.check_type);
                  return parts.length > 0 ? (
                    <span className="text-sm text-gray-300">{parts.join(' · ')}</span>
                  ) : (
                    <span className="text-gray-500 text-xs">{Object.keys(v).length} fields</span>
                  );
                },
              },
            ]}
            searchable
          />
        </section>
      )}

      {/* Failure Deep Dive */}
      {failedChecks.length > 0 && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">🧬 Failure Deep Dive</h2>
          {failedChecks.map((check: any, idx: number) => {
            const hist = trendLookup[check.check_name];
            // Find the corresponding node result for additional detail
            const failedNode = nodeResults.find(
              (n) => n.result_data?.node_label === check.check_name || n.node_id === check.check_name
            );
            const violations = failedNode?.result_data?.violations || failedNode?.result_data?.canonical_violations || [];

            return (
              <div
                key={idx}
                className="bg-red-900/20 border border-red-700 rounded-lg p-6 mb-4"
              >
                <div className="mb-4">
                  <h3 className="text-lg font-semibold text-white mb-2">
                    <ExclamationTriangleIcon className="w-5 h-5 inline mr-2 text-red-400" />
                    {check.check_name}
                  </h3>
                  <p className="text-sm text-gray-300 mb-4">
                    <strong>Rule:</strong> {check.check_type} check on{' '}
                    <span className="text-blue-300">{check.dataset}</span>
                    {check.column && check.column !== '*' && (
                      <span>
                        {' '}→ column <span className="text-blue-300">{check.column}</span>
                      </span>
                    )}
                    {check.threshold && (
                      <span> (threshold: {check.threshold})</span>
                    )}
                  </p>
                  <div className="bg-gray-800 border border-gray-700 rounded p-4 mb-4">
                    <p className="text-sm text-gray-300">
                      <strong>Why it failed:</strong>{' '}
                      {check.actual_value != null
                        ? `Actual value ${typeof check.actual_value === 'number' ? check.actual_value.toFixed(1) + '%' : check.actual_value} did not meet the threshold of ${check.threshold || check.expected_value}.`
                        : failedNode?.error_message || 'Check did not pass the configured threshold.'}
                      {hist && (
                        <span className="ml-1">
                          Previous result: {hist.comparison} ({hist.trend}).
                        </span>
                      )}
                    </p>
                  </div>
                  {failedNode?.error_message && (
                    <div className="bg-orange-900/20 border border-orange-700 rounded p-4 mb-4">
                      <p className="text-sm text-orange-300">
                        <strong>Error:</strong> {failedNode.error_message}
                      </p>
                    </div>
                  )}
                </div>
                {violations.length > 0 && (
                  <div>
                    <h4 className="text-md font-semibold text-white mb-2">Sample Faulty Rows</h4>
                    <DataTable
                      data={violations.slice(0, 5)}
                      columns={Object.keys(violations[0] || {}).map((k) => ({
                        key: k,
                        label: k,
                        render: (v: any) => (
                          <span className={v === null ? 'text-red-400' : ''}>
                            {v === null ? 'NULL' : String(v)}
                          </span>
                        ),
                      }))}
                      pagination={false}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </section>
      )}

      {/* Legacy: Failure Details for nodes without check enrichment */}
      {failedChecks.length === 0 && nodeResults.filter((n) => n.status === ExecutionStatus.FAILED).length > 0 && (
        <section>
          <h2 className="text-xl font-bold text-white mb-4">🧬 Failure Details</h2>
          {nodeResults
            .filter((n) => n.status === ExecutionStatus.FAILED)
            .map((node) => (
              <div
                key={node.id}
                className="bg-red-900/20 border border-red-700 rounded-lg p-6 mb-4"
              >
                <h3 className="text-lg font-semibold text-white mb-2">
                  <ExclamationTriangleIcon className="w-5 h-5 inline mr-2 text-red-400" />
                  {node.result_data?.node_label || node.node_id}
                </h3>
                {node.error_message && (
                  <div className="bg-gray-800 border border-gray-700 rounded p-4 mb-4">
                    <p className="text-sm text-gray-300">
                      <strong>Error:</strong> {node.error_message}
                    </p>
                  </div>
                )}
              </div>
            ))}
        </section>
      )}

      {/* Execution-Level Error */}
      {exec.error_message && (
        <section>
          <div className="bg-red-900/20 border border-red-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-2">Execution Error</h3>
            <p className="text-sm text-red-300">{exec.error_message}</p>
          </div>
        </section>
      )}

      {/* Actions */}
      <section>
        <h2 className="text-xl font-bold text-white mb-4">🛠️ Actions</h2>
        <div className="flex flex-wrap gap-3">
          <button className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium flex items-center gap-2 transition-colors">
            <ArrowPathIcon className="w-5 h-5" />
            Re-run Flow
          </button>
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg font-medium transition-colors">
            Disable Check
          </button>
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg font-medium transition-colors">
            Adjust Threshold
          </button>
          <button className="px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg font-medium transition-colors">
            Create Issue
          </button>
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg font-medium transition-colors">
            Notify Owner
          </button>
        </div>
      </section>
    </div>
  );
};
