/**
 * Dataset Configuration Panel — replaces DataSourceConfigPanel.
 *
 * Lets the user pick one of the active F005 datasets for a source node.
 */
import { useState, useEffect } from 'react'
import { X, Database, Table, Columns, Search, Edit2, Loader2 } from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { listDatasets, listFields, getDataset } from '../../services/datasetService'
import type { DatasetListItem, DatasetField } from '../../types/dataset'
import type { FlowNode } from './types'

interface DatasetConfigPanelProps {
  node: FlowNode
  onClose: () => void
  onSave: (config: any) => void
}

export function DatasetConfigPanel({ node, onClose, onSave }: DatasetConfigPanelProps) {
  const { currentWorkspace } = useWorkspace()

  const [datasets, setDatasets] = useState<DatasetListItem[]>([])
  const [loading, setLoading] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [isEditing, setIsEditing] = useState(!node.config?.dataset_id)
  const [selectedDataset, setSelectedDataset] = useState<DatasetListItem | null>(null)
  const [fields, setFields] = useState<DatasetField[]>([])
  const [loadingFields, setLoadingFields] = useState(false)
  const [schemaName, setSchemaName] = useState<string>(node.config?.schema_name || 'public')

  // Fetch active datasets on mount / workspace change
  useEffect(() => {
    if (!currentWorkspace) return
    setLoading(true)
    listDatasets(currentWorkspace.workspace_id, { status: 'active', page_size: 100 })
      .then(res => setDatasets(res.items ?? []))
      .catch(() => setDatasets([]))
      .finally(() => setLoading(false))
  }, [currentWorkspace])

  // If node already has a dataset configured, load its fields for the view mode
  useEffect(() => {
    if (!currentWorkspace || !node.config?.dataset_id) return
    setLoadingFields(true)
    listFields(currentWorkspace.workspace_id, node.config.dataset_id)
      .then(setFields)
      .catch(() => setFields([]))
      .finally(() => setLoadingFields(false))
  }, [currentWorkspace, node.config?.dataset_id])

  // When user picks a dataset, load its fields and full detail for schema_name
  useEffect(() => {
    if (!currentWorkspace || !selectedDataset) return
    setLoadingFields(true)
    Promise.all([
      listFields(currentWorkspace.workspace_id, selectedDataset.dataset_id),
      getDataset(currentWorkspace.workspace_id, selectedDataset.dataset_id),
    ])
      .then(([fieldList, detail]) => {
        setFields(fieldList)
        setSchemaName(detail.schema_name || 'public')
      })
      .catch(() => { setFields([]); setSchemaName('public') })
      .finally(() => setLoadingFields(false))
  }, [currentWorkspace, selectedDataset])

  const filtered = datasets.filter(d => {
    const q = searchTerm.toLowerCase()
    return (
      d.dataset_name.toLowerCase().includes(q) ||
      (d.physical_identifier ?? '').toLowerCase().includes(q) ||
      (d.data_source_name ?? '').toLowerCase().includes(q) ||
      (d.business_domain ?? '').toLowerCase().includes(q)
    )
  })

  const handleSave = () => {
    const ds = selectedDataset
    if (!ds) return
    onSave({
      dataset_id: ds.dataset_id,
      dataset_name: ds.dataset_name,
      data_source_id: ds.data_source_id,
      data_source_name: ds.data_source_name,
      physical_identifier: ds.physical_identifier,
      dataset_type: ds.dataset_type,
      field_count: ds.field_count,
      // Backend source node handler requires these for DB execution
      schema_name: schemaName,
      table_name: ds.physical_identifier,
      // Keep columns list for check nodes to consume
      metadata: {
        columns: fields.map(f => ({
          column_name: f.field_name,
          data_type: f.data_type,
          nullable: f.nullable,
        })),
      },
    })
    setIsEditing(false)
    onClose()
  }

  const config = node.config || {}
  const viewColumns: any[] = config.metadata?.columns ?? fields.map(f => ({ column_name: f.field_name, data_type: f.data_type }))

  return (
    <div className="absolute right-0 top-0 bottom-0 w-96 glass border-l border-dark-700 flex flex-col z-50">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-dark-700">
        <div>
          <h3 className="text-lg font-semibold text-white">Dataset</h3>
          <p className="text-xs text-gray-400">{node.name || 'Configure dataset'}</p>
        </div>
        <div className="flex items-center space-x-2">
          {!isEditing && (
            <button onClick={() => setIsEditing(true)} className="p-2 hover:bg-dark-700 rounded-lg text-primary-400" title="Change dataset">
              <Edit2 className="w-4 h-4" />
            </button>
          )}
          <button onClick={onClose} className="p-2 hover:bg-dark-700 rounded-lg">
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {isEditing ? (
          <>
            {/* Search */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Select Active Dataset</label>
              <div className="relative mb-3">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input
                  type="text"
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                  placeholder="Search datasets…"
                  className="w-full pl-10 pr-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-sm text-gray-200 focus:outline-none focus:border-primary-500"
                />
              </div>

              {/* Dataset list */}
              <div className="space-y-2 max-h-96 overflow-y-auto bg-dark-900/50 border border-dark-700 rounded-lg p-2">
                {loading ? (
                  <div className="flex items-center justify-center py-8 text-gray-400 text-sm">
                    <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading datasets…
                  </div>
                ) : filtered.length > 0 ? (
                  filtered.map(ds => {
                    const isSelected = selectedDataset?.dataset_id === ds.dataset_id || (!selectedDataset && config.dataset_id === ds.dataset_id)
                    return (
                      <button
                        key={ds.dataset_id}
                        onClick={() => setSelectedDataset(ds)}
                        className={`w-full text-left p-3 rounded-lg transition-all ${
                          isSelected
                            ? 'bg-primary-500/20 border border-primary-500/50'
                            : 'bg-dark-800 hover:bg-dark-700 border border-dark-700'
                        }`}
                      >
                        <div className="flex items-start space-x-2">
                          <Database className="w-4 h-4 text-primary-400 flex-shrink-0 mt-0.5" />
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-white text-sm truncate">{ds.dataset_name}</p>
                            <p className="text-xs text-gray-500 truncate">
                              {ds.physical_identifier}
                              {ds.data_source_name && ` · ${ds.data_source_name}`}
                            </p>
                            <p className="text-xs text-gray-600 mt-0.5">
                              {ds.field_count} fields · {ds.dataset_type}
                            </p>
                          </div>
                        </div>
                      </button>
                    )
                  })
                ) : (
                  <div className="text-center py-8 text-gray-500 text-sm">
                    {searchTerm ? 'No datasets match your search' : 'No active datasets available'}
                  </div>
                )}
              </div>
            </div>

            {/* Preview of selected dataset */}
            {selectedDataset && (
              <div className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
                <p className="text-xs font-medium text-blue-400 mb-1">Selected:</p>
                <p className="text-sm text-white">{selectedDataset.dataset_name}</p>
                <p className="text-xs text-gray-500 mt-1">{selectedDataset.physical_identifier}</p>
                {loadingFields && <p className="text-xs text-gray-500 mt-1">Loading fields…</p>}
                {!loadingFields && fields.length > 0 && (
                  <p className="text-xs text-gray-500 mt-1">{fields.length} fields available</p>
                )}
              </div>
            )}
          </>
        ) : (
          /* View mode — show configured dataset info */
          config.dataset_id ? (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  <Database className="w-4 h-4 inline mr-1" />
                  Dataset Name
                </label>
                <div className="bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200">
                  {config.dataset_name || config.physical_identifier}
                </div>
              </div>
              {config.physical_identifier && (
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">Physical Identifier</label>
                  <div className="bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200">
                    {config.physical_identifier}
                  </div>
                </div>
              )}
              {config.data_source_name && (
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">Data Source</label>
                  <div className="bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200">
                    {config.data_source_name}
                  </div>
                </div>
              )}
              {/* Columns / fields */}
              {loadingFields ? (
                <div className="flex items-center text-gray-400 text-sm py-4">
                  <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading fields…
                </div>
              ) : viewColumns.length > 0 ? (
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    <Columns className="w-4 h-4 inline mr-1" />
                    Fields ({viewColumns.length})
                  </label>
                  <div className="bg-dark-800 border border-dark-700 rounded-lg p-3 max-h-96 overflow-y-auto space-y-1">
                    {viewColumns.map((col: any, idx: number) => (
                      <div key={idx} className="flex items-center justify-between py-1.5 px-2 hover:bg-dark-700 rounded text-sm">
                        <div className="flex items-center space-x-2 flex-1 min-w-0">
                          <Table className="w-3 h-3 text-primary-400 flex-shrink-0" />
                          <span className="text-gray-300 truncate">{col.column_name || col.field_name || col.name}</span>
                        </div>
                        {col.data_type && <span className="text-xs text-gray-500 ml-2 flex-shrink-0">{col.data_type}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </>
          ) : (
            <div className="text-center py-12">
              <Database className="w-16 h-16 text-gray-600 mx-auto mb-4" />
              <p className="text-gray-400 mb-2">No dataset configured</p>
              <p className="text-sm text-gray-600">Click Edit to select an active dataset</p>
            </div>
          )
        )}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-dark-700">
        {isEditing ? (
          <div className="flex space-x-2">
            <button
              onClick={() => { setIsEditing(false); setSelectedDataset(null); setSearchTerm('') }}
              className="flex-1 bg-dark-800 hover:bg-dark-700 text-gray-300 py-2 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={!selectedDataset}
              className="flex-1 btn-primary py-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Apply Dataset
            </button>
          </div>
        ) : (
          <button onClick={onClose} className="w-full bg-dark-800 hover:bg-dark-700 text-gray-300 py-2 rounded-lg transition-colors">
            Close
          </button>
        )}
      </div>
    </div>
  )
}
