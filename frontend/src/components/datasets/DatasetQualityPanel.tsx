import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueries, useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Eye,
  PlayCircle,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import {
  getRuleExecutionHistory,
  listRules,
  type RuleExecutionResponse,
  type RuleResponse,
} from '../../services/ruleService';
import { useTenantScopedPath } from '../../hooks/useTenantScopedPath';
import FaultyRecordsModal from '../common/FaultyRecordsModal';
import type { Dataset, DatasetField } from '../../types/dataset';

interface Props {
  workspaceId: string;
  dataset: Dataset;
}

const CATEGORY_COLORS: Record<string, string> = {
  completeness: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  validity: 'bg-green-500/15 text-green-300 border-green-500/30',
  conformity: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
  uniqueness: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
  consistency: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  accuracy: 'bg-red-500/15 text-red-300 border-red-500/30',
  timeliness: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  statistical: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
  reconciliation: 'bg-pink-500/15 text-pink-300 border-pink-500/30',
};

const STATUS_ICONS: Record<
  string,
  { icon: typeof CheckCircle2; color: string; label: string }
> = {
  active: { icon: CheckCircle2, color: 'text-green-400', label: 'Active' },
  draft: { icon: Clock, color: 'text-gray-400', label: 'Draft' },
  inactive: { icon: XCircle, color: 'text-red-400', label: 'Inactive' },
  archived: { icon: AlertTriangle, color: 'text-yellow-400', label: 'Archived' },
};

function executionStatusColor(status?: string | null): string {
  switch (status) {
    case 'completed':
      return 'text-green-400';
    case 'running':
    case 'pending':
      return 'text-blue-400';
    case 'failed':
      return 'text-red-400';
    case 'cancelled':
      return 'text-gray-400';
    default:
      return 'text-gray-500';
  }
}

function passRateColor(passRate: number | null | undefined): string {
  if (passRate == null) return 'text-gray-400';
  if (passRate >= 95) return 'text-green-400';
  if (passRate >= 80) return 'text-yellow-400';
  return 'text-red-400';
}

interface ColumnSummary {
  field: DatasetField;
  rules: RuleResponse[];
  latestExecutions: RuleExecutionResponse[];
  avgPassRate: number | null;
  totalFailedRows: number;
}

export default function DatasetQualityPanel({ workspaceId, dataset }: Props) {
  // 1. Fetch all workspace rules. We deliberately don't filter by
  //    data_source_id here because rules may have been created against a
  //    different data source row that points at the same physical table
  //    (e.g. NL-generated rules vs. user-registered datasets), or with no
  //    data_source_id at all. Filtering happens client-side by
  //    physical_identifier (+ optional schema) below.
  const rulesQuery = useQuery({
    queryKey: ['dataset-rules', workspaceId, dataset.physical_identifier],
    queryFn: () =>
      listRules(workspaceId, {
        limit: 1000,
      }),
    enabled: !!workspaceId && !!dataset.physical_identifier,
    staleTime: 30_000,
  });

  // 2. Filter to rules that target THIS dataset's physical table.
  //    F6 — robust matcher:
  //      • Prefer data_source_id equality when both sides have it (the
  //        most reliable signal; survives schema renames, case drift).
  //      • Otherwise fall back to physical-name match: case-insensitive,
  //        tolerate "schema.table" prefix on the rule side, and require
  //        schema match only when both sides explicitly report one.
  //    The previous filter was strict on case-sensitive schema and missed
  //    rules that legitimately target the same physical table — see B8.
  const datasetRules = useMemo<RuleResponse[]>(() => {
    if (!rulesQuery.data) return [];
    const target = (dataset.physical_identifier ?? '').toLowerCase();
    const datasetSchema = (dataset.schema_name ?? '').toLowerCase() || null;
    const datasetDsId = dataset.data_source_id ?? null;
    return rulesQuery.data.filter((r) => {
      // Prefer exact data_source_id match when available on both sides.
      if (datasetDsId && r.data_source_id) {
        if (r.data_source_id !== datasetDsId) return false;
        // data_source_id matched — still require table-name match so
        // we don't pick up rules on sibling tables in the same source.
      }
      const ruleTable = (r.target_table ?? '').toLowerCase();
      if (!ruleTable) return false;
      const tableMatch =
        ruleTable === target ||
        // Tolerate "schema.table" prefixed values on the rule side.
        ruleTable.endsWith(`.${target}`);
      if (!tableMatch) return false;
      // If both sides report a schema, require it to match (case-insensitive).
      const ruleSchema = (r.target_schema ?? '').toLowerCase() || null;
      if (ruleSchema && datasetSchema) {
        return ruleSchema === datasetSchema;
      }
      return true;
    });
  }, [
    rulesQuery.data,
    dataset.physical_identifier,
    dataset.schema_name,
    dataset.data_source_id,
  ]);

  // 3. For each rule, fetch the last 30 executions. We use this both for
  //    "latest execution" cards and for the F10 30-day pass-rate sparkline
  //    rendered in the header.
  const executionQueries = useQueries({
    queries: datasetRules.map((rule) => ({
      queryKey: ['rule-exec-history', workspaceId, rule.id],
      queryFn: () => getRuleExecutionHistory(workspaceId, rule.id, { limit: 30 }),
      enabled: !!workspaceId && !!rule.id,
      staleTime: 15_000,
    })),
  });

  const executionsByRule = useMemo<Record<string, RuleExecutionResponse[]>>(() => {
    const out: Record<string, RuleExecutionResponse[]> = {};
    datasetRules.forEach((rule, idx) => {
      out[rule.id] = executionQueries[idx]?.data ?? [];
    });
    return out;
  }, [datasetRules, executionQueries]);

  const latestByRule = useMemo<Record<string, RuleExecutionResponse | undefined>>(() => {
    const out: Record<string, RuleExecutionResponse | undefined> = {};
    datasetRules.forEach((rule) => {
      const list = executionsByRule[rule.id] ?? [];
      // executions endpoint returns most-recent first.
      out[rule.id] = list.length > 0 ? list[0] : undefined;
    });
    return out;
  }, [datasetRules, executionsByRule]);

  // F10 — 30-day pass-rate sparkline points + per-dimension donut slices.
  const headerCharts = useMemo(() => {
    const allExecs: RuleExecutionResponse[] = Object.values(executionsByRule).flat();
    const completed = allExecs.filter(
      (e) => e.status === 'completed' && e.pass_rate != null,
    );
    // Bucket by day for the last 30 days.
    const now = Date.now();
    const horizon = now - 30 * 24 * 60 * 60 * 1000;
    const buckets = new Map<string, { sum: number; count: number; ts: number }>();
    for (const e of completed) {
      const ts = Date.parse(e.completed_at ?? e.created_at);
      if (!Number.isFinite(ts) || ts < horizon) continue;
      const day = new Date(ts).toISOString().slice(0, 10);
      const cur = buckets.get(day) ?? { sum: 0, count: 0, ts };
      cur.sum += Number(e.pass_rate);
      cur.count += 1;
      cur.ts = Math.max(cur.ts, ts);
      buckets.set(day, cur);
    }
    const sparkline = Array.from(buckets.values())
      .sort((a, b) => a.ts - b.ts)
      .map((b) => b.sum / b.count);

    // Per-category donut (counts).
    const categoryCounts = new Map<string, number>();
    for (const r of datasetRules) {
      categoryCounts.set(r.category, (categoryCounts.get(r.category) ?? 0) + 1);
    }
    const donut = Array.from(categoryCounts.entries())
      .map(([category, count]) => ({ category, count }))
      .sort((a, b) => b.count - a.count);

    return { sparkline, donut };
  }, [executionsByRule, datasetRules]);

  // 4. Aggregate per-column quality stats.
  const columnSummaries = useMemo<ColumnSummary[]>(() => {
    const fields = dataset.fields ?? [];
    return fields.map((field) => {
      const rulesForField = datasetRules.filter(
        (r) => r.target_columns?.includes(field.field_name),
      );
      const latestExecs = rulesForField
        .map((r) => latestByRule[r.id])
        .filter((e): e is RuleExecutionResponse => !!e);
      const ratesWithValues = latestExecs
        .map((e) => (e.pass_rate == null ? null : Number(e.pass_rate)))
        .filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
      const avgPassRate =
        ratesWithValues.length > 0
          ? ratesWithValues.reduce((a, b) => a + b, 0) / ratesWithValues.length
          : null;
      const totalFailedRows = latestExecs.reduce(
        (acc, e) => acc + (e.rows_failed ?? 0),
        0,
      );
      return {
        field,
        rules: rulesForField,
        latestExecutions: latestExecs,
        avgPassRate,
        totalFailedRows,
      };
    });
  }, [dataset.fields, datasetRules, latestByRule]);

  // 5. Top-level summary cards.
  const summary = useMemo(() => {
    const totalRules = datasetRules.length;
    const activeRules = datasetRules.filter((r) => r.is_active && r.status === 'active').length;
    const allLatest = Object.values(latestByRule).filter(
      (e): e is RuleExecutionResponse => !!e,
    );
    const completedLatest = allLatest.filter((e) => e.status === 'completed');
    const ratesWithValues = completedLatest
      .map((e) => (e.pass_rate == null ? null : Number(e.pass_rate)))
      .filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
    const overallPassRate =
      ratesWithValues.length > 0
        ? ratesWithValues.reduce((a, b) => a + b, 0) / ratesWithValues.length
        : null;
    const lastRunAt = allLatest
      .map((e) => e.completed_at ?? e.started_at ?? e.created_at)
      .filter((v): v is string => !!v)
      .sort()
      .pop();
    const totalFailedRows = allLatest.reduce(
      (acc, e) => acc + (e.rows_failed ?? 0),
      0,
    );
    const failedExecs = allLatest.filter((e) => e.status === 'failed').length;
    return {
      totalRules,
      activeRules,
      overallPassRate,
      lastRunAt,
      totalFailedRows,
      failedExecs,
      executedRulesCount: allLatest.length,
    };
  }, [datasetRules, latestByRule]);

  const isLoading =
    rulesQuery.isLoading ||
    executionQueries.some((q) => q.isLoading);

  // Build a workspace-scoped link for navigating to rule detail / NL builder.
  const { wsPath } = useTenantScopedPath();
  const rulesListPath = wsPath(workspaceId, '/rules');
  const nlRuleBuilderPath = wsPath(workspaceId, '/nl-rule-builder');

  // F-faulty — modal state for the per-rule "View faulty records" action.
  const [faultySource, setFaultySource] = useState<
    | { executionId: string; ruleName: string; subtitle: string }
    | null
  >(null);

  return (
    <div
      className="rounded-2xl border border-gray-700 bg-gray-800/60 overflow-hidden"
      data-testid="dataset-quality-panel"
    >
      <div className="px-5 py-3 border-b border-gray-700 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          <h2 className="text-sm font-medium text-gray-200">Data Quality</h2>
          {datasetRules.length > 0 && (
            <span className="text-xs text-gray-500">
              ({datasetRules.length} rule{datasetRules.length === 1 ? '' : 's'})
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Link
            to={`${nlRuleBuilderPath}?dataset_id=${dataset.dataset_id}`}
            data-testid="quality-add-rule-link"
            className="text-xs text-purple-300 hover:text-purple-200"
          >
            + Author rule
          </Link>
          <Link
            to={rulesListPath}
            className="text-xs text-gray-400 hover:text-gray-200"
          >
            All rules →
          </Link>
        </div>
      </div>

      {/* Body */}
      <div className="p-5 space-y-5">
        {/* Loading + empty states */}
        {rulesQuery.isError && (
          <div
            className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-300 text-sm"
            data-testid="dataset-quality-error"
          >
            Failed to load rules for this dataset.
          </div>
        )}

        {!rulesQuery.isError && rulesQuery.isLoading && (
          <div
            className="text-gray-400 text-sm"
            data-testid="dataset-quality-loading"
          >
            Loading rules…
          </div>
        )}

        {!rulesQuery.isLoading && !rulesQuery.isError && datasetRules.length === 0 && (
          <div
            className="rounded-lg border border-gray-700 bg-gray-900/40 px-4 py-6 text-center"
            data-testid="dataset-quality-empty"
          >
            <ShieldCheck className="w-6 h-6 text-gray-500 mx-auto mb-2" />
            <p className="text-sm text-gray-300">
              No data quality rules target this dataset yet.
            </p>
            <Link
              to={`${nlRuleBuilderPath}?dataset_id=${dataset.dataset_id}`}
              className="mt-2 inline-block text-xs text-purple-300 hover:text-purple-200"
            >
              Author your first rule →
            </Link>
          </div>
        )}

        {/* F10 — 30-day pass-rate trend + dimension breakdown */}
        {datasetRules.length > 0 && (headerCharts.sparkline.length > 0 || headerCharts.donut.length > 0) && (
          <div
            className="grid grid-cols-1 md:grid-cols-2 gap-3"
            data-testid="quality-header-charts"
          >
            <div className="rounded-lg border border-gray-700 bg-gray-900/40 px-3 py-3">
              <p className="text-[11px] uppercase tracking-wide text-gray-400 mb-1">
                Pass rate — last 30 days
              </p>
              {headerCharts.sparkline.length > 0 ? (
                <PassRateSparkline values={headerCharts.sparkline} />
              ) : (
                <p className="text-xs text-gray-500">No completed executions in the last 30 days.</p>
              )}
            </div>
            <div className="rounded-lg border border-gray-700 bg-gray-900/40 px-3 py-3">
              <p className="text-[11px] uppercase tracking-wide text-gray-400 mb-1">
                Rules by dimension
              </p>
              {headerCharts.donut.length > 0 ? (
                <CategoryDonut slices={headerCharts.donut} />
              ) : (
                <p className="text-xs text-gray-500">No categorized rules.</p>
              )}
            </div>
          </div>
        )}

        {/* Summary cards */}
        {datasetRules.length > 0 && (
          <div
            className="grid grid-cols-2 md:grid-cols-4 gap-3"
            data-testid="dataset-quality-summary"
          >
            <SummaryCard
              label="Overall pass rate"
              value={
                summary.overallPassRate != null
                  ? `${summary.overallPassRate.toFixed(1)}%`
                  : '—'
              }
              tone={
                summary.overallPassRate == null
                  ? 'neutral'
                  : summary.overallPassRate >= 95
                    ? 'good'
                    : summary.overallPassRate >= 80
                      ? 'warn'
                      : 'bad'
              }
              testid="quality-card-pass-rate"
              hint={
                summary.executedRulesCount === 0
                  ? 'Not executed yet'
                  : `${summary.executedRulesCount} execution${summary.executedRulesCount === 1 ? '' : 's'} sampled`
              }
            />
            <SummaryCard
              label="Active rules"
              value={`${summary.activeRules} / ${summary.totalRules}`}
              tone={summary.activeRules > 0 ? 'good' : 'neutral'}
              testid="quality-card-active-rules"
            />
            <SummaryCard
              label="Failed rows"
              value={summary.totalFailedRows.toLocaleString()}
              tone={summary.totalFailedRows === 0 ? 'good' : summary.totalFailedRows > 100 ? 'bad' : 'warn'}
              testid="quality-card-failed-rows"
              hint={
                summary.failedExecs > 0
                  ? `${summary.failedExecs} execution${summary.failedExecs === 1 ? '' : 's'} errored`
                  : undefined
              }
            />
            <SummaryCard
              label="Last run"
              value={
                summary.lastRunAt ? new Date(summary.lastRunAt).toLocaleString() : '—'
              }
              tone="neutral"
              testid="quality-card-last-run"
              hint={summary.lastRunAt ? undefined : 'Run a rule to populate metrics'}
            />
          </div>
        )}

        {/* Per-column breakdown */}
        {datasetRules.length > 0 && columnSummaries.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-xs font-medium uppercase tracking-wide text-gray-400">
              Quality by column
            </h3>
            <div
              className="rounded-lg border border-gray-700 overflow-hidden"
              data-testid="quality-columns-table"
            >
              <table className="w-full text-sm">
                <thead className="bg-gray-900/50">
                  <tr>
                    <th className="text-left px-4 py-2 text-gray-400 font-medium">Column</th>
                    <th className="text-left px-4 py-2 text-gray-400 font-medium">Type</th>
                    <th className="text-right px-4 py-2 text-gray-400 font-medium">Rules</th>
                    <th className="text-right px-4 py-2 text-gray-400 font-medium">Avg pass rate</th>
                    <th className="text-right px-4 py-2 text-gray-400 font-medium">Failed rows</th>
                  </tr>
                </thead>
                <tbody>
                  {columnSummaries.map((cs) => (
                    <tr
                      key={cs.field.field_id}
                      className="border-t border-gray-700/60"
                      data-testid={`quality-column-row-${cs.field.field_name}`}
                    >
                      <td className="px-4 py-2 text-white font-mono">{cs.field.field_name}</td>
                      <td className="px-4 py-2 text-gray-400">{cs.field.data_type}</td>
                      <td className="px-4 py-2 text-right text-gray-300">{cs.rules.length}</td>
                      <td
                        className={`px-4 py-2 text-right font-medium ${passRateColor(cs.avgPassRate)}`}
                      >
                        {cs.avgPassRate != null ? `${cs.avgPassRate.toFixed(1)}%` : '—'}
                      </td>
                      <td className="px-4 py-2 text-right text-gray-300">
                        {cs.totalFailedRows > 0 ? cs.totalFailedRows.toLocaleString() : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Rules list */}
        {datasetRules.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-xs font-medium uppercase tracking-wide text-gray-400">
              Rules applied to this dataset
            </h3>
            <div className="space-y-2" data-testid="quality-rules-list">
              {datasetRules.map((rule) => {
                const latest = latestByRule[rule.id];
                const statusCfg = STATUS_ICONS[rule.status] ?? STATUS_ICONS.draft;
                const StatusIcon = statusCfg.icon;
                const categoryClass =
                  CATEGORY_COLORS[rule.category] ?? 'bg-gray-700 text-gray-200 border-gray-600';
                return (
                  <div
                    key={rule.id}
                    className="block rounded-lg border border-gray-700 bg-gray-900/40 hover:bg-gray-900/70 transition-colors px-4 py-3"
                    data-testid={`quality-rule-card-${rule.id}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Link
                            to={wsPath(workspaceId, `/rules?rule=${rule.id}`)}
                            className="text-sm font-medium text-white truncate hover:text-purple-300"
                          >
                            {rule.name}
                          </Link>
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border ${categoryClass}`}
                          >
                            {rule.category}
                          </span>
                          <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
                            <StatusIcon className={`w-3 h-3 ${statusCfg.color}`} />
                            {statusCfg.label}
                          </span>
                        </div>
                        {rule.description && (
                          <p className="mt-1 text-xs text-gray-400 line-clamp-1">
                            {rule.description}
                          </p>
                        )}
                        {(rule.target_columns?.length ?? 0) > 0 && (
                          <p className="mt-1 text-[11px] text-gray-500 font-mono">
                            columns: {rule.target_columns!.join(', ')}
                          </p>
                        )}
                        {/* F7 — quick links into the rule and its execution history */}
                        <div className="mt-2 flex items-center gap-3 text-[11px]">
                          <Link
                            to={wsPath(workspaceId, `/rules?rule=${rule.id}`)}
                            className="text-purple-300 hover:text-purple-200"
                            data-testid={`quality-rule-open-${rule.id}`}
                          >
                            Open rule →
                          </Link>
                          <Link
                            to={wsPath(workspaceId, `/rules?rule=${rule.id}&tab=executions`)}
                            className="text-gray-300 hover:text-white inline-flex items-center gap-1"
                            data-testid={`quality-rule-executions-${rule.id}`}
                          >
                            <PlayCircle className="w-3 h-3" /> Executions →
                          </Link>
                          {latest && (latest.rows_failed ?? 0) > 0 && (
                            <button
                              type="button"
                              onClick={() =>
                                setFaultySource({
                                  executionId: latest.id,
                                  ruleName: rule.name,
                                  subtitle: `${rule.name} · ${(latest.rows_failed ?? 0).toLocaleString()} failed row${
                                    (latest.rows_failed ?? 0) === 1 ? '' : 's'
                                  }${
                                    latest.completed_at
                                      ? ` · ${new Date(latest.completed_at).toLocaleString()}`
                                      : ''
                                  }`,
                                })
                              }
                              className="inline-flex items-center gap-1 text-red-300 hover:text-red-200"
                              data-testid={`quality-rule-faulty-${rule.id}`}
                            >
                              <Eye className="w-3 h-3" /> View faulty records →
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Latest execution snapshot */}
                      <div className="text-right text-xs text-gray-300 min-w-[150px]">
                        {latest ? (
                          <>
                            <div
                              className={`font-medium ${executionStatusColor(latest.status)}`}
                            >
                              {latest.status}
                            </div>
                            <div className={`mt-0.5 ${passRateColor(latest.pass_rate ?? null)}`}>
                              {latest.pass_rate != null
                                ? `pass ${Number(latest.pass_rate).toFixed(1)}%`
                                : '—'}
                            </div>
                            <div className="mt-0.5 text-gray-500">
                              {(latest.rows_scanned ?? 0).toLocaleString()} scanned ·{' '}
                              {(latest.rows_failed ?? 0).toLocaleString()} failed
                            </div>
                            {latest.completed_at && (
                              <div className="text-gray-500">
                                {new Date(latest.completed_at).toLocaleString()}
                              </div>
                            )}
                          </>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-gray-500">
                            <PlayCircle className="w-3 h-3" /> Not executed
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {isLoading && datasetRules.length > 0 && (
          <p className="text-xs text-gray-500">Refreshing execution data…</p>
        )}
      </div>

      <FaultyRecordsModal
        workspaceId={workspaceId}
        source={
          faultySource
            ? {
                kind: 'execution',
                executionId: faultySource.executionId,
                title: `Faulty records · ${faultySource.ruleName}`,
                subtitle: faultySource.subtitle,
              }
            : null
        }
        onClose={() => setFaultySource(null)}
      />
    </div>
  );
}

interface SummaryCardProps {
  label: string;
  value: string;
  tone: 'good' | 'warn' | 'bad' | 'neutral';
  hint?: string;
  testid?: string;
}

function SummaryCard({ label, value, tone, hint, testid }: SummaryCardProps) {
  const toneClass: Record<SummaryCardProps['tone'], string> = {
    good: 'text-green-400',
    warn: 'text-yellow-400',
    bad: 'text-red-400',
    neutral: 'text-gray-200',
  };
  return (
    <div
      className="rounded-lg border border-gray-700 bg-gray-900/40 px-3 py-2"
      data-testid={testid}
    >
      <p className="text-[11px] uppercase tracking-wide text-gray-400">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${toneClass[tone]}`}>{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-gray-500">{hint}</p>}
    </div>
  );
}

// F10 — lightweight inline SVG sparkline. No chart-lib dependency: easier to
// audit, smaller bundle, deterministic test snapshots.
function PassRateSparkline({ values }: { values: number[] }) {
  if (values.length === 0) return null;
  const W = 240;
  const H = 56;
  const PAD = 4;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = values.length === 1 ? 0 : (W - PAD * 2) / (values.length - 1);
  const points = values.map((v, i) => {
    const x = PAD + i * stepX;
    const y = PAD + (H - PAD * 2) * (1 - (v - min) / span);
    return [x, y] as const;
  });
  const path = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const last = values[values.length - 1];
  const stroke = last >= 95 ? '#34d399' : last >= 80 ? '#fbbf24' : '#f87171';
  return (
    <div className="flex items-center gap-3" data-testid="quality-sparkline">
      <svg width={W} height={H} role="img" aria-label="Pass rate trend">
        <path d={path} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
        {points.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={1.6} fill={stroke} />
        ))}
      </svg>
      <div className="text-xs text-gray-300">
        <div className="font-semibold" style={{ color: stroke }}>{last.toFixed(1)}%</div>
        <div className="text-gray-500">latest</div>
      </div>
    </div>
  );
}

// F10 — minimal SVG donut (no recharts). Hue cycles through a fixed palette so
// repeated categories stay visually distinct.
const DONUT_COLORS = ['#a78bfa', '#34d399', '#60a5fa', '#fbbf24', '#f87171', '#22d3ee', '#f472b6', '#818cf8'];
function CategoryDonut({ slices }: { slices: { category: string; count: number }[] }) {
  const total = slices.reduce((acc, s) => acc + s.count, 0);
  if (total === 0) return null;
  const SIZE = 64;
  const R = 26;
  const C = 2 * Math.PI * R;
  let offset = 0;
  return (
    <div className="flex items-center gap-3" data-testid="quality-donut">
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        <g transform={`translate(${SIZE / 2} ${SIZE / 2}) rotate(-90)`}>
          {slices.map((s, i) => {
            const frac = s.count / total;
            const dash = C * frac;
            const seg = (
              <circle
                key={s.category}
                r={R}
                cx={0}
                cy={0}
                fill="transparent"
                stroke={DONUT_COLORS[i % DONUT_COLORS.length]}
                strokeWidth={10}
                strokeDasharray={`${dash} ${C - dash}`}
                strokeDashoffset={-offset}
              />
            );
            offset += dash;
            return seg;
          })}
        </g>
        <text x="50%" y="54%" textAnchor="middle" fontSize="12" fill="#e5e7eb">{total}</text>
      </svg>
      <ul className="text-xs text-gray-300 space-y-0.5">
        {slices.slice(0, 4).map((s, i) => (
          <li key={s.category} className="flex items-center gap-1.5">
            <span className="inline-block w-2 h-2 rounded-sm" style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }} />
            <span className="capitalize">{s.category}</span>
            <span className="text-gray-500">({s.count})</span>
          </li>
        ))}
        {slices.length > 4 && (
          <li className="text-gray-500">+{slices.length - 4} more</li>
        )}
      </ul>
    </div>
  );
}
