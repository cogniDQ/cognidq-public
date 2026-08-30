/**
 * F130 — CreateConnectionPage
 *
 * Two-step registry-driven wizard at `/hub/connections/new`:
 *
 *   Step 1 — pick a connector via {@link ConnectorCatalog}.
 *   Step 2 — fill in the connector's `credential_schema` via
 *            {@link CredentialFormRenderer}, plus connection metadata
 *            (name / mode / environment / description). Validates
 *            client-side, then POSTs to `createConnection`.
 *
 * On success: redirects to `/hub/connections`.
 */
import { useMemo, useState } from 'react';
import { useNavigate, Link, useParams } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { ArrowLeft, Zap, CheckCircle2, XCircle, Loader2 } from 'lucide-react';

import ConnectorCatalog from '../../components/connections/ConnectorCatalog';
import ConnectorDetailsPanel from '../../components/connections/ConnectorDetailsPanel';
import RecommendedPaths from '../../components/connections/RecommendedPaths';
import CredentialFormRenderer, {
  validateCredentials,
} from '../../components/connections/CredentialFormRenderer';
import type {
  ConnectorSpec,
  CustomerGroup,
} from '../../services/connectorCatalogService';
import {
  createConnection,
  testConnectionConfig,
  type CreateConnectionPayload,
  type ConnectionEnvironment,
  type ConnectionMode,
  type ConnectionTestResult,
} from '../../services/connectionService';
import { getActorRole, getTenantId } from '../../utils/jwt';
import { useWorkspace } from '../../contexts/WorkspaceContext';

const ENVIRONMENTS: ConnectionEnvironment[] = [
  'development',
  'staging',
  'production',
];
const MODES: ConnectionMode[] = ['direct', 'agent'];

type WizardStep = 'pick' | 'configure';

export default function CreateConnectionPage() {
  const navigate = useNavigate();
  const { tenant_id: urlTenantId, workspace_id: urlWorkspaceId } = useParams<{ tenant_id?: string; workspace_id?: string }>();
  const token = localStorage.getItem('access_token');
  const { currentTenantId, currentWorkspace, workspaces } = useWorkspace();
  const tenantId = urlTenantId ?? currentTenantId ?? getTenantId(token);
  const connectionsBase = tenantId ? `/hub/t/${tenantId}/connections` : '/hub/connections';
  const actorRole = getActorRole(token);
  // Surface engineering metadata only for platform admins. Tenant admins
  // get the customer-facing onboarding catalog.
  const adminMode = actorRole === 'platform_admin';

  const [step, setStep] = useState<WizardStep>('pick');
  const [selected, setSelected] = useState<ConnectorSpec | null>(null);
  const [previewSpec, setPreviewSpec] = useState<ConnectorSpec | null>(null);
  const [groupFilter, setGroupFilter] = useState<CustomerGroup | null>(null);
  const [availableGroups, setAvailableGroups] = useState<CustomerGroup[]>([]);

  // Connection metadata (step 2 panel).
  const [name, setName] = useState('');
  const [connectionMode, setConnectionMode] =
    useState<ConnectionMode>('direct');
  const [environment, setEnvironment] =
    useState<ConnectionEnvironment>('development');
  const [description, setDescription] = useState('');

  // Tenant-level connections: the user grants access to one or more
  // workspaces. The schema requires a primary workspace_id (first entry of
  // selectedWorkspaceIds), and the full set is persisted via the workspace
  // assignments endpoint after creation.
  const initialWs = urlWorkspaceId ?? currentWorkspace?.workspace_id ?? '';
  const [selectedWorkspaceIds, setSelectedWorkspaceIds] = useState<string[]>(
    initialWs ? [initialWs] : [],
  );
  const primaryWorkspaceId = selectedWorkspaceIds[0] ?? '';
  const effectiveWorkspaceId = primaryWorkspaceId;

  // Connector-specific credentials (driven by spec.credential_schema).
  const [credentials, setCredentials] = useState<Record<string, unknown>>({});
  const [submitted, setSubmitted] = useState(false);

  const credentialErrors = useMemo(() => {
    if (!selected) return {};
    return validateCredentials(selected.credential_schema, credentials);
  }, [selected, credentials]);

  const { mutate, isPending, isError, error } = useMutation({
    mutationFn: async (payload: CreateConnectionPayload) => {
      // Tenant-scoped create persists the connection, encrypts credentials,
      // and writes workspace assignments in a single backend transaction.
      return await createConnection(tenantId!, payload);
    },
    onSuccess: () => navigate(connectionsBase),
  });

  const {
    mutate: runTest,
    isPending: isTesting,
    data: testResult,
    error: testError,
    reset: resetTest,
  } = useMutation({
    mutationFn: () =>
      testConnectionConfig(
        effectiveWorkspaceId,
        selected!.type,
        credentials,
      ),
  });

  // Reset test result whenever the user changes credentials.
  function handleCredentialChange(fieldName: string, value: unknown) {
    setCredentials((prev) => ({ ...prev, [fieldName]: value }));
    resetTest();
  }

  function handleSelectConnector(spec: ConnectorSpec) {
    setSelected(spec);
    // Seed credentials with declared defaults.
    const defaults: Record<string, unknown> = {};
    for (const field of spec.credential_schema) {
      if (field.default !== undefined) defaults[field.name] = field.default;
    }
    setCredentials(defaults);
    setSubmitted(false);
    setStep('configure');
  }

  // Step 1 — first click on a card just previews the details panel; the
  // user advances explicitly via the panel's "Configure connection" CTA.
  function handlePreviewConnector(spec: ConnectorSpec) {
    setPreviewSpec(spec);
  }

  function handlePickGroup(group: CustomerGroup) {
    setGroupFilter((current) => (current === group ? null : group));
  }

  function handleBackToCatalog() {
    setStep('pick');
    setSubmitted(false);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted(true);
    if (!selected) return;
    if (!name.trim()) return;
    if (!effectiveWorkspaceId) return;
    if (Object.keys(credentialErrors).length > 0) return;

    mutate({
      name: name.trim(),
      source_type: selected.type,
      connection_mode: connectionMode,
      environment,
      description: description.trim() || undefined,
      credentials,
      workspace_ids: selectedWorkspaceIds,
    });
  }

  return (
    <div className="p-6 space-y-6 w-full">
      <div className="flex items-center gap-3">
        <Link
          to={connectionsBase}
          className="text-gray-500 hover:text-gray-300 transition-colors"
          aria-label="Back to connections"
        >
          <ArrowLeft size={18} />
        </Link>
        <div>
          <h1 className="text-3xl font-bold gradient-text">Connect a data source</h1>
          <p className="text-gray-400 mt-1">Choose a source to profile datasets, generate rules, and run data quality checks.</p>
        </div>
      </div>

      <Stepper step={step} selected={selected} />

      {step === 'pick' ? (
        <div data-testid="wizard-step-pick" className="space-y-4">
          <RecommendedPaths
            availableGroups={availableGroups}
            onPick={handlePickGroup}
            activeGroup={groupFilter}
          />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
            <div className="lg:col-span-2 rounded-xl border border-dark-700 bg-dark-900 overflow-hidden">
              <ConnectorCatalog
                onSelect={handlePreviewConnector}
                selectedType={previewSpec?.type ?? selected?.type}
                adminMode={adminMode}
                groupFilter={groupFilter}
                onGroupsAvailable={setAvailableGroups}
              />
            </div>
            <div className="lg:col-span-1">
              <ConnectorDetailsPanel
                spec={previewSpec}
                onConfigure={handleSelectConnector}
                adminMode={adminMode}
              />
            </div>
          </div>
        </div>
      ) : (
        <ConfigureStep
          spec={selected!}
          name={name}
          setName={setName}
          connectionMode={connectionMode}
          setConnectionMode={setConnectionMode}
          environment={environment}
          setEnvironment={setEnvironment}
          description={description}
          setDescription={setDescription}
          workspaces={workspaces}
          selectedWorkspaceIds={selectedWorkspaceIds}
          setSelectedWorkspaceIds={setSelectedWorkspaceIds}
          credentials={credentials}
          credentialErrors={submitted ? credentialErrors : {}}
          onCredentialChange={handleCredentialChange}
          onBack={handleBackToCatalog}
          onSubmit={handleSubmit}
          submitting={isPending}
          isError={isError}
          error={error as Error | null}
          submitted={submitted}
          onTest={() => runTest()}
          isTesting={isTesting}
          testResult={testResult ?? null}
          testError={testError as Error | null}
        />
      )}
    </div>
  );
}

// ─── Step 1/2 indicator ───────────────────────────────────────────────────

interface StepperProps {
  step: WizardStep;
  selected: ConnectorSpec | null;
}

function Stepper({ step, selected }: StepperProps) {
  return (
    <ol
      className="flex items-center gap-2 text-sm"
      data-testid="wizard-stepper"
    >
      <li
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ${
          step === 'pick'
            ? 'bg-primary-600/20 text-primary-400 border border-primary-700'
            : 'text-gray-500 border border-dark-700'
        }`}
        data-testid="wizard-step-1"
      >
        <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${step === 'pick' ? 'bg-primary-600 text-white' : 'bg-dark-700 text-gray-400'}`}>1</span>
        Choose connector
        {selected && (
          <span className="ml-1 text-gray-500 font-normal">({selected.display_name})</span>
        )}
      </li>
      <li className="text-dark-600">›</li>
      <li
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ${
          step === 'configure'
            ? 'bg-primary-600/20 text-primary-400 border border-primary-700'
            : 'text-gray-500 border border-dark-700'
        }`}
        data-testid="wizard-step-2"
      >
        <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${step === 'configure' ? 'bg-primary-600 text-white' : 'bg-dark-700 text-gray-400'}`}>2</span>
        Configure
      </li>
    </ol>
  );
}

// ─── Step 2 form ──────────────────────────────────────────────────────────

interface ConfigureStepProps {
  spec: ConnectorSpec;
  name: string;
  setName: (v: string) => void;
  connectionMode: ConnectionMode;
  setConnectionMode: (v: ConnectionMode) => void;
  environment: ConnectionEnvironment;
  setEnvironment: (v: ConnectionEnvironment) => void;
  description: string;
  setDescription: (v: string) => void;
  workspaces: { workspace_id: string; workspace_name: string }[];
  selectedWorkspaceIds: string[];
  setSelectedWorkspaceIds: (v: string[]) => void;
  credentials: Record<string, unknown>;
  credentialErrors: Record<string, string>;
  onCredentialChange: (name: string, value: unknown) => void;
  onBack: () => void;
  onSubmit: (e: React.FormEvent) => void;
  submitting: boolean;
  isError: boolean;
  error: Error | null;
  submitted: boolean;
  onTest: () => void;
  isTesting: boolean;
  testResult: ConnectionTestResult | null;
  testError: Error | null;
}

function ConfigureStep({
  spec,
  name,
  setName,
  connectionMode,
  setConnectionMode,
  environment,
  setEnvironment,
  description,
  setDescription,
  workspaces,
  selectedWorkspaceIds,
  setSelectedWorkspaceIds,
  credentials,
  credentialErrors,
  onCredentialChange,
  onBack,
  onSubmit,
  submitting,
  isError,
  error,
  submitted,
  onTest,
  isTesting,
  testResult,
  testError,
}: ConfigureStepProps) {
  const nameMissing = submitted && !name.trim();
  const workspaceMissing = submitted && selectedWorkspaceIds.length === 0;
  const primaryWorkspaceId = selectedWorkspaceIds[0] ?? '';

  function toggleWorkspace(wid: string) {
    if (selectedWorkspaceIds.includes(wid)) {
      setSelectedWorkspaceIds(selectedWorkspaceIds.filter((x) => x !== wid));
    } else {
      setSelectedWorkspaceIds([...selectedWorkspaceIds, wid]);
    }
  }
  return (
    <form
      onSubmit={onSubmit}
      className="space-y-6 w-full"
      data-testid="create-connection-form"
    >
      {/* Selected connector summary */}
      <div className="flex items-center justify-between p-4 rounded-xl bg-dark-800 border border-dark-700">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-0.5">Selected Connector</p>
          <p className="font-semibold text-gray-100" data-testid="selected-connector">
            {spec.display_name}{' '}
            <span className="text-gray-500 text-xs font-mono">({spec.type})</span>
          </p>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="text-sm text-primary-400 hover:text-primary-300"
          data-testid="change-connector-btn"
        >
          Change
        </button>
      </div>

      {isError && (
        <div className="p-4 rounded-lg bg-red-900/20 border border-red-800 text-red-400 text-sm" data-testid="create-error">
          {error?.message ?? 'Failed to create connection.'}
        </div>
      )}

      <div className="card space-y-5">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">Connection Details</h2>

        <div>
          <label className="block text-sm font-medium text-gray-400 mb-1.5">
            Name<span className="ml-1 text-red-400">*</span>
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={`input ${nameMissing ? 'border-red-600 focus:ring-red-500' : ''}`}
            data-testid="field-name"
          />
          {nameMissing && (
            <p className="mt-1 text-xs text-red-400" data-testid="field-name-error">Name is required</p>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1.5">Mode</label>
            <select
              value={connectionMode}
              onChange={(e) => setConnectionMode(e.target.value as ConnectionMode)}
              className="input"
              data-testid="field-mode"
            >
              {MODES.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1.5">Environment</label>
            <select
              value={environment}
              onChange={(e) => setEnvironment(e.target.value as ConnectionEnvironment)}
              className="input"
              data-testid="field-environment"
            >
              {ENVIRONMENTS.map((env) => (
                <option key={env} value={env}>{env}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-400 mb-1.5">
            Grant access to workspaces<span className="ml-1 text-red-400">*</span>
          </label>
          <p className="text-xs text-gray-500 mb-2">
            Select one or more workspaces that will be able to use this connection.
            The first selected workspace becomes the primary owner; you can adjust assignments anytime from the connection's detail page.
          </p>
          {workspaces.length === 0 ? (
            <p className="text-xs text-gray-500 italic" data-testid="no-workspaces">No workspaces available.</p>
          ) : (
            <div
              className={`space-y-1.5 max-h-56 overflow-y-auto rounded-lg border ${workspaceMissing ? 'border-red-600' : 'border-dark-700'} bg-dark-800 p-3`}
              data-testid="field-workspaces"
            >
              {workspaces.map((ws) => {
                const checked = selectedWorkspaceIds.includes(ws.workspace_id);
                const isPrimary = primaryWorkspaceId === ws.workspace_id;
                return (
                  <label
                    key={ws.workspace_id}
                    className="flex items-center gap-2 text-sm text-gray-200 cursor-pointer hover:bg-dark-700/60 rounded px-2 py-1"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleWorkspace(ws.workspace_id)}
                      className="w-4 h-4 accent-primary-500"
                      data-testid={`workspace-checkbox-${ws.workspace_id}`}
                    />
                    <span className="flex-1">{ws.workspace_name}</span>
                    {isPrimary && (
                      <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-primary-600/20 text-primary-300 border border-primary-700">
                        Primary
                      </span>
                    )}
                  </label>
                );
              })}
            </div>
          )}
          {workspaceMissing && (
            <p className="mt-1 text-xs text-red-400" data-testid="field-workspace-error">Select at least one workspace</p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-400 mb-1.5">Description</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            className="textarea"
            data-testid="field-description"
          />
        </div>
      </div>

      <div className="card space-y-4">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">Credentials</h2>
        {spec.credential_schema.length === 0 ? (
          <p className="text-sm text-gray-500" data-testid="no-credentials">
            This connector has no credential fields.
          </p>
        ) : (
          <CredentialFormRenderer
            fields={spec.credential_schema}
            values={credentials}
            onChange={onCredentialChange}
            errors={credentialErrors}
            disabled={submitting}
          />
        )}
      </div>

      {/* Test before create */}
      {spec.credential_schema.length > 0 && (
        <div className="space-y-3">
          <button
            type="button"
            onClick={onTest}
            disabled={isTesting || submitting || !primaryWorkspaceId}
            className="btn btn-secondary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            data-testid="test-config-btn"
            title={!primaryWorkspaceId ? 'Select at least one workspace before testing the connection' : undefined}
          >
            {isTesting ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Zap size={14} />
            )}
            {isTesting ? 'Testing…' : 'Test Connection'}
          </button>
          {!primaryWorkspaceId && (
            <p className="text-xs text-gray-500" data-testid="test-config-hint">
              Select at least one workspace above before testing the connection.
            </p>
          )}

          {testResult && (
            <div
              className={`flex items-start gap-2 p-3 rounded-lg text-sm border ${
                testResult.success
                  ? 'bg-green-900/20 border-green-800/60 text-green-400'
                  : 'bg-red-900/20 border-red-800/60 text-red-400'
              }`}
              data-testid="test-config-result"
            >
              {testResult.success ? (
                <CheckCircle2 size={15} className="mt-0.5 flex-shrink-0" />
              ) : (
                <XCircle size={15} className="mt-0.5 flex-shrink-0" />
              )}
              <span>
                {testResult.message}
                {testResult.success && testResult.latency_ms != null && (
                  <span className="ml-1 opacity-60 text-xs">({testResult.latency_ms}ms)</span>
                )}
              </span>
            </div>
          )}

          {testError && !testResult && (
            <div
              className="flex items-start gap-2 p-3 rounded-lg text-sm border bg-red-900/20 border-red-800/60 text-red-400"
              data-testid="test-config-error"
            >
              <XCircle size={15} className="mt-0.5 flex-shrink-0" />
              <span>{(testError as Error).message ?? 'Connection test failed.'}</span>
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onBack}
          className="btn btn-secondary"
          data-testid="back-btn"
        >
          Back
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="btn btn-primary disabled:opacity-50"
          data-testid="submit-btn"
        >
          {submitting ? 'Creating…' : 'Create Connection'}
        </button>
      </div>
    </form>
  );
}
