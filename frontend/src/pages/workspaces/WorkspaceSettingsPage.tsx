/**
 * WorkspaceSettingsPage — workspace settings management page (F003 P07).
 *
 * Route: /workspaces/:workspace_id/settings
 *
 * Access control (UI level — backend enforces authoritatively):
 *   - workspace_administrator: all sections editable
 *   - data_engineer / data_steward: read-only view
 *   - platform_operator / platform_viewer / others: redirected to /404
 *
 * Data flow:
 *   - React Query fetches GET /workspaces/{id}/settings on mount.
 *   - Each section has its own Save handler that issues a PATCH with just
 *     that section's data.
 *   - Success: toast notification + query invalidated (refetch).
 */
import { useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle } from 'lucide-react';
import toast from 'react-hot-toast';

import { getWorkspaceSettings, updateWorkspaceSettings } from '../../services/workspaceSettings';
import { getActorRole, getActorId } from '../../utils/jwt';
import { useWorkspacePermissions } from '../../hooks/useWorkspacePermissions';
import ForbiddenPage from '../admin/ForbiddenPage';
import type {
  TimezonePolicy,
  SeverityPolicy,
  SlaPolicy,
  IssueGroupingMode,
  NamingConstraint,
  LLMConfigUpdate,
  IncidentPolicy,
} from '../../types/workspaceSettings';

import WorkspaceSettingsHeader from '../../components/workspaces/settings/WorkspaceSettingsHeader';
import TimezoneSection from '../../components/workspaces/settings/TimezoneSection';
import SeverityPolicySection from '../../components/workspaces/settings/SeverityPolicySection';
import SLAPolicySection from '../../components/workspaces/settings/SLAPolicySection';
import IssueGroupingSection from '../../components/workspaces/settings/IssueGroupingSection';
import NamingStandardsSection from '../../components/workspaces/settings/NamingStandardsSection';
import LLMConfigSection from '../../components/workspaces/settings/LLMConfigSection';
import CostModelSection from '../../components/workspaces/settings/CostModelSection';
import IncidentPolicySection from '../../components/workspaces/settings/IncidentPolicySection';

const STALE_TIME = 30_000;

export default function WorkspaceSettingsPage() {
  const { workspace_id } = useParams<{ workspace_id: string }>();
  const queryClient = useQueryClient();

  // Resolve platform role and actor id from JWT
  const token = localStorage.getItem('access_token');
  const platformRole = getActorRole(token);
  const actorId = getActorId(token) ?? undefined;
  const isPlatformAdmin = platformRole === 'platform_admin';
  const isTenantAdmin = platformRole === 'tenant_admin';
  const isPlatformOperator = isPlatformAdmin || platformRole === 'platform_viewer';

  // Workspace-level permissions (skipped for platform operators and tenant admins — they bypass workspace roles)
  const { can, loading: permLoading } = useWorkspacePermissions(
    isPlatformOperator || isTenantAdmin ? undefined : workspace_id,
    actorId,
  );

  // platform_admin / tenant_admin can write; workspace_administrator has settings:write permission
  const canEdit = isPlatformAdmin || isTenantAdmin || can('settings:write');

  const queryKey = ['workspace-settings', workspace_id];

  const { data, isLoading, isError } = useQuery({
    queryKey,
    queryFn: () => getWorkspaceSettings(workspace_id!),
    staleTime: STALE_TIME,
    enabled: !!workspace_id,
  });

  const settings = data?.data;

  const invalidate = () => queryClient.invalidateQueries({ queryKey });

  // ---------------------------------------------------------------------------
  // Per-section save handlers
  // ---------------------------------------------------------------------------

  const handleSaveTimezone = async (update: TimezonePolicy) => {
    await updateWorkspaceSettings(workspace_id!, { timezone_policy: update });
    toast.success('Timezone updated.');
    await invalidate();
  };

  const handleSaveSeverity = async (update: SeverityPolicy) => {
    await updateWorkspaceSettings(workspace_id!, { severity_policy: update });
    toast.success('Severity labels updated.');
    await invalidate();
  };

  const handleSaveSla = async (update: SlaPolicy) => {
    await updateWorkspaceSettings(workspace_id!, { sla_policy: update });
    toast.success('SLA policy updated.');
    await invalidate();
  };

  const handleSaveGrouping = async (mode: IssueGroupingMode) => {
    await updateWorkspaceSettings(workspace_id!, { issue_grouping_policy: mode });
    toast.success('Issue grouping mode updated.');
    await invalidate();
  };

  const handleSaveDatasetsConstraint = async (update: NamingConstraint) => {
    await updateWorkspaceSettings(workspace_id!, {
      naming_standards: { datasets: update },
    });
    toast.success('Dataset naming standards updated.');
    await invalidate();
  };

  const handleSaveRulesConstraint = async (update: NamingConstraint) => {
    await updateWorkspaceSettings(workspace_id!, {
      naming_standards: { rules: update },
    });
    toast.success('Rule naming standards updated.');
    await invalidate();
  };

  const handleSaveLLMConfig = async (update: LLMConfigUpdate) => {
    await updateWorkspaceSettings(workspace_id!, { llm_config: update });
    toast.success('LLM configuration updated.');
    await invalidate();
  };

  const handleSaveIncidentPolicy = async (update: IncidentPolicy) => {
    await updateWorkspaceSettings(workspace_id!, { incident_policy: update });
    toast.success('Incident policy updated.');
    await invalidate();
  };

  // Gate access: after permissions finish loading, non-platform users need settings:read
  if (!permLoading && !isPlatformOperator && !isTenantAdmin && !can('settings:read')) {
    return <ForbiddenPage />;
  }

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse" data-testid="settings-loading">
        <div className="h-8 w-64 rounded-lg bg-dark-800" />
        <div className="h-32 rounded-2xl bg-dark-800/60" />
        <div className="h-32 rounded-2xl bg-dark-800/60" />
        <div className="h-32 rounded-2xl bg-dark-800/60" />
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Error state
  // ---------------------------------------------------------------------------

  if (isError || !settings) {
    return (
      <div data-testid="settings-error">
        <WorkspaceSettingsHeader workspaceId={workspace_id!} />
        <div
          role="alert"
          className="mt-4 flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400"
        >
          <AlertCircle className="w-5 h-5 shrink-0" aria-hidden="true" />
          <span>Failed to load settings. The workspace may not exist or you may not have access.</span>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Main render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6" data-testid="workspace-settings-page">
      <WorkspaceSettingsHeader workspaceId={workspace_id!} />

      <TimezoneSection
        value={settings.timezone_policy}
        canEdit={canEdit}
        onSave={handleSaveTimezone}
      />

      <SeverityPolicySection
        value={settings.severity_policy}
        canEdit={canEdit}
        onSave={handleSaveSeverity}
      />

      <SLAPolicySection
        value={settings.sla_policy}
        canEdit={canEdit}
        onSave={handleSaveSla}
      />

      <IssueGroupingSection
        value={settings.issue_grouping_policy}
        canEdit={canEdit}
        onSave={handleSaveGrouping}
      />

      <NamingStandardsSection
        value={settings.naming_standards}
        canEdit={canEdit}
        onSaveDatasetsConstraint={handleSaveDatasetsConstraint}
        onSaveRulesConstraint={handleSaveRulesConstraint}
      />

      <LLMConfigSection
        value={settings.llm_config}
        canEdit={canEdit}
        onSave={handleSaveLLMConfig}
      />

      <IncidentPolicySection
        value={settings.incident_policy}
        canEdit={canEdit}
        onSave={handleSaveIncidentPolicy}
      />

      <CostModelSection
        workspaceId={workspace_id!}
        canEdit={canEdit}
      />
    </div>
  );
}
