/**
 * KQI Service — API calls for Key Quality Indicator endpoints (F095)
 */
import { api } from './api';

// ─────────────────────────────────────────────────────────────────────────────
// Response types
// ─────────────────────────────────────────────────────────────────────────────

export interface CoverageInventoryResponse {
  total_datasets: number;
  datasets_analyzed: number;
  datasets_analyzed_pct: number;
  datasets_analyzed_24h: number;
  datasets_without_flows: number;
  total_flows: number;
  active_flows: number;
  active_flows_pct: number;
  paused_flows: number;
  failed_flows: number;
  avg_datasets_per_flow: number;
  avg_checks_per_flow: number;
  has_data: boolean;
}

export interface DimensionCount {
  dimension: string;
  count: number;
}

export interface CheckInventoryResponse {
  total_checks: number;
  checks_by_dimension: DimensionCount[];
  standard_checks: number;
  custom_checks: number;
  standard_checks_pct: number;
  has_data: boolean;
}

export interface GovernanceMaturityResponse {
  datasets_with_owner_pct: number;
  datasets_with_criticality_pct: number;
  datasets_with_domain_pct: number;
  datasets_with_thresholds_pct: number;
  checks_with_sla_pct: number;
  has_data: boolean;
}

export interface CoverageTrendDataPoint {
  date: string;
  datasets: number;
  flows: number;
  checks: number;
}

export interface CoverageTrendResponse {
  data_points: CoverageTrendDataPoint[];
  has_data: boolean;
}

export interface OperationalSummaryResponse {
  runs_per_day: number;
  success_rate: number;
  failure_rate: number;
  mttr_hours: number | null;
  quality_stability_index: number | null;
  has_data: boolean;
}

export interface TimelineDataPoint {
  date: string;
  success: number;
  partial: number;
  failed: number;
}

export interface OperationalTimelineResponse {
  data_points: TimelineDataPoint[];
  has_data: boolean;
}

export interface ColumnCoverage {
  column: string;
  checks_count: number;
  coverage_pct: number;
}

export interface WorstCheck {
  name: string;
  pass_rate: number;
}

export interface UnstableColumn {
  name: string;
  variance: number;
}

export interface DatasetProfileResponse {
  dataset_id: string;
  dataset_name: string;
  overall_score: number;
  dimension_scores: Record<string, number>;
  worst_check: WorstCheck | null;
  most_unstable_column: UnstableColumn | null;
  days_since_healthy: number | null;
  column_coverage: ColumnCoverage[];
  has_data: boolean;
}

export interface HealthDistributionItem {
  status: string;
  count: number;
}

export interface CheckIntelligenceSummaryResponse {
  noisy_checks_count: number;
  always_passing_count: number;
  always_failing_count: number;
  duplicate_checks_count: number;
  effectiveness_score: number;
  health_distribution: HealthDistributionItem[];
  has_data: boolean;
}

export interface ProblematicCheck {
  check_id: string;
  flow_id: string;
  flow_name: string;
  check_name: string;
  classification: string;
  flip_rate?: number;
  pass_rate_30d?: number;
  recommendation: string;
}

export interface ProblematicChecksResponse {
  checks: ProblematicCheck[];
  total: number;
  page: number;
  page_size: number;
}

export interface IssuesTrendDataPoint {
  date: string;
  count: number;
}

export interface BusinessValueSummaryResponse {
  issues_caught: number;
  issues_caught_trend: IssuesTrendDataPoint[];
  estimated_incidents_avoided: number;
  estimated_cost_saved_usd: number;
  has_data: boolean;
}

export interface TopFlowEntry {
  flow_id: string;
  flow_name: string;
  issues_caught: number;
  critical_issues: number;
  estimated_value_usd: number;
}

export interface TopFlowsResponse {
  flows: TopFlowEntry[];
}

// ─────────────────────────────────────────────────────────────────────────────
// API functions
// ─────────────────────────────────────────────────────────────────────────────

const base = (workspaceId: string) => `/workspaces/${workspaceId}/kqi`;

// Coverage
export async function getCoverageInventory(workspaceId: string, useCache = true): Promise<CoverageInventoryResponse> {
  const res = await api.get(`${base(workspaceId)}/coverage/inventory`, { params: { use_cache: useCache } });
  return res.data;
}

export async function getCheckInventory(workspaceId: string, useCache = true): Promise<CheckInventoryResponse> {
  const res = await api.get(`${base(workspaceId)}/coverage/checks`, { params: { use_cache: useCache } });
  return res.data;
}

export async function getGovernanceMaturity(workspaceId: string, useCache = true): Promise<GovernanceMaturityResponse> {
  const res = await api.get(`${base(workspaceId)}/coverage/maturity`, { params: { use_cache: useCache } });
  return res.data;
}

export async function getCoverageTrend(workspaceId: string, period = '30d'): Promise<CoverageTrendResponse> {
  const res = await api.get(`${base(workspaceId)}/coverage/trend`, { params: { period } });
  return res.data;
}

// Operational Intelligence
export async function getOperationalSummary(workspaceId: string, period = '30d', useCache = true): Promise<OperationalSummaryResponse> {
  const res = await api.get(`${base(workspaceId)}/operational/summary`, { params: { period, use_cache: useCache } });
  return res.data;
}

export async function getOperationalTimeline(workspaceId: string, period = '30d'): Promise<OperationalTimelineResponse> {
  const res = await api.get(`${base(workspaceId)}/operational/timeline`, { params: { period } });
  return res.data;
}

// Check Performance Heatmap
export interface CheckHeatmapCell {
  x: string;
  y: string;
  value: number;
}

export interface CheckHeatmapResponse {
  data: CheckHeatmapCell[];
  has_data: boolean;
}

export async function getCheckHeatmap(workspaceId: string, period = '30d'): Promise<CheckHeatmapResponse> {
  const res = await api.get(`${base(workspaceId)}/operational/check-heatmap`, { params: { period } });
  return res.data;
}

// Recent Alerts
export interface RecentAlertItem {
  date: string;
  check: string;
  severity: string;
  message: string;
  resolved: boolean;
}

export interface RecentAlertsResponse {
  alerts: RecentAlertItem[];
  has_data: boolean;
}

export async function getRecentAlerts(workspaceId: string, limit = 20): Promise<RecentAlertsResponse> {
  const res = await api.get(`${base(workspaceId)}/operational/recent-alerts`, { params: { limit } });
  return res.data;
}

// Dataset Quality
export async function getDatasetProfile(workspaceId: string, datasetId: string, period = '30d', useCache = true): Promise<DatasetProfileResponse> {
  const res = await api.get(`${base(workspaceId)}/datasets/${datasetId}/profile`, { params: { period, use_cache: useCache } });
  return res.data;
}

// Check Intelligence
export async function getCheckIntelligence(workspaceId: string, useCache = true): Promise<CheckIntelligenceSummaryResponse> {
  const res = await api.get(`${base(workspaceId)}/checks/intelligence`, { params: { use_cache: useCache } });
  return res.data;
}

export async function getProblematicChecks(workspaceId: string, page = 1, pageSize = 20): Promise<ProblematicChecksResponse> {
  const res = await api.get(`${base(workspaceId)}/checks/problematic`, { params: { page, page_size: pageSize } });
  return res.data;
}

// Business Value
export async function getBusinessValueSummary(workspaceId: string, period = '30d', useCache = true): Promise<BusinessValueSummaryResponse> {
  const res = await api.get(`${base(workspaceId)}/value/summary`, { params: { period, use_cache: useCache } });
  return res.data;
}

export async function getTopFlows(workspaceId: string, period = '30d', limit = 10): Promise<TopFlowsResponse> {
  const res = await api.get(`${base(workspaceId)}/value/top-flows`, { params: { period, limit } });
  return res.data;
}

// Cost Model Configuration
export interface CostModelEntry {
  severity: string;
  estimated_cost_usd: number;
}

export interface CostModelResponse {
  costs: CostModelEntry[];
  is_custom: boolean;
}

export async function getCostModel(workspaceId: string): Promise<CostModelResponse> {
  const res = await api.get(`${base(workspaceId)}/value/cost-model`);
  return res.data;
}

export async function updateCostModel(workspaceId: string, costs: CostModelEntry[]): Promise<CostModelResponse> {
  const res = await api.put(`${base(workspaceId)}/value/cost-model`, { costs });
  return res.data;
}

// ─────────────────────────────────────────────────────────────────────────────
// Incident SLA Analytics (F096)
// ─────────────────────────────────────────────────────────────────────────────

export interface IncidentSLAMetricsResponse {
  compliance_rate: number;
  breaches_count: number;
  avg_breach_duration_hours: number;
  mttr_hours: number;
  total_incidents: number;
  resolved_count: number;
  open_count: number;
  has_data: boolean;
}

export interface BreachDistributionItem {
  name: string;
  value: number;
}

export interface IncidentSLABreachesResponse {
  distribution: BreachDistributionItem[];
  has_data: boolean;
}

export interface ComplianceTrendPoint {
  date: string;
  compliance: number;
  breaches: number;
}

export interface IncidentSLAComplianceTrendResponse {
  trend: ComplianceTrendPoint[];
  has_data: boolean;
}

export interface IncidentSLAItem {
  id: string;
  title: string;
  severity: string;
  priority: string;
  status: string;
  created: string | null;
  sla_target_hours: number;
  elapsed_hours: number;
  breached: boolean;
  acknowledged_at: string | null;
  resolved_at: string | null;
  owner_id: string | null;
}

export interface IncidentSLAListResponse {
  items: IncidentSLAItem[];
  total: number;
  page: number;
  page_size: number;
  has_data: boolean;
}

export async function getIncidentSLAMetrics(workspaceId: string, period = '30d', useCache = true): Promise<IncidentSLAMetricsResponse> {
  const res = await api.get(`${base(workspaceId)}/incident-sla/metrics`, { params: { period, use_cache: useCache } });
  return res.data;
}

export async function getIncidentSLABreaches(workspaceId: string, period = '30d', useCache = true): Promise<IncidentSLABreachesResponse> {
  const res = await api.get(`${base(workspaceId)}/incident-sla/breaches`, { params: { period, use_cache: useCache } });
  return res.data;
}

export async function getIncidentSLAComplianceTrend(workspaceId: string, weeks = 8, useCache = true): Promise<IncidentSLAComplianceTrendResponse> {
  const res = await api.get(`${base(workspaceId)}/incident-sla/compliance-trend`, { params: { weeks, use_cache: useCache } });
  return res.data;
}

export async function getIncidentSLAList(workspaceId: string, period = '30d', page = 1, pageSize = 20): Promise<IncidentSLAListResponse> {
  const res = await api.get(`${base(workspaceId)}/incident-sla/incidents`, { params: { period, page, page_size: pageSize } });
  return res.data;
}

// ======================================================================
// Anomaly Detection (F098)
// ======================================================================

export interface AnomalySummaryResponse {
  total_anomalies: number;
  critical_anomalies: number;
  high_anomalies: number;
  medium_anomalies: number;
  low_anomalies: number;
  has_data: boolean;
}

export interface DetectedAnomaly {
  dataset: string;
  column: string;
  anomaly: string;
  anomaly_type: string;
  severity: 'Critical' | 'High' | 'Medium' | 'Low';
  detected: string | null;
  current_value: string;
  expected_value: string;
  deviation: string;
  status: string;
}

export interface DetectedAnomaliesResponse {
  anomalies: DetectedAnomaly[];
  has_data: boolean;
}

export interface VolumeTrendPoint {
  date: string;
  total_executions: number;
  failed_executions: number;
  successful_executions: number;
}

export interface VolumeTrendResponse {
  trends: VolumeTrendPoint[];
  has_data: boolean;
}

export interface AnomalySuggestion {
  signal: string;
  priority: string;
  action: string;
  estimated_impact: string;
}

export interface AnomalySuggestionsResponse {
  suggestions: AnomalySuggestion[];
  has_data: boolean;
}

export async function getAnomalySummary(workspaceId: string, period = '30d', useCache = true): Promise<AnomalySummaryResponse> {
  const res = await api.get(`${base(workspaceId)}/anomalies/summary`, { params: { period, use_cache: useCache } });
  return res.data;
}

export async function getDetectedAnomalies(workspaceId: string, period = '30d', useCache = true): Promise<DetectedAnomaliesResponse> {
  const res = await api.get(`${base(workspaceId)}/anomalies/detected`, { params: { period, use_cache: useCache } });
  return res.data;
}

export async function getAnomalyVolumeTrend(workspaceId: string, period = '30d', useCache = true): Promise<VolumeTrendResponse> {
  const res = await api.get(`${base(workspaceId)}/anomalies/volume-trend`, { params: { period, use_cache: useCache } });
  return res.data;
}

export async function getAnomalySuggestions(workspaceId: string, period = '30d', useCache = true): Promise<AnomalySuggestionsResponse> {
  const res = await api.get(`${base(workspaceId)}/anomalies/suggestions`, { params: { period, use_cache: useCache } });
  return res.data;
}
