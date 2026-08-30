/**
 * F-CONN-UX — ConnectorCatalog component tests.
 *
 * Coverage:
 *   1. Loading state.
 *   2. Renders categorised cards from registry payload.
 *   3. Search filter narrows results.
 *   4. Status filter narrows results.
 *   5. Deferred connector cards are disabled (cannot be selected).
 *   6. Click on a ready card invokes onSelect with the spec.
 *   7. Error state.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import ConnectorCatalog from '@/components/connections/ConnectorCatalog';
import type { ConnectorSpec } from '@/services/connectorCatalogService';

vi.mock('@/services/connectorCatalogService', async () => {
  const actual = await vi.importActual<typeof import('@/services/connectorCatalogService')>(
    '@/services/connectorCatalogService',
  );
  return {
    ...actual,
    listConnectors: vi.fn(),
  };
});

import { listConnectors } from '@/services/connectorCatalogService';

const mockList = listConnectors as ReturnType<typeof vi.fn>;

function spec(partial: Partial<ConnectorSpec> & Pick<ConnectorSpec, 'type' | 'display_name'>): ConnectorSpec {
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

const SPECS: ConnectorSpec[] = [
  spec({ type: 'postgresql', display_name: 'PostgreSQL', status: 'ready' }),
  spec({
    type: 'snowflake',
    display_name: 'Snowflake',
    category: 'warehouse',
    status: 'integration_ready',
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
      requires_external_credentials: true,
      local_test_available: false,
    },
  }),
  spec({
    type: 'csv',
    display_name: 'CSV File',
    category: 'file',
    status: 'deferred',
    deferred_reason: 'Coming after P0 file connectors',
  }),
];

function renderCatalog(onSelect = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    onSelect,
    ...render(
      <QueryClientProvider client={qc}>
        <ConnectorCatalog onSelect={onSelect} />
      </QueryClientProvider>,
    ),
  };
}

describe('ConnectorCatalog', () => {
  beforeEach(() => {
    mockList.mockReset();
  });

  it('shows loading then renders connector cards grouped by category', async () => {
    mockList.mockResolvedValue({ items: SPECS, total: SPECS.length });
    renderCatalog();

    expect(screen.getByTestId('catalog-loading')).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.getByTestId('connector-card-postgresql')).toBeInTheDocument(),
    );

    expect(screen.getByTestId('catalog-group-connect_database')).toBeInTheDocument();
    expect(screen.getByTestId('catalog-group-enterprise_warehouse')).toBeInTheDocument();
    expect(screen.getByTestId('catalog-group-start_fast')).toBeInTheDocument();
  });

  it('search input filters cards by display name', async () => {
    mockList.mockResolvedValue({ items: SPECS, total: SPECS.length });
    renderCatalog();
    await screen.findByTestId('connector-card-postgresql');

    fireEvent.change(screen.getByTestId('catalog-search'), {
      target: { value: 'snow' },
    });

    expect(screen.queryByTestId('connector-card-postgresql')).not.toBeInTheDocument();
    expect(screen.getByTestId('connector-card-snowflake')).toBeInTheDocument();
  });

  it('status filter narrows to a single status bucket', async () => {
    mockList.mockResolvedValue({ items: SPECS, total: SPECS.length });
    renderCatalog();
    await screen.findByTestId('connector-card-postgresql');

    fireEvent.change(screen.getByTestId('catalog-status-filter'), {
      target: { value: 'available' },
    });

    expect(screen.getByTestId('connector-card-postgresql')).toBeInTheDocument();
    expect(screen.queryByTestId('connector-card-snowflake')).not.toBeInTheDocument();
    expect(screen.queryByTestId('connector-card-csv')).not.toBeInTheDocument();
  });

  it('deferred cards are disabled and clicking them does not select', async () => {
    const { onSelect } = renderCatalogReady();
    await screen.findByTestId('connector-card-csv');

    const card = screen.getByTestId('connector-card-csv') as HTMLButtonElement;
    expect(card).toBeDisabled();

    fireEvent.click(card);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('click on a ready card invokes onSelect with the full spec', async () => {
    const { onSelect } = renderCatalogReady();
    await screen.findByTestId('connector-card-postgresql');

    fireEvent.click(screen.getByTestId('connector-card-postgresql'));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0].type).toBe('postgresql');
  });

  it('renders error state when fetch fails', async () => {
    mockList.mockRejectedValue(new Error('boom'));
    renderCatalog();
    await waitFor(() =>
      expect(screen.getByTestId('catalog-error')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('catalog-error')).toHaveTextContent('boom');
  });
});

function renderCatalogReady() {
  mockList.mockResolvedValue({ items: SPECS, total: SPECS.length });
  return renderCatalog();
}
