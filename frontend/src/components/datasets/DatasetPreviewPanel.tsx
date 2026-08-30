/**
 * F-CONN-P0 — Dataset Preview Panel
 *
 * Lazily fetches a sample of rows from the connector via
 * `GET /workspaces/{ws}/datasets/{ds}/preview` (see
 * `backend/app/api/v1/endpoints/datasets.py`) and renders them as a
 * read-only table.
 *
 * The fetch is opt-in: clicking "Load preview" mounts the React Query
 * subscription so the upstream data source is only contacted on demand.
 *
 * Spec §21.3 — Dataset detail Preview tab.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronUp } from 'lucide-react';

import {
  DATASET_PREVIEW_DEFAULT_ROWS,
  DATASET_PREVIEW_MAX_ROWS,
  DATASET_PREVIEW_MIN_ROWS,
  getDatasetPreview,
} from '../../services/datasetService';

interface DatasetPreviewPanelProps {
  workspaceId: string;
  datasetId: string;
}

const ROW_LIMIT_CHOICES = [50, 100, 250, 500, 1000].filter(
  (n) => n >= DATASET_PREVIEW_MIN_ROWS && n <= DATASET_PREVIEW_MAX_ROWS,
);

export default function DatasetPreviewPanel({
  workspaceId,
  datasetId,
}: DatasetPreviewPanelProps) {
  const [open, setOpen] = useState(false);
  const [limit, setLimit] = useState<number>(DATASET_PREVIEW_DEFAULT_ROWS);

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['dataset-preview', workspaceId, datasetId, limit],
    queryFn: () => getDatasetPreview(workspaceId, datasetId, limit),
    enabled: open,
    staleTime: 60_000,
    retry: false,
  });

  return (
    <div
      className="rounded-2xl border border-gray-700 bg-gray-800/60 overflow-hidden"
      data-testid="dataset-preview-panel"
    >
      <button
        type="button"
        data-testid="dataset-preview-toggle"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-3 text-sm font-medium text-gray-300 hover:bg-gray-700/30 transition-colors"
      >
        <span className="flex items-center gap-2">
          Preview
          <span className="text-xs text-gray-500">
            (live sample from data source)
          </span>
        </span>
        {open ? (
          <ChevronUp className="w-4 h-4" />
        ) : (
          <ChevronDown className="w-4 h-4" />
        )}
      </button>

      {open && (
        <div className="px-5 pb-4 space-y-3" data-testid="dataset-preview-body">
          <div className="flex items-center gap-3 text-sm">
            <label
              htmlFor="dataset-preview-limit"
              className="text-gray-400"
            >
              Rows
            </label>
            <select
              id="dataset-preview-limit"
              data-testid="dataset-preview-limit"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              disabled={isFetching}
              className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
            >
              {ROW_LIMIT_CHOICES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => refetch()}
              disabled={isFetching}
              data-testid="dataset-preview-refresh"
              className="px-3 py-1 text-sm border border-gray-600 rounded text-gray-300 hover:bg-gray-700 disabled:opacity-50"
            >
              {isFetching ? 'Loading…' : 'Refresh'}
            </button>
            {data && (
              <span
                className="text-xs text-gray-500"
                data-testid="dataset-preview-count"
              >
                {data.row_count} of up to {data.row_limit} rows
              </span>
            )}
          </div>

          {isLoading && (
            <p
              className="text-sm text-gray-400 py-4"
              data-testid="dataset-preview-loading"
            >
              Loading preview…
            </p>
          )}

          {isError && (
            <div
              role="alert"
              data-testid="dataset-preview-error"
              className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400"
            >
              Failed to load preview:{' '}
              {(error as Error)?.message ?? 'unknown error'}
            </div>
          )}

          {data && data.row_count === 0 && (
            <p
              className="text-sm text-gray-400 py-4"
              data-testid="dataset-preview-empty"
            >
              No rows returned.
            </p>
          )}

          {data && data.truncated_columns.length > 0 && (
            <p
              className="text-xs text-yellow-400"
              data-testid="dataset-preview-truncated-notice"
            >
              Long values truncated in:{' '}
              {data.truncated_columns.join(', ')}
            </p>
          )}

          {data && data.row_count > 0 && (
            <div
              className="overflow-x-auto"
              data-testid="dataset-preview-table-wrapper"
            >
              <table
                className="w-full text-sm border-collapse"
                data-testid="dataset-preview-table"
              >
                <thead>
                  <tr className="border-b border-gray-700">
                    {data.columns.map((col) => (
                      <th
                        key={col}
                        scope="col"
                        className="text-left px-3 py-2 text-gray-400 font-medium whitespace-nowrap"
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row, rowIdx) => (
                    <tr
                      key={rowIdx}
                      data-testid={`dataset-preview-row-${rowIdx}`}
                      className="border-b border-gray-700/50"
                    >
                      {data.columns.map((col) => (
                        <td
                          key={col}
                          className="px-3 py-1.5 text-gray-200 font-mono text-xs whitespace-pre-wrap break-words max-w-xs"
                        >
                          {formatCell(row[col])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '∅';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
