/**
 * ReferenceDataSection — Shown for subtypes that require a reference/target dataset
 * 
 * Renders:
 *  - DatasetPicker to choose the reference dataset
 *  - KeyPairTable for join-key mappings (source ↔ reference columns)
 *  - ColumnPicker for comparison columns (optional, when subtype provides them)
 *
 * Relevant subtypes: validity/reference_lookup, uniqueness/cross_dataset,
 * consistency/cross_table, accuracy/reference_comparison,
 * accuracy/trusted_source, accuracy/tolerated_deviation, reconciliation/*
 */
import { useQuery } from '@tanstack/react-query'
import { useWorkspace } from '../../../contexts/WorkspaceContext'
import { getDataset } from '../../../services/datasetService'
import { DatasetPicker, DatasetOption } from '../shared/DatasetPicker'
import { KeyPairTable, KeyPair } from '../shared/KeyPairTable'
import { ColumnPicker } from '../shared/ColumnPicker'
import type { BaseCheckConfig, ValidationError } from '../../../schemas/dq-checks/types'

interface ReferenceDataSectionProps {
  config: BaseCheckConfig & Record<string, unknown>
  onChange: (key: string, value: unknown) => void
  errors: ValidationError[]
  sourceColumns: string[]
  /** Datasets available for selection — parent provides from API or flow context */
  availableDatasets?: DatasetOption[]
  /** Columns available in the selected reference dataset */
  referenceColumns?: string[]
  /** Whether datasets are currently loading */
  loadingDatasets?: boolean
  /** Show a comparison-columns picker (e.g. accuracy subtypes) */
  showCompareColumns?: boolean
  /** Label for comparison columns picker */
  compareColumnsLabel?: string
}

export function ReferenceDataSection({
  config,
  onChange,
  errors,
  sourceColumns,
  availableDatasets = [],
  referenceColumns: referenceColumnsProp = [],
  loadingDatasets = false,
  showCompareColumns = false,
  compareColumnsLabel = 'Comparison Columns',
}: ReferenceDataSectionProps) {
  const hasError = (key: string) => errors.some(e => e.field === key)

  // Fetch columns of the selected reference dataset
  const { currentWorkspace } = useWorkspace()
  const selectedDatasetId = (config.reference_dataset as string) || null
  const { data: refDataset, isFetching: loadingRefCols } = useQuery({
    queryKey: ['dataset-detail', currentWorkspace?.workspace_id, selectedDatasetId],
    queryFn: () => getDataset(currentWorkspace!.workspace_id, selectedDatasetId!),
    enabled: !!currentWorkspace?.workspace_id && !!selectedDatasetId,
    staleTime: 60_000,
  })
  const referenceColumns: string[] =
    refDataset?.fields?.map((f) => f.field_name) ??
    referenceColumnsProp

  // ─── Join key pairs ───────────────────────────────────────────────
  const joinKeys: KeyPair[] = Array.isArray(config.join_keys) ? config.join_keys as KeyPair[] : [{ source: '', target: '' }]

  // ─── Compare columns (for accuracy subtypes) ────────────────────
  const compareColumns: string[] = Array.isArray(config.compare_columns) ? config.compare_columns as string[] : []

  return (
    <div className="space-y-4">
      <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Reference Data</h4>

      {/* Dataset picker */}
      <div className={hasError('reference_dataset') ? 'ring-1 ring-red-500/50 rounded' : ''}>
        <DatasetPicker
          datasets={availableDatasets}
          selected={(config.reference_dataset as string) || null}
          onChange={(id) => {
            onChange('reference_dataset', id || '')
            // Clear join keys when dataset changes
            onChange('join_keys', [{ source: '', target: '' }])
          }}
          label="Reference Dataset"
          loading={loadingDatasets}
        />
      </div>

      {/* Join key mapping */}
      <div className={hasError('join_keys') ? 'ring-1 ring-red-500/50 rounded p-1' : ''}>
        <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Join Keys {loadingRefCols && <span className="text-gray-600 normal-case font-normal">(loading columns…)</span>}
        </label>
        <KeyPairTable
          pairs={joinKeys}
          onChange={(pairs) => onChange('join_keys', pairs)}
          sourceColumns={sourceColumns}
          targetColumns={referenceColumns}
          sourceLabel="Source Column"
          targetLabel="Reference Column"
        />
      </div>

      {/* Comparison columns (optional) */}
      {showCompareColumns && (
        <div className={hasError('compare_columns') ? 'ring-1 ring-red-500/50 rounded' : ''}>
          <ColumnPicker
            columns={referenceColumns.length > 0 ? referenceColumns : sourceColumns}
            selected={compareColumns}
            onChange={(cols) => onChange('compare_columns', cols)}
            label={compareColumnsLabel}
            placeholder="Select columns to compare…"
          />
        </div>
      )}
    </div>
  )
}
