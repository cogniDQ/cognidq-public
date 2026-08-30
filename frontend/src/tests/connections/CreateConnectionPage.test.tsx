/**
 * F130 — CreateConnectionPage tests
 *
 * Coverage:
 *   1. Renders connector catalog (step 1).
 *   2. Selecting a connector advances to the configure step and renders
 *      the credential schema for that connector.
 *   3. Submitting calls createConnection with the registry-driven
 *      payload (source_type from the picked spec, credentials from the
 *      schema-driven inputs).
 *   4. Success redirects to /hub/connections.
 *   5. Submitting with missing required credential field shows a
 *      schema-driven validation error and does NOT call createConnection.
 *   6. Back button returns to the catalog step.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import CreateConnectionPage from '@/pages/connections/CreateConnectionPage';
import type { ConnectorSpec } from '@/services/connectorCatalogService';

// ── Mocks ──────────────────────────────────────────────────────────────────
vi.mock('@/services/connectionService', () => ({
  createConnection: vi.fn(),
}));

vi.mock('@/utils/jwt', () => ({
  getTenantId: vi.fn(),
  getActorRole: vi.fn(),
}));

vi.mock('@/contexts/WorkspaceContext', () => ({
  useWorkspace: vi.fn(() => ({
    currentTenantId: 'tenant-123',
    currentWorkspace: { workspace_id: 'ws-1', workspace_name: 'Alpha' },
    workspaces: [{ workspace_id: 'ws-1', workspace_name: 'Alpha' }],
  })),
}));

vi.mock('@/services/connectorCatalogService', async () => {
  const actual = await vi.importActual<
    typeof import('@/services/connectorCatalogService')
  >('@/services/connectorCatalogService');
  return {
    ...actual,
    listConnectors: vi.fn(),
  };
});

import { createConnection } from '@/services/connectionService';
import { getTenantId, getActorRole } from '@/utils/jwt';
import { listConnectors } from '@/services/connectorCatalogService';

const mockCreateConnection = createConnection as ReturnType<typeof vi.fn>;
const mockGetTenantId = getTenantId as ReturnType<typeof vi.fn>;
const mockGetActorRole = getActorRole as ReturnType<typeof vi.fn>;
const mockListConnectors = listConnectors as ReturnType<typeof vi.fn>;

// ── Fixtures ───────────────────────────────────────────────────────────────
function spec(
  partial: Partial<ConnectorSpec> &
    Pick<ConnectorSpec, 'type' | 'display_name'>,
): ConnectorSpec {
  return {
    description: 'A connector',
    category: 'database',
    priority: 'P0',
    status: 'ready',
    capabilities: {
      supports_connection_test: true,
      supports_metadata_discovery: true,
      supports_schema_discovery: true,
      supports_table_discovery: true,
      supports_file_discovery: false,
      supports_dataset_preview: true,
      supports_check_execution: true,
      supports_sampling: true,
      supports_pushdown_sql: true,
      supports_parquet: false,
      requires_external_credentials: false,
      local_test_available: true,
    },
    credential_schema: [],
    ...partial,
  };
}

const POSTGRES_SPEC: ConnectorSpec = spec({
  type: 'postgresql',
  display_name: 'PostgreSQL',
  credential_schema: [
    { name: 'host', type: 'string', label: 'Host', required: true },
    {
      name: 'port',
      type: 'number',
      label: 'Port',
      required: true,
      default: 5432,
    },
    { name: 'database', type: 'string', label: 'Database', required: true },
    { name: 'username', type: 'string', label: 'Username', required: true },
    { name: 'password', type: 'secret', label: 'Password', required: true },
    { name: 'sslmode', type: 'string', label: 'SSL mode', required: false },
  ],
});

const SPECS: ConnectorSpec[] = [POSTGRES_SPEC];

// ── Render helper ──────────────────────────────────────────────────────────
function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderPage() {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/hub/connections/new']}>
        <Routes>
          <Route
            path="/hub/connections/new"
            element={<CreateConnectionPage />}
          />
          <Route
            path="/hub/connections"
            element={
              <div data-testid="connections-list-page">Connections</div>
            }
          />
          <Route
            path="/hub/t/:tenant_id/connections"
            element={
              <div data-testid="connections-list-page">Connections</div>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function pickPostgres() {
  const card = await screen.findByTestId('connector-card-postgresql');
  fireEvent.click(card);
  // First click only previews the details panel; configure CTA advances.
  const configureBtn = await screen.findByTestId('details-configure-btn');
  fireEvent.click(configureBtn);
  await screen.findByTestId('create-connection-form');
}

// ── Tests ──────────────────────────────────────────────────────────────────
describe('CreateConnectionPage', () => {
  beforeEach(() => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('mock_token');
    mockGetTenantId.mockReturnValue('tenant-123');
    mockGetActorRole.mockReturnValue('tenant_admin');
    mockListConnectors.mockResolvedValue({ items: SPECS, total: SPECS.length });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    mockCreateConnection.mockReset();
    mockListConnectors.mockReset();
  });

  it('renders the connector catalog as step 1', async () => {
    renderPage();
    expect(await screen.findByTestId('wizard-step-1')).toBeInTheDocument();
    expect(await screen.findByTestId('connector-catalog')).toBeInTheDocument();
    expect(
      await screen.findByTestId('connector-card-postgresql'),
    ).toBeInTheDocument();
  });

  it('selecting a connector advances to step 2 with its credential schema', async () => {
    renderPage();
    await pickPostgres();
    expect(screen.getByTestId('selected-connector')).toHaveTextContent(
      /PostgreSQL/,
    );
    expect(screen.getByTestId('credential-row-host')).toBeInTheDocument();
    expect(screen.getByTestId('credential-row-port')).toBeInTheDocument();
    expect(screen.getByTestId('credential-row-password')).toBeInTheDocument();
  });

  it('back button returns to the catalog step', async () => {
    renderPage();
    await pickPostgres();
    fireEvent.click(screen.getByTestId('back-btn'));
    expect(await screen.findByTestId('connector-catalog')).toBeInTheDocument();
    expect(
      screen.queryByTestId('create-connection-form'),
    ).not.toBeInTheDocument();
  });

  it('submitting with missing required credentials shows validation errors and does not call API', async () => {
    renderPage();
    await pickPostgres();

    fireEvent.change(screen.getByTestId('field-name'), {
      target: { value: 'My DB' },
    });
    // Leave host/database/username/password empty.

    fireEvent.submit(screen.getByTestId('create-connection-form'));

    expect(await screen.findByTestId('credential-error-host')).toHaveTextContent(
      /required/i,
    );
    expect(mockCreateConnection).not.toHaveBeenCalled();
  });

  it('form submit calls createConnection with registry-driven payload', async () => {
    mockCreateConnection.mockResolvedValue({
      connection_id: 'new-conn',
      tenant_id: 'tenant-123',
      name: 'My DB',
      source_type: 'postgresql',
      connection_mode: 'read_only',
      environment: 'development',
      status: 'active',
      description: null,
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T00:00:00Z',
    });

    renderPage();
    await pickPostgres();

    fireEvent.change(screen.getByTestId('field-name'), {
      target: { value: 'My DB' },
    });
    fireEvent.change(screen.getByTestId('credential-input-host'), {
      target: { value: 'db.example.com' },
    });
    fireEvent.change(screen.getByTestId('credential-input-database'), {
      target: { value: 'app' },
    });
    fireEvent.change(screen.getByTestId('credential-input-username'), {
      target: { value: 'admin' },
    });
    fireEvent.change(screen.getByTestId('credential-input-password'), {
      target: { value: 's3cret' },
    });
    // Leave port at the default (5432).

    fireEvent.submit(screen.getByTestId('create-connection-form'));

    await waitFor(() => {
      expect(mockCreateConnection).toHaveBeenCalledTimes(1);
    });
    const [tenantArg, payload] = mockCreateConnection.mock.calls[0];
    expect(tenantArg).toBe('tenant-123');
    expect(payload).toMatchObject({
      name: 'My DB',
      source_type: 'postgresql',
      connection_mode: 'direct',
      environment: 'development',
    });
    expect(payload.credentials).toMatchObject({
      host: 'db.example.com',
      port: 5432,
      database: 'app',
      username: 'admin',
      password: 's3cret',
    });
  });

  it('redirects to /hub/connections on successful creation', async () => {
    mockCreateConnection.mockResolvedValue({
      connection_id: 'new-conn',
      tenant_id: 'tenant-123',
      name: 'My DB',
      source_type: 'postgresql',
      connection_mode: 'read_only',
      environment: 'development',
      status: 'active',
      description: null,
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T00:00:00Z',
    });

    renderPage();
    await pickPostgres();

    fireEvent.change(screen.getByTestId('field-name'), {
      target: { value: 'My DB' },
    });
    fireEvent.change(screen.getByTestId('credential-input-host'), {
      target: { value: 'db.example.com' },
    });
    fireEvent.change(screen.getByTestId('credential-input-database'), {
      target: { value: 'app' },
    });
    fireEvent.change(screen.getByTestId('credential-input-username'), {
      target: { value: 'admin' },
    });
    fireEvent.change(screen.getByTestId('credential-input-password'), {
      target: { value: 's3cret' },
    });

    fireEvent.submit(screen.getByTestId('create-connection-form'));

    await waitFor(() => {
      expect(screen.getByTestId('connections-list-page')).toBeInTheDocument();
    });
  });
});
