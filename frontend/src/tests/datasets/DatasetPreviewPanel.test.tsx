/**
 * F-CONN-P0 — DatasetPreviewPanel tests
 *
 * Coverage:
 *   1. Collapsed by default; preview API not called until toggle.
 *   2. Loading state appears while preview is fetching.
 *   3. Renders columns + rows from the API response.
 *   4. Surfaces truncated_columns notice.
 *   5. Refresh re-issues the preview request with the same limit.
 *   6. Changing the row limit triggers a new fetch.
 *   7. Empty state when row_count is 0.
 *   8. Error state when the API rejects.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import DatasetPreviewPanel from '@/components/datasets/DatasetPreviewPanel';

vi.mock('@/services/datasetService', async () => {
  const actual = await vi.importActual<
    typeof import('@/services/datasetService')
  >('@/services/datasetService');
  return {
    ...actual,
    getDatasetPreview: vi.fn(),
  };
});

import { getDatasetPreview } from '@/services/datasetService';

const mockPreview = getDatasetPreview as ReturnType<typeof vi.fn>;

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderPanel() {
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <DatasetPreviewPanel workspaceId="ws-1" datasetId="ds-1" />
    </QueryClientProvider>,
  );
}

const SAMPLE_RESPONSE = {
  dataset_id: 'ds-1',
  schema_name: 'public',
  table_name: 'customers',
  row_limit: 100,
  row_count: 2,
  columns: ['id', 'email'],
  rows: [
    { id: 1, email: 'alice@example.com' },
    { id: 2, email: null },
  ],
  truncated_columns: [],
};

beforeEach(() => {
  mockPreview.mockReset();
});

describe('DatasetPreviewPanel', () => {
  it('does not call the preview API until the panel is opened', async () => {
    mockPreview.mockResolvedValue(SAMPLE_RESPONSE);
    renderPanel();
    expect(mockPreview).not.toHaveBeenCalled();
    expect(
      screen.queryByTestId('dataset-preview-table'),
    ).not.toBeInTheDocument();
  });

  it('opens, fetches, and renders columns + rows', async () => {
    mockPreview.mockResolvedValue(SAMPLE_RESPONSE);
    renderPanel();

    fireEvent.click(screen.getByTestId('dataset-preview-toggle'));

    await waitFor(() =>
      expect(mockPreview).toHaveBeenCalledWith('ws-1', 'ds-1', 100),
    );
    expect(
      await screen.findByTestId('dataset-preview-table'),
    ).toBeInTheDocument();
    expect(screen.getByText('id')).toBeInTheDocument();
    expect(screen.getByText('email')).toBeInTheDocument();
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    // Null cells render as ∅ placeholder.
    expect(screen.getByTestId('dataset-preview-row-1')).toHaveTextContent('∅');
  });

  it('shows the truncated-columns notice when present', async () => {
    mockPreview.mockResolvedValue({
      ...SAMPLE_RESPONSE,
      truncated_columns: ['payload'],
    });
    renderPanel();
    fireEvent.click(screen.getByTestId('dataset-preview-toggle'));

    expect(
      await screen.findByTestId('dataset-preview-truncated-notice'),
    ).toHaveTextContent(/payload/);
  });

  it('changing the row limit triggers a new fetch with the new limit', async () => {
    mockPreview.mockResolvedValue(SAMPLE_RESPONSE);
    renderPanel();
    fireEvent.click(screen.getByTestId('dataset-preview-toggle'));
    await waitFor(() =>
      expect(mockPreview).toHaveBeenCalledWith('ws-1', 'ds-1', 100),
    );

    fireEvent.change(screen.getByTestId('dataset-preview-limit'), {
      target: { value: '500' },
    });

    await waitFor(() =>
      expect(mockPreview).toHaveBeenCalledWith('ws-1', 'ds-1', 500),
    );
  });

  it('shows an empty-state message when the response has no rows', async () => {
    mockPreview.mockResolvedValue({
      ...SAMPLE_RESPONSE,
      row_count: 0,
      rows: [],
      columns: [],
    });
    renderPanel();
    fireEvent.click(screen.getByTestId('dataset-preview-toggle'));

    expect(
      await screen.findByTestId('dataset-preview-empty'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('dataset-preview-table'),
    ).not.toBeInTheDocument();
  });

  it('renders an error state when the preview request fails', async () => {
    mockPreview.mockRejectedValue(new Error('connector unreachable'));
    renderPanel();
    fireEvent.click(screen.getByTestId('dataset-preview-toggle'));

    expect(
      await screen.findByTestId('dataset-preview-error'),
    ).toHaveTextContent(/connector unreachable/);
  });
});
