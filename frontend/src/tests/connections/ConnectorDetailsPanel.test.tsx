/**
 * F-CONN-UX — ConnectorDetailsPanel tests.
 *
 * Coverage:
 *   1. Empty state ("Pick a connector").
 *   2. Selected state shows display name, customer status badge,
 *      capabilities, requirements.
 *   3. Coming-soon spec hides Configure button and shows the
 *      details-coming-soon block.
 *   4. Configure button invokes onConfigure with the spec.
 *   5. adminMode={true} surfaces dev metadata.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import ConnectorDetailsPanel from '@/components/connections/ConnectorDetailsPanel';
import type { ConnectorSpec } from '@/services/connectorCatalogService';

function spec(
  partial: Partial<ConnectorSpec> & Pick<ConnectorSpec, 'type' | 'display_name'>,
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

const PG = spec({
  type: 'postgresql',
  display_name: 'PostgreSQL',
  description: 'Connect a PostgreSQL database to profile and test data.',
  credential_schema: [
    {
      name: 'host',
      type: 'string',
      label: 'Host',
      required: true,
      help_text: 'Server hostname or IP address.',
    },
    { name: 'port', type: 'number', label: 'Port', required: false },
  ],
});

const COMING_SOON = spec({
  type: 'csv',
  display_name: 'CSV File',
  category: 'file',
  status: 'deferred',
  deferred_reason: 'Coming after P0 file connectors.',
});

describe('ConnectorDetailsPanel', () => {
  it('renders empty state when no spec is selected', () => {
    render(<ConnectorDetailsPanel spec={null} onConfigure={vi.fn()} />);
    const panel = screen.getByTestId('connector-details-panel');
    expect(panel).toHaveAttribute('data-state', 'empty');
    expect(screen.getByText(/pick a connector/i)).toBeInTheDocument();
  });

  it('renders display name, status badge, capabilities and requirements', () => {
    render(<ConnectorDetailsPanel spec={PG} onConfigure={vi.fn()} />);
    expect(
      screen.getByTestId('connector-details-panel'),
    ).toHaveAttribute('data-state', 'selected');
    expect(screen.getByTestId('details-display-name')).toHaveTextContent(
      'PostgreSQL',
    );
    expect(screen.getByTestId('details-status-badge')).toHaveTextContent(
      /available/i,
    );
    expect(screen.getByTestId('details-capabilities')).toBeInTheDocument();
    expect(screen.getByTestId('details-capability-metadata')).toBeInTheDocument();
    expect(screen.getByTestId('details-capability-preview')).toBeInTheDocument();
    expect(
      screen.getByTestId('details-requirement-host'),
    ).toHaveTextContent(/server hostname/i);
  });

  it('hides Configure button and shows coming-soon block for deferred specs', () => {
    render(
      <ConnectorDetailsPanel spec={COMING_SOON} onConfigure={vi.fn()} />,
    );
    expect(screen.queryByTestId('details-configure-btn')).not.toBeInTheDocument();
    expect(screen.getByTestId('details-coming-soon')).toHaveTextContent(
      /coming after p0/i,
    );
  });

  it('Configure button invokes onConfigure with the spec', () => {
    const onConfigure = vi.fn();
    render(<ConnectorDetailsPanel spec={PG} onConfigure={onConfigure} />);
    fireEvent.click(screen.getByTestId('details-configure-btn'));
    expect(onConfigure).toHaveBeenCalledWith(PG);
  });

  it('adminMode surfaces engineering metadata', () => {
    render(
      <ConnectorDetailsPanel spec={PG} onConfigure={vi.fn()} adminMode />,
    );
    const block = screen.getByTestId('details-admin-metadata');
    expect(block).toHaveTextContent(/postgresql/i);
    expect(block).toHaveTextContent(/P0/);
  });
});
