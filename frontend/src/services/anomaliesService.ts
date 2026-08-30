/**
 * Anomalies service — F5
 *
 * Wraps the persisted anomaly endpoints under
 *   /api/v1/workspaces/{ws}/anomalies
 */
import { api } from './api';

export type AnomalyStatus = 'open' | 'acknowledged' | 'resolved' | 'suppressed';
export type AnomalySeverity = 'Critical' | 'High' | 'Medium' | 'Low';
export type AnomalyType = 'pass_rate_drop' | 'volume_anomaly' | 'failure_spike' | string;

export interface Anomaly {
  id: string;
  workspace_id: string;
  anomaly_type: AnomalyType;
  severity: AnomalySeverity;
  dataset: string | null;
  column: string | null;
  rule_id: string | null;
  summary: string;
  current_value: string | null;
  expected_value: string | null;
  deviation: string | null;
  status: AnomalyStatus;
  detected_at: string | null;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AnomaliesListResponse {
  total: number;
  items: Anomaly[];
}

export interface RunDetectionResponse {
  detected: number;
  inserted: number;
  updated: number;
}

export interface ListAnomalyParams {
  status?: AnomalyStatus;
  severity?: AnomalySeverity;
  anomaly_type?: AnomalyType;
  limit?: number;
  offset?: number;
}

const base = (workspaceId: string) =>
  `/workspaces/${workspaceId}/anomalies`;

export async function runAnomalyDetection(workspaceId: string, periodDays = 30): Promise<RunDetectionResponse> {
  const { data } = await api.post<RunDetectionResponse>(`${base(workspaceId)}/run`, { period_days: periodDays });
  return data;
}

export async function listAnomalies(workspaceId: string, params: ListAnomalyParams = {}): Promise<AnomaliesListResponse> {
  const { data } = await api.get<AnomaliesListResponse>(base(workspaceId), { params });
  return data;
}

export async function getAnomaly(workspaceId: string, anomalyId: string): Promise<Anomaly> {
  const { data } = await api.get<Anomaly>(`${base(workspaceId)}/${anomalyId}`);
  return data;
}

export async function acknowledgeAnomaly(workspaceId: string, anomalyId: string, notes?: string): Promise<Anomaly> {
  const { data } = await api.post<Anomaly>(`${base(workspaceId)}/${anomalyId}/acknowledge`, { notes });
  return data;
}

export async function resolveAnomaly(workspaceId: string, anomalyId: string, notes?: string): Promise<Anomaly> {
  const { data } = await api.post<Anomaly>(`${base(workspaceId)}/${anomalyId}/resolve`, { notes });
  return data;
}

export async function suppressAnomaly(workspaceId: string, anomalyId: string, notes?: string): Promise<Anomaly> {
  const { data } = await api.post<Anomaly>(`${base(workspaceId)}/${anomalyId}/suppress`, { notes });
  return data;
}
