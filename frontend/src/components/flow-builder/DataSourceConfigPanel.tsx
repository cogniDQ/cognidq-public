/**
 * Data Source Configuration Panel - Side panel for viewing/editing data source details
 */
import { useState, useEffect } from 'react'
import { X, Database, Table, Columns, Save, Search, Edit2, FileSpreadsheet } from 'lucide-react'
import { FlowNode } from './types'

interface DataSourceConfigPanelProps {
  node: FlowNode | null
  onClose: () => void
  onSave?: (config: any) => void
  availableDataSources?: any[]
}

export function DataSourceConfigPanel(props: DataSourceConfigPanelProps) {
  if (!props.node || props.node.type !== 'source') return null
  return <DataSourceConfigPanelInner {...props} node={props.node} />
}

function DataSourceConfigPanelInner({ node, onClose, onSave, availableDataSources = [] }: DataSourceConfigPanelProps & { node: FlowNode }) {
  const [isEditing, setIsEditing] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedSource, setSelectedSource] = useState<any>(node.config || {})

  useEffect(() => {
    setSelectedSource(node.config || {})
  }, [node.config])

  const handleSaveConfig = () => {
    console.log('DataSourceConfigPanel - Saving config:', selectedSource)
    console.log('DataSourceConfigPanel - Has data_source_id?', selectedSource.source_id || selectedSource.data_source_id || selectedSource.id)
    if (onSave) {
      onSave(selectedSource)
    }
    setIsEditing(false)
    onClose()
  }

  const handleSelectSource = (source: any) => {
    console.log('DataSourceConfigPanel - Selected source:', source)
    setSelectedSource(source)
  }

  const filteredSources = availableDataSources.filter(ds => {
    const searchLower = searchTerm.toLowerCase()
    const tableName = (ds.table_name || '').toLowerCase()
    const schemaName = (ds.schema_name || '').toLowerCase()
    const name = (ds.name || '').toLowerCase()
    const displayName = (ds.display_name || '').toLowerCase()
    return tableName.includes(searchLower) || 
           schemaName.includes(searchLower) || 
           name.includes(searchLower) ||
           displayName.includes(searchLower)
  })

  const config = selectedSource
  const metadata = config.metadata || {}
  const columns = metadata.columns || config.columns || []

  return (
    <div className="absolute right-0 top-0 bottom-0 w-96 glass border-l border-dark-700 flex flex-col z-50">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-dark-700">
        <div>
          <h3 className="text-lg font-semibold text-white">Data Source</h3>
          <p className="text-xs text-gray-400">{node.name || 'Configure data source'}</p>
        </div>
        <div className="flex items-center space-x-2">
          {!isEditing && onSave && (
            <button
              onClick={() => setIsEditing(true)}
              className="p-2 hover:bg-dark-700 rounded-lg text-primary-400"
              title="Edit data source"
            >
              <Edit2 className="w-4 h-4" />
            </button>
          )}
          <button onClick={onClose} className="p-2 hover:bg-dark-700 rounded-lg">
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>
      </div>

      {/* Configuration Display/Edit */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {isEditing ? (
          <>
            {/* Edit Mode - Select Different Data Source */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Search and Select Data Source
              </label>
              <div className="relative mb-3">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="Search by table or schema name..."
                  className="w-full pl-10 pr-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-sm text-gray-200 focus:outline-none focus:border-primary-500"
                />
              </div>

              <div className="space-y-2 max-h-96 overflow-y-auto bg-dark-900/50 border border-dark-700 rounded-lg p-2">
                {filteredSources.length > 0 ? (
                  filteredSources.map((source: any, idx: number) => {
                    const isSelected = selectedSource?.id === source.id || 
                                      (selectedSource?.table_name === source.table_name && 
                                       selectedSource?.schema_name === source.schema_name)
                    
                    // Determine display based on source type
                    const isFileSource = source.source_type === 'file' || source.file_type
                    const fullPath = isFileSource 
                      ? source.display_name || source.name 
                      : (source.display_name || 
                         (source.schema_name && source.table_name 
                           ? `${source.schema_name}.${source.table_name}`
                           : source.table_name || source.name || 'Unknown'))
                    
                    const icon = isFileSource ? (
                      <FileSpreadsheet className="w-4 h-4 text-green-400 flex-shrink-0" />
                    ) : (
                      <Database className="w-4 h-4 text-primary-400 flex-shrink-0" />
                    )
                    
                    return (
                      <button
                        key={idx}
                        onClick={() => handleSelectSource(source)}
                        className={`w-full text-left p-3 rounded-lg transition-all ${
                          isSelected
                            ? 'bg-primary-500/20 border border-primary-500/50'
                            : 'bg-dark-800 hover:bg-dark-700 border border-dark-700'
                        }`}
                      >
                        <div className="flex items-start space-x-2">
                          {icon}
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-white text-sm">{fullPath}</p>
                            {source.metadata?.columns && (
                              <p className="text-xs text-gray-600 mt-1 truncate">
                                {Array.isArray(source.metadata.columns) 
                                  ? `${source.metadata.columns.length} columns`
                                  : `${source.metadata.columns} columns`}
                                {source.metadata.rowCount && ` • ${source.metadata.rowCount.toLocaleString()} rows`}
                              </p>
                            )}
                            {isFileSource && source.file_type && (
                              <p className="text-xs text-gray-600 mt-1">
                                Type: {source.file_type.toUpperCase()}
                              </p>
                            )}
                          </div>
                        </div>
                      </button>
                    )
                  })
                ) : (
                  <div className="text-center py-8 text-gray-500 text-sm">
                    {searchTerm ? 'No data sources match your search' : 'No data sources available'}
                  </div>
                )}
              </div>
            </div>

            {/* Preview of Selected Source */}
            {(selectedSource?.table_name || selectedSource?.file_name || selectedSource?.name) && (
              <div className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
                <p className="text-xs font-medium text-blue-400 mb-1">Selected:</p>
                <p className="text-sm text-white">
                  {selectedSource.file_name || 
                   selectedSource.display_name || 
                   (selectedSource.schema_name && selectedSource.table_name 
                     ? `${selectedSource.schema_name}.${selectedSource.table_name}`
                     : selectedSource.name)}
                </p>
                {selectedSource.metadata?.columns && (
                  <p className="text-xs text-gray-500 mt-1">
                    {Array.isArray(selectedSource.metadata.columns)
                      ? `${selectedSource.metadata.columns.length} columns available`
                      : `${selectedSource.metadata.columns} columns available`}
                  </p>
                )}
              </div>
            )}
          </>
        ) : (
          <>
            {/* View Mode - Show Current Configuration */}
            {(config.schema_name && config.table_name) || config.file_name || config.file_path ? (
              <>
                {/* File or Table Information */}
                {config.file_name || config.file_path ? (
                  <>
                    {/* File Source */}
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        <FileSpreadsheet className="w-4 h-4 inline mr-1" />
                        File Name
                      </label>
                      <div className="bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200">
                        {config.file_name || config.name}
                      </div>
                    </div>

                    {/* File Type */}
                    {config.file_type && (
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">
                          File Type
                        </label>
                        <div className="bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200 uppercase">
                          {config.file_type}
                        </div>
                      </div>
                    )}

                    {/* File Path */}
                    {config.file_path && (
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">
                          Location
                        </label>
                        <div className="bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-xs text-gray-400 break-all">
                          {config.file_path}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    {/* Table Source */}
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        <Database className="w-4 h-4 inline mr-1" />
                        Table Path
                      </label>
                      <div className="bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200">
                        {config.schema_name}.{config.table_name}
                      </div>
                    </div>

                    {/* Connection Type */}
                    {config.type && (
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">
                          Connection Type
                        </label>
                        <div className="bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200 capitalize">
                          {config.type}
                        </div>
                      </div>
                    )}
                  </>
                )}

                {/* Metadata - Common for both file and table sources */}
                {metadata.rowCount && (
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">
                      Row Count
                    </label>
                    <div className="bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200">
                      {metadata.rowCount.toLocaleString()} rows
                    </div>
                  </div>
                )}

                {metadata.size && (
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">
                      Size
                    </label>
                    <div className="bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200">
                      {metadata.size}
                    </div>
                  </div>
                )}

                {/* Columns */}
                {columns.length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">
                      <Columns className="w-4 h-4 inline mr-1" />
                      Columns ({columns.length})
                    </label>
                    <div className="bg-dark-800 border border-dark-700 rounded-lg p-3 max-h-96 overflow-y-auto">
                      <div className="space-y-1">
                        {columns.map((col: any, idx: number) => {
                          const columnName = typeof col === 'string' ? col : (col.column_name || col.name || `Column ${idx + 1}`)
                          const dataType = typeof col === 'object' ? col.data_type : undefined
                          
                          return (
                            <div key={idx} className="flex items-center justify-between py-1.5 px-2 hover:bg-dark-700 rounded text-sm">
                              <div className="flex items-center space-x-2 flex-1 min-w-0">
                                <Table className="w-3 h-3 text-primary-400 flex-shrink-0" />
                                <span className="text-gray-300 truncate">{columnName}</span>
                              </div>
                              {dataType && (
                                <span className="text-xs text-gray-500 ml-2 flex-shrink-0">{dataType}</span>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-center py-12">
                <Database className="w-16 h-16 text-gray-600 mx-auto mb-4" />
                <p className="text-gray-400 mb-2">No data source configured</p>
                <p className="text-sm text-gray-600">Click Edit to select a data source</p>
              </div>
            )}
          </>
        )}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-dark-700">
        {isEditing ? (
          <div className="flex space-x-2">
            <button
              onClick={() => {
                setIsEditing(false)
                setSelectedSource(node.config || {})
                setSearchTerm('')
              }}
              className="flex-1 bg-dark-800 hover:bg-dark-700 text-gray-300 py-2 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSaveConfig}
              disabled={!selectedSource?.table_name && !selectedSource?.file_name && !selectedSource?.name}
              className="flex-1 btn-primary flex items-center justify-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Save className="w-4 h-4" />
              <span>Save Changes</span>
            </button>
          </div>
        ) : (
          <button
            onClick={onClose}
            className="w-full bg-dark-800 hover:bg-dark-700 text-gray-300 py-2 rounded-lg transition-colors"
          >
            Close
          </button>
        )}
      </div>
    </div>
  )
}
