/**
 * TypeScript types for F003 Workspace Default Policies / Settings.
 *
 * Shapes mirror the backend WorkspaceSettings API contract:
 *   GET  /api/v1/workspaces/{id}/settings  → WorkspaceSettingsResponse
 *   PATCH /api/v1/workspaces/{id}/settings → WorkspaceSettingsResponse
 */

// ---------------------------------------------------------------------------
// Grouped sub-types
// ---------------------------------------------------------------------------

export interface TimezonePolicy {
  default_timezone: string;
}

export interface SeverityPolicy {
  critical_label: string;
  major_label: string;
  minor_label: string;
  informational_label: string;
}

export interface SlaPolicy {
  critical_hours: number;
  major_hours: number;
  minor_hours: number;
  informational_hours: number | null;
}

export type IssueGroupingMode =
  | 'one_per_execution'
  | 'one_per_rule'
  | 'one_per_day';

export interface NamingConstraint {
  max_length: number | null;
  allowed_pattern: string | null;
  forbidden_keywords: string[] | null;
}

export interface NamingStandards {
  datasets: NamingConstraint;
  rules: NamingConstraint;
}

export interface LLMConfig {
  provider: string;
  api_key_masked: string;
  model: string;
  temperature: number;
  max_tokens: number;
  configured: boolean;
}

export type IncidentSeverityFloor =
  | 'critical'
  | 'major'
  | 'minor'
  | 'informational';

export interface IncidentPolicy {
  enabled: boolean;
  min_severity: IncidentSeverityFloor;
  recurrence_threshold: number;
  auto_priority: 'P1' | 'P2' | 'P3' | 'P4' | null;
  auto_owner_user_id: string | null;
}

// ---------------------------------------------------------------------------
// Full settings shape returned by GET and PATCH responses
// ---------------------------------------------------------------------------

export interface WorkspaceSettingsData {
  workspace_id: string;
  tenant_id: string;
  timezone_policy: TimezonePolicy;
  severity_policy: SeverityPolicy;
  sla_policy: SlaPolicy;
  issue_grouping_policy: IssueGroupingMode;
  naming_standards: NamingStandards;
  llm_config: LLMConfig | null;
  incident_policy: IncidentPolicy | null;
  updated_at: string | null;
  updated_by: string | null;
}

/** Shape of the full API response envelope */
export interface WorkspaceSettingsResponse {
  data: WorkspaceSettingsData;
}

// ---------------------------------------------------------------------------
// PATCH request body — all fields optional
// ---------------------------------------------------------------------------

export interface LLMConfigUpdate {
  provider: string;
  api_key: string;
  model: string;
  temperature?: number;
  max_tokens?: number;
}

export interface WorkspaceSettingsUpdate {
  timezone_policy?: Partial<TimezonePolicy>;
  severity_policy?: Partial<SeverityPolicy>;
  sla_policy?: Partial<SlaPolicy>;
  issue_grouping_policy?: IssueGroupingMode;
  naming_standards?: {
    datasets?: Partial<NamingConstraint>;
    rules?: Partial<NamingConstraint>;
  };
  llm_config?: LLMConfigUpdate;
  incident_policy?: Partial<IncidentPolicy>;
}
