/**
 * Reporting Service - API calls for dashboards and metrics
 */
import { api } from './api';

export interface OverviewMetrics {
  total_rules: number;
  total_executions: number;
  average_pass_rate: number;
  dq_score: number;
  critical_violations: number;
  total_data_sources: number;
  total_flows: number;
  last_updated: string;
}

export interface TrendDataPoint {
  timestamp: string;
  value: number;
  label?: string;
}

export interface TrendMetrics {
  metric_name: string;
  data_points: TrendDataPoint[];
  time_period: string;
}

export interface CategoryMetrics {
  category: string;
  total_rules: number;
  total_executions: number;
  pass_rate: number;
  avg_execution_time: number;
}

export interface CategoryBreakdown {
  categories: CategoryMetrics[];
  total: number;
}

export interface SourceMetrics {
  source_id: string;
  source_name: string;
  total_rules: number;
  total_executions: number;
  pass_rate: number;
  last_execution: string | null;
  health_status: string;
}

export interface SourceBreakdown {
  sources: SourceMetrics[];
  total: number;
}

export interface ScorecardDimension {
  dimension: string;
  score: number;
  weight: number;
  issues_count: number;
  trend: string;
}

export interface Scorecard {
  overall_score: number;
  dimensions: ScorecardDimension[];
  total_issues: number;
  critical_issues: number;
  trend: string;
  last_updated: string;
}

const reportingService = {
  /**
   * Get overview metrics for workspace or specific flow
   */
  getOverviewMetrics: async (
    workspaceId: string,
    useCache: boolean = true,
    flowId?: string,
    executionId?: string
  ): Promise<OverviewMetrics> => {
    const params: any = { use_cache: useCache };
    if (flowId) {
      params.flow_id = flowId;
    }
    if (executionId) {
      params.execution_id = executionId;
    }
    const response = await api.get(
      `/workspaces/${workspaceId}/metrics/overview`,
      { params }
    );
    return response.data;
  },

  /**
   * Get trend metrics
   */
  getTrendMetrics: async (
    workspaceId: string,
    metricName: string = 'pass_rate',
    period: string = '30d'
  ): Promise<TrendMetrics> => {
    const response = await api.get(
      `/workspaces/${workspaceId}/metrics/trends`,
      {
        params: { metric_name: metricName, period },
      }
    );
    return response.data;
  },

  /**
   * Get category breakdown
   */
  getCategoryBreakdown: async (
    workspaceId: string,
    period: string = '30d',
    flowId?: string
  ): Promise<CategoryBreakdown> => {
    const params: any = { period };
    if (flowId) {
      params.flow_id = flowId;
    }
    const response = await api.get(
      `/workspaces/${workspaceId}/metrics/by-category`,
      { params }
    );
    return response.data;
  },

  /**
   * Get source breakdown
   */
  getSourceBreakdown: async (
    workspaceId: string,
    period: string = '30d',
    flowId?: string
  ): Promise<SourceBreakdown> => {
    const params: any = { period };
    if (flowId) {
      params.flow_id = flowId;
    }
    const response = await api.get(
      `/workspaces/${workspaceId}/metrics/by-source`,
      { params }
    );
    return response.data;
  },

  /**
   * Get data quality scorecard
   */
  getScorecard: async (
    workspaceId: string,
    period: string = '30d'
  ): Promise<Scorecard> => {
    const response = await api.get(
      `/workspaces/${workspaceId}/metrics/scorecard`,
      {
        params: { period },
      }
    );
    return response.data;
  },

  /**
   * Get column-level metrics
   */
  getColumnMetrics: async (
    workspaceId: string,
    flowId?: string,
    executionId?: string
  ): Promise<any> => {
    const params: any = {};
    if (flowId) {
      params.flow_id = flowId;
    }
    if (executionId) {
      params.execution_id = executionId;
    }
    const response = await api.get(
      `/workspaces/${workspaceId}/metrics/by-column`,
      { params }
    );
    return response.data;
  },

  /**
   * Get dimensional breakdown (structural, semantic, statistical)
   */
  getDimensionalBreakdown: async (
    workspaceId: string,
    flowId?: string,
    executionId?: string
  ): Promise<any> => {
    const params: any = {};
    if (flowId) {
      params.flow_id = flowId;
    }
    if (executionId) {
      params.execution_id = executionId;
    }
    const response = await api.get(
      `/workspaces/${workspaceId}/metrics/by-dimension`,
      { params }
    );
    return response.data;
  },
  /**
   * Get workspace entity counts for the hub dashboard (F114)
   */
  getWorkspaceStats: async (workspaceId: string): Promise<WorkspaceStats> => {
    const response = await api.get(`/workspaces/${workspaceId}/stats`);
    return response.data;
  },
};

export interface WorkspaceStats {
  datasource_count: number;
  glossary_count: number;
  flow_count: number;
  rule_count: number;
  issue_count: number;
  dataset_count: number;
}

export default reportingService;
