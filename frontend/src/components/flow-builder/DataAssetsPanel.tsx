import { useState, useEffect } from 'react'
import { 
  Database, 
  Table, 
  Upload, 
  BarChart3, 
  Plus,
  FileSpreadsheet,
  Eye,
  RefreshCw,
  Loader2,
  CheckCircle,
  XCircle,
  Cloud,
  ChevronDown,
  ChevronRight
} from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'

interface DataAsset {
  id: string
  name: string
  type: 'database' | 'table' | 'csv' | 'excel' | 'parquet' | 'json'
  source: string
  rows?: number
  columns?: number
  lastUpdated?: Date
  status?: 'active' | 'inactive' | 'profiling'
  metadata?: {
    datasource_id?: string
    datasource_name?: string
    table_name?: string
    schema_name?: string
    database_name?: string
    connection_type?: string
    host?: string
    database?: string
    file_size?: number
    file_path?: string
    rows?: number
    columns?: any[]
  }
}

interface ColumnMetadata {
  name: string
  inferred_type: string
  nullable: boolean
  sample_values: any[]
  null_count: number
  unique_count: number
}

interface UploadedFile {
  file_id: string
  file_path: string
  original_filename: string
  file_type: string
  row_count: number
  file_size: number
  encoding?: string
  parse_time?: number
  columns: ColumnMetadata[]
  sample_data: any[]
}

interface ProfileData {
  total_rows: number
  total_columns: number
  columns: any[]
  profiled_at: string
}

interface DataAssetsPanelProps {
  onSelectAsset?: (asset: DataAsset) => void
  onAddToFlow?: (asset: DataAsset) => void
}

export function DataAssetsPanel({ onSelectAsset, onAddToFlow }: DataAssetsPanelProps) {
  const { currentWorkspace } = useWorkspace()
  const [assets, setAssets] = useState<DataAsset[]>([])
  const [selectedAsset, setSelectedAsset] = useState<DataAsset | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeView, setActiveView] = useState<'list' | 'upload'>('list')
  
  // Upload states
  const [uploadedFile, setUploadedFile] = useState<UploadedFile | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  
  // Profile states
  const [profileData, setProfileData] = useState<ProfileData | null>(null)
  const [profiling, setProfiling] = useState(false)
  const [showProfileModal, setShowProfileModal] = useState(false)
  
  // Metadata view states
  const [showMetadataModal, setShowMetadataModal] = useState(false)
  const [metadataAsset, setMetadataAsset] = useState<DataAsset | null>(null)
  
  // Hierarchical tree states for PostgreSQL
  const [expandedDatabases, setExpandedDatabases] = useState<Set<string>>(new Set())
  const [expandedSchemas, setExpandedSchemas] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (currentWorkspace) {
      loadDataAssets()
    }
  }, [currentWorkspace])

  const loadDataAssets = async () => {
    if (!currentWorkspace) return
    
    try {
      setLoading(true)
      
      // Load all data assets from the new unified endpoint
      const response = await fetch(
        `/api/v1/ingestion/workspaces/${currentWorkspace?.workspace_id}/data-assets`
      )
      
      if (!response.ok) {
        throw new Error('Failed to load data assets')
      }
      
      const apiAssets = await response.json()
      
      // Convert to UI format
      const uiAssets: DataAsset[] = apiAssets.map((asset: any) => ({
        id: asset.id,
        name: asset.name,
        type: asset.type,
        source: asset.source,
        rows: asset.metadata?.rows,
        columns: Array.isArray(asset.metadata?.columns) ? asset.metadata.columns.length : asset.metadata?.columns,
        status: asset.status === 'active' ? 'active' : 'inactive',
        lastUpdated: asset.last_updated ? new Date(asset.last_updated) : undefined,
        metadata: asset.metadata
      }))
      
      setAssets(uiAssets)
    } catch (error) {
      console.error('Failed to load data assets:', error)
      setAssets([])
    } finally {
      setLoading(false)
    }
  }

  const handleFileUpload = async (file: File) => {
    setUploading(true)
    setUploadProgress(0)
    setError(null)
    setUploadedFile(null)
    setProfileData(null)

    try {
      const formData = new FormData()
      formData.append('file', file)

      // Simulate progress
      const progressInterval = setInterval(() => {
        setUploadProgress(prev => Math.min(prev + 10, 90))
      }, 200)

      const response = await fetch('/api/v1/ingestion/upload', {
        method: 'POST',
        body: formData,
      })

      clearInterval(progressInterval)
      setUploadProgress(100)

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Upload failed')
      }

      const data: UploadedFile = await response.json()
      setUploadedFile(data)
      
      // Add to assets list
      const newAsset: DataAsset = {
        id: data.file_id,
        name: data.original_filename,
        type: data.file_type.includes('csv') ? 'csv' : 
              data.file_type.includes('excel') ? 'excel' :
              data.file_type.includes('parquet') ? 'parquet' : 'json',
        source: 'Uploaded',
        rows: data.row_count,
        columns: data.columns.length,
        lastUpdated: new Date(),
        status: 'active'
      }
      
      setAssets(prev => [newAsset, ...prev])
      setActiveView('list')
    } catch (err: any) {
      setError(err.message || 'Failed to upload file')
    } finally {
      setUploading(false)
      setTimeout(() => setUploadProgress(0), 1000)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) {
      handleFileUpload(files[0])
    }
  }

  const handleProfileAsset = async (asset: DataAsset) => {
    if (!currentWorkspace) return

    setProfiling(true)
    setError(null)
    
    try {
      let response;
      
      // Build the profiling URL based on asset type
      if (asset.type === 'table' && asset.metadata?.table_name && asset.metadata?.datasource_id) {
        // For table assets from databases
        const tableName = asset.metadata.table_name;
        const datasourceId = asset.metadata.datasource_id;
        response = await fetch(
          `/api/v1/ingestion/workspaces/${currentWorkspace?.workspace_id}/assets/${datasourceId}/profile?asset_type=database&table_name=${encodeURIComponent(tableName)}`,
          { method: 'POST' }
        )
      } else if (asset.type === 'database') {
        // For database assets without specific table
        setError('Please select a specific table to profile')
        setProfiling(false)
        return
      } else {
        // For file assets (csv, excel, parquet, json)
        response = await fetch(
          `/api/v1/ingestion/workspaces/${currentWorkspace?.workspace_id}/assets/${asset.id}/profile?asset_type=${asset.type}`,
          { method: 'POST' }
        )
      }

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Profiling failed')
      }

      const data: ProfileData = await response.json()
      setProfileData(data)
      setShowProfileModal(true)
      
      // Update asset status
      setAssets(prev => prev.map(a => 
        a.id === asset.id ? { ...a, status: 'active' as const } : a
      ))
    } catch (err: any) {
      setError(err.message || 'Failed to profile data')
    } finally {
      setProfiling(false)
    }
  }

  const handleAddAssetToFlow = (asset: DataAsset) => {
    if (onAddToFlow) {
      onAddToFlow(asset)
    }
  }

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
  }

  const getAssetIcon = (type: string) => {
    switch (type) {
      case 'database': return Database
      case 'table': return Table
      case 'csv': return FileSpreadsheet
      case 'excel': return FileSpreadsheet
      case 'parquet': return FileSpreadsheet
      case 'json': return FileSpreadsheet
      default: return Database
    }
  }

  // Group assets by source type
  const groupedAssets = assets.reduce((groups, asset) => {
    const sourceType = asset.type === 'table' ? asset.source : asset.type
    if (!groups[sourceType]) {
      groups[sourceType] = []
    }
    groups[sourceType].push(asset)
    return groups
  }, {} as Record<string, DataAsset[]>)
  
  // Create hierarchical structure for PostgreSQL assets
  const PostgreSQLHierarchy = () => {
    const postgresAssets = groupedAssets['postgresql'] || []
    
    // Group by database -> schema -> tables
    const hierarchy: Record<string, Record<string, DataAsset[]>> = {}
    
    postgresAssets.forEach(asset => {
      const database = asset.metadata?.database_name || 'Unknown Database'
      const schema = asset.metadata?.schema_name || 'public'
      
      if (!hierarchy[database]) {
        hierarchy[database] = {}
      }
      if (!hierarchy[database][schema]) {
        hierarchy[database][schema] = []
      }
      hierarchy[database][schema].push(asset)
    })
    
    const toggleDatabase = (dbName: string) => {
      const newExpanded = new Set(expandedDatabases)
      if (newExpanded.has(dbName)) {
        newExpanded.delete(dbName)
      } else {
        newExpanded.add(dbName)
      }
      setExpandedDatabases(newExpanded)
    }
    
    const toggleSchema = (dbName: string, schemaName: string) => {
      const key = `${dbName}.${schemaName}`
      const newExpanded = new Set(expandedSchemas)
      if (newExpanded.has(key)) {
        newExpanded.delete(key)
      } else {
        newExpanded.add(key)
      }
      setExpandedSchemas(newExpanded)
    }
    
    return (
      <div className="space-y-2">
        {Object.entries(hierarchy).map(([dbName, schemas]) => {
          const isDbExpanded = expandedDatabases.has(dbName)
          const tableCount = Object.values(schemas).flat().length
          
          return (
            <div key={dbName} className="glass rounded-lg overflow-hidden">
              {/* Database Level */}
              <button
                onClick={() => toggleDatabase(dbName)}
                className="w-full px-4 py-3 flex items-center justify-between hover:bg-dark-700 transition-colors"
              >
                <div className="flex items-center space-x-2">
                  {isDbExpanded ? (
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-gray-400" />
                  )}
                  <Database className="w-5 h-5 text-primary-400" />
                  <span className="text-sm font-medium text-gray-200">{dbName}</span>
                  <span className="text-xs text-gray-500">({tableCount} tables)</span>
                </div>
              </button>
              
              {/* Schemas Level */}
              {isDbExpanded && (
                <div className="bg-dark-900/50 border-t border-dark-700">
                  {Object.entries(schemas).map(([schemaName, tables]) => {
                    const schemaKey = `${dbName}.${schemaName}`
                    const isSchemaExpanded = expandedSchemas.has(schemaKey)
                    
                    return (
                      <div key={schemaKey} className="border-b border-dark-800 last:border-b-0">
                        {/* Schema Level */}
                        <button
                          onClick={() => toggleSchema(dbName, schemaName)}
                          className="w-full px-4 py-2.5 pl-8 flex items-center justify-between hover:bg-dark-700 transition-colors"
                        >
                          <div className="flex items-center space-x-2">
                            {isSchemaExpanded ? (
                              <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
                            ) : (
                              <ChevronRight className="w-3.5 h-3.5 text-gray-400" />
                            )}
                            <Table className="w-4 h-4 text-blue-400" />
                            <span className="text-sm text-gray-300">{schemaName}</span>
                            <span className="text-xs text-gray-500">({tables.length} tables)</span>
                          </div>
                        </button>
                        
                        {/* Tables Level */}
                        {isSchemaExpanded && (
                          <div className="bg-dark-950/50">
                            {tables.map((asset) => {
                              const tableName = asset.metadata?.table_name?.split('.').pop() || asset.name.split('.').pop()
                              
                              return (
                                <div
                                  key={asset.id}
                                  className={`px-4 py-3 pl-16 cursor-pointer transition-all hover:bg-dark-700 border-b border-dark-800 last:border-b-0 ${
                                    selectedAsset?.id === asset.id ? 'bg-primary-500/10' : ''
                                  }`}
                                  onClick={() => {
                                    setSelectedAsset(asset)
                                    if (onSelectAsset) onSelectAsset(asset)
                                  }}
                                >
                                  <div className="flex items-start justify-between">
                                    <div className="flex items-start space-x-3 flex-1 min-w-0">
                                      <FileSpreadsheet className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
                                      <div className="flex-1 min-w-0">
                                        <h4 className="text-sm font-medium text-gray-200 truncate">
                                          {tableName}
                                        </h4>
                                        <div className="flex items-center space-x-3 mt-1 text-xs text-gray-500">
                                          {asset.rows && (
                                            <span>{asset.rows.toLocaleString()} rows</span>
                                          )}
                                          {asset.columns && (
                                            <span>{asset.columns} columns</span>
                                          )}
                                        </div>
                                      </div>
                                    </div>
                                    <div className="flex items-center space-x-2 ml-2">
                                      {asset.status === 'active' && (
                                        <CheckCircle className="w-3.5 h-3.5 text-green-500" />
                                      )}
                                    </div>
                                  </div>
                                  
                                  <div className="flex items-center space-x-2 mt-2 ml-7">
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        handleAddAssetToFlow(asset)
                                      }}
                                      className="px-2.5 py-1 bg-primary-500 text-white text-xs rounded hover:bg-primary-600 transition-colors flex items-center space-x-1"
                                    >
                                      <Plus className="w-3 h-3" />
                                      <span>Add to Flow</span>
                                    </button>
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        handleProfileAsset(asset)
                                      }}
                                      disabled={profiling}
                                      className="px-2.5 py-1 bg-dark-700 text-gray-300 text-xs rounded hover:bg-dark-600 transition-colors flex items-center space-x-1 disabled:opacity-50"
                                    >
                                      {profiling ? (
                                        <Loader2 className="w-3 h-3 animate-spin" />
                                      ) : (
                                        <BarChart3 className="w-3 h-3" />
                                      )}
                                      <span>Profile</span>
                                    </button>
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        setMetadataAsset(asset)
                                        setShowMetadataModal(true)
                                      }}
                                      className="px-2.5 py-1 bg-dark-700 text-gray-300 text-xs rounded hover:bg-dark-600 transition-colors flex items-center space-x-1"
                                    >
                                      <Eye className="w-3 h-3" />
                                      <span>View</span>
                                    </button>
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  const getSourceLabel = (sourceType: string) => {
    const labels: Record<string, string> = {
      'postgresql': 'PostgreSQL',
      'mysql': 'MySQL',
      'csv': 'CSV Files',
      'excel': 'Excel Files',
      'parquet': 'Parquet Files',
      'json': 'JSON Files',
      'database': 'Databases'
    }
    return labels[sourceType] || sourceType.toUpperCase()
  }

  const getTypeColor = (type: string) => {
    const colors: Record<string, string> = {
      integer: 'bg-blue-100 text-blue-800',
      float: 'bg-purple-100 text-purple-800',
      string: 'bg-green-100 text-green-800',
      boolean: 'bg-yellow-100 text-yellow-800',
      datetime: 'bg-pink-100 text-pink-800',
      date: 'bg-pink-100 text-pink-800'
    }
    return colors[type] || 'bg-gray-100 text-gray-800'
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-dark-900">
      {/* Header */}
      <div className="p-4 border-b border-dark-800">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-200">Data Assets</h2>
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setActiveView('list')}
              className={`px-3 py-1.5 text-sm rounded transition-colors ${
                activeView === 'list'
                  ? 'bg-primary-500 text-white'
                  : 'bg-dark-800 text-gray-400 hover:text-gray-300'
              }`}
            >
              <Database className="w-4 h-4 inline mr-1" />
              Assets
            </button>
            <button
              onClick={() => setActiveView('upload')}
              className={`px-3 py-1.5 text-sm rounded transition-colors ${
                activeView === 'upload'
                  ? 'bg-primary-500 text-white'
                  : 'bg-dark-800 text-gray-400 hover:text-gray-300'
              }`}
            >
              <Upload className="w-4 h-4 inline mr-1" />
              Upload
            </button>
            <button
              onClick={loadDataAssets}
              className="p-1.5 rounded bg-dark-800 text-gray-400 hover:text-gray-300 transition-colors"
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {activeView === 'list' && (
          <div className="p-4">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-6 h-6 animate-spin text-primary-400" />
              </div>
            ) : assets.length === 0 ? (
              <div className="text-center py-12">
                <Database className="w-12 h-12 text-gray-600 mx-auto mb-3" />
                <p className="text-gray-400 mb-2">No data assets found</p>
                <p className="text-sm text-gray-500">Upload a file or connect a data source</p>
              </div>
            ) : (
              <div className="space-y-6">
                {Object.entries(groupedAssets).map(([sourceType, sourceAssets]) => (
                  <div key={sourceType}>
                    {/* Section Header */}
                    <div className="flex items-center space-x-2 mb-3">
                      <div className="h-px flex-1 bg-dark-700"></div>
                      <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
                        {getSourceLabel(sourceType)}
                      </h3>
                      <div className="h-px flex-1 bg-dark-700"></div>
                    </div>

                    {/* PostgreSQL: Use hierarchical tree */}
                    {sourceType === 'postgresql' ? (
                      <PostgreSQLHierarchy />
                    ) : (
                      /* Other asset types: Use flat list */
                      <div className="space-y-2">
                        {sourceAssets.map((asset) => {
                  const Icon = getAssetIcon(asset.type)
                  return (
                    <div
                      key={asset.id}
                      className={`glass p-4 rounded-lg cursor-pointer transition-all hover:bg-dark-700 ${
                        selectedAsset?.id === asset.id ? 'ring-2 ring-primary-500' : ''
                      }`}
                      onClick={() => {
                        setSelectedAsset(asset)
                        if (onSelectAsset) onSelectAsset(asset)
                      }}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-start space-x-3 flex-1">
                          <Icon className="w-5 h-5 text-primary-400 mt-0.5" />
                          <div className="flex-1 min-w-0">
                            <h3 className="text-sm font-medium text-gray-200 truncate">
                              {asset.name}
                            </h3>
                            <div className="flex items-center space-x-3 mt-1 text-xs text-gray-500">
                              <span>{asset.source}</span>
                              {asset.rows && (
                                <span>{asset.rows.toLocaleString()} rows</span>
                              )}
                              {asset.columns && (
                                <span>{asset.columns} columns</span>
                              )}
                            </div>
                            {asset.lastUpdated && (
                              <div className="text-xs text-gray-600 mt-1">
                                Updated {asset.lastUpdated.toLocaleDateString()}
                              </div>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center space-x-2 ml-2">
                          {asset.status === 'active' && (
                            <CheckCircle className="w-4 h-4 text-green-500" />
                          )}
                          {asset.status === 'inactive' && (
                            <XCircle className="w-4 h-4 text-red-500" />
                          )}
                          {asset.status === 'profiling' && (
                            <Loader2 className="w-4 h-4 animate-spin text-primary-400" />
                          )}
                        </div>
                      </div>
                      
                      <div className="flex items-center space-x-2 mt-3">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleAddAssetToFlow(asset)
                          }}
                          className="px-3 py-1.5 bg-primary-500 text-white text-xs rounded hover:bg-primary-600 transition-colors flex items-center space-x-1"
                        >
                          <Plus className="w-3 h-3" />
                          <span>Add to Flow</span>
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleProfileAsset(asset)
                          }}
                          disabled={profiling}
                          className="px-3 py-1.5 bg-dark-700 text-gray-300 text-xs rounded hover:bg-dark-600 transition-colors flex items-center space-x-1 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {profiling ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <BarChart3 className="w-3 h-3" />
                          )}
                          <span>Profile</span>
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setMetadataAsset(asset)
                            setShowMetadataModal(true)
                          }}
                          className="px-3 py-1.5 bg-dark-700 text-gray-300 text-xs rounded hover:bg-dark-600 transition-colors flex items-center space-x-1"
                        >
                          <Eye className="w-3 h-3" />
                          <span>View</span>
                        </button>
                      </div>
                    </div>
                  )
                })}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeView === 'upload' && (
          <div className="p-4">
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-lg p-12 text-center transition-all ${
                isDragging
                  ? 'border-primary-500 bg-primary-500/10'
                  : 'border-dark-700 hover:border-dark-600'
              }`}
            >
              <input
                type="file"
                id="file-upload"
                className="hidden"
                accept=".csv,.xlsx,.xls,.json,.jsonl,.parquet"
                onChange={(e) => {
                  const files = e.target.files
                  if (files && files.length > 0) {
                    handleFileUpload(files[0])
                  }
                }}
              />
              
              {uploading ? (
                <div>
                  <Loader2 className="w-12 h-12 text-primary-400 mx-auto mb-4 animate-spin" />
                  <p className="text-gray-300 mb-2">Uploading...</p>
                  <div className="w-64 mx-auto bg-dark-700 rounded-full h-2">
                    <div
                      className="bg-primary-500 h-2 rounded-full transition-all"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                  <p className="text-sm text-gray-500 mt-2">{uploadProgress}%</p>
                </div>
              ) : (
                <>
                  <Cloud className="w-16 h-16 text-gray-600 mx-auto mb-4" />
                  <p className="text-lg font-medium text-gray-300 mb-2">
                    {isDragging ? 'Drop the file here' : 'Drag & drop a file here'}
                  </p>
                  <p className="text-sm text-gray-500 mb-4">or</p>
                  <label
                    htmlFor="file-upload"
                    className="inline-flex items-center px-4 py-2 bg-primary-500 text-white rounded cursor-pointer hover:bg-primary-600 transition-colors"
                  >
                    <Upload className="w-4 h-4 mr-2" />
                    Choose File
                  </label>
                  <p className="text-xs text-gray-600 mt-4">
                    Supported: CSV, Excel (.xlsx, .xls), JSON, JSONL, Parquet (Max 100MB)
                  </p>
                </>
              )}
            </div>

            {error && (
              <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded text-red-400 text-sm">
                {error}
              </div>
            )}

            {uploadedFile && (
              <div className="mt-4 glass p-4 rounded-lg">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-medium text-gray-200">Upload Complete</h3>
                  <CheckCircle className="w-5 h-5 text-green-500" />
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">File:</span>
                    <span className="text-gray-300">{uploadedFile.original_filename}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Rows:</span>
                    <span className="text-gray-300">{uploadedFile.row_count.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Columns:</span>
                    <span className="text-gray-300">{uploadedFile.columns.length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Size:</span>
                    <span className="text-gray-300">{formatBytes(uploadedFile.file_size)}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Profile Modal */}
      {showProfileModal && profileData && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-6xl w-full max-h-[90vh] overflow-hidden">
            <div className="p-4 border-b border-gray-200 flex items-center justify-between bg-gradient-to-r from-blue-50 to-purple-50">
              <h3 className="text-lg font-semibold text-gray-900">Data Profile</h3>
              <button
                onClick={() => setShowProfileModal(false)}
                className="text-gray-500 hover:text-gray-700 text-xl"
              >
                ✕
              </button>
            </div>
            <div className="p-6 overflow-y-auto max-h-[calc(90vh-80px)] bg-gray-50">
              {/* Summary Cards */}
              <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="bg-white border border-gray-300 rounded-lg p-4 shadow-sm">
                  <div className="text-sm text-gray-600 font-medium">Total Rows</div>
                  <div className="text-2xl font-bold text-gray-900 mt-1">
                    {profileData.total_rows.toLocaleString()}
                  </div>
                </div>
                <div className="bg-white border border-gray-300 rounded-lg p-4 shadow-sm">
                  <div className="text-sm text-gray-600 font-medium">Total Columns</div>
                  <div className="text-2xl font-bold text-gray-900 mt-1">
                    {profileData.total_columns}
                  </div>
                </div>
                <div className="bg-white border border-gray-300 rounded-lg p-4 shadow-sm">
                  <div className="text-sm text-gray-600 font-medium">Profiled At</div>
                  <div className="text-sm font-medium text-gray-900 mt-1">
                    {new Date(profileData.profiled_at).toLocaleString()}
                  </div>
                </div>
              </div>

              {/* Column Profiles */}
              <div className="space-y-6">
                {profileData.columns.map((col: any, idx: number) => (
                  <div key={idx} className="bg-white border border-gray-300 rounded-lg p-6 shadow-sm">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center space-x-3">
                        <h5 className="text-lg font-semibold text-gray-900">{col.name}</h5>
                        <span className={`px-3 py-1 rounded-full text-sm font-medium ${getTypeColor(col.data_type || col.inferred_type)}`}>
                          {col.data_type || col.inferred_type}
                        </span>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                      <div>
                        <div className="text-xs text-gray-500 font-medium">Total Count</div>
                        <div className="text-sm font-semibold text-gray-900">
                          {(col.total_count || col.unique_count || 0).toLocaleString()}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-500 font-medium">Null Count</div>
                        <div className="text-sm font-semibold text-gray-900">
                          {(col.null_count || 0).toLocaleString()} 
                          {col.null_percentage && ` (${col.null_percentage}%)`}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-500 font-medium">Unique Values</div>
                        <div className="text-sm font-semibold text-gray-900">
                          {(col.unique_count || 0).toLocaleString()}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-500 font-medium">Cardinality</div>
                        <div className="text-sm font-semibold text-gray-900">
                          {col.cardinality || (col.nullable ? 'High' : 'Low')}
                        </div>
                      </div>
                    </div>

                    {/* Numeric Stats */}
                    {(col.data_type === 'integer' || col.data_type === 'float' || col.inferred_type === 'integer' || col.inferred_type === 'float') && (
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4 pt-4 border-t border-gray-200">
                        {col.min_value !== null && col.min_value !== undefined && (
                          <div>
                            <div className="text-xs text-gray-500 font-medium">Min</div>
                            <div className="text-sm font-semibold text-gray-900">{col.min_value}</div>
                          </div>
                        )}
                        {col.max_value !== null && col.max_value !== undefined && (
                          <div>
                            <div className="text-xs text-gray-500 font-medium">Max</div>
                            <div className="text-sm font-semibold text-gray-900">{col.max_value}</div>
                          </div>
                        )}
                        {col.mean !== null && col.mean !== undefined && (
                          <div>
                            <div className="text-xs text-gray-500 font-medium">Mean</div>
                            <div className="text-sm font-semibold text-gray-900">{col.mean.toFixed(2)}</div>
                          </div>
                        )}
                        {col.median !== null && col.median !== undefined && (
                          <div>
                            <div className="text-xs text-gray-500 font-medium">Median</div>
                            <div className="text-sm font-semibold text-gray-900">{col.median}</div>
                          </div>
                        )}
                        {col.std_dev !== null && col.std_dev !== undefined && (
                          <div>
                            <div className="text-xs text-gray-500 font-medium">Std Dev</div>
                            <div className="text-sm font-semibold text-gray-900">{col.std_dev.toFixed(2)}</div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Sample Values */}
                    {col.sample_values && col.sample_values.length > 0 && (
                      <div className="pt-4 border-t border-gray-200">
                        <div className="text-xs text-gray-500 font-medium mb-2">Sample Values</div>
                        <div className="text-xs text-gray-700 truncate">
                          {col.sample_values.slice(0, 5).map(String).join(', ')}
                        </div>
                      </div>
                    )}

                    {/* Top Values */}
                    {col.top_values && col.top_values.length > 0 && (
                      <div className="pt-4 border-t border-gray-200">
                        <div className="text-xs text-gray-500 font-medium mb-2">Top Values</div>
                        <div className="flex flex-wrap gap-2">
                          {col.top_values.map((item: any, i: number) => (
                            <span key={i} className="inline-flex items-center px-3 py-1 rounded-full text-sm bg-white border border-gray-300">
                              <span className="font-medium text-gray-900">{String(item.value)}</span>
                              <span className="ml-2 text-gray-500">({item.count})</span>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Suggested Checks */}
                    {col.suggested_checks && col.suggested_checks.length > 0 && (
                      <div className="pt-4 border-t border-gray-200 mt-4">
                        <div className="text-xs text-gray-500 font-medium mb-2">Suggested Quality Checks</div>
                        <div className="flex flex-wrap gap-2">
                          {col.suggested_checks.map((check: string, i: number) => (
                            <span key={i} className="inline-flex items-center px-2 py-1 rounded text-xs bg-blue-100 text-blue-800 border border-blue-200">
                              {check.replace(/_/g, ' ')}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Metadata View Modal */}
      {showMetadataModal && metadataAsset && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-dark-900 rounded-lg shadow-xl max-w-3xl w-full max-h-[80vh] overflow-hidden">
            <div className="p-4 border-b border-dark-800 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-200">Asset Metadata</h3>
              <button
                onClick={() => setShowMetadataModal(false)}
                className="text-gray-400 hover:text-gray-300 text-xl"
              >
                ✕
              </button>
            </div>
            <div className="p-6 overflow-y-auto max-h-[calc(80vh-80px)]">
              {/* Asset Name & Type */}
              <div className="mb-6">
                <div className="flex items-center space-x-3 mb-2">
                  {metadataAsset.type === 'table' ? (
                    <Table className="w-6 h-6 text-primary-400" />
                  ) : (
                    <FileSpreadsheet className="w-6 h-6 text-primary-400" />
                  )}
                  <h4 className="text-xl font-semibold text-gray-200">{metadataAsset.name}</h4>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="px-3 py-1 rounded-full text-xs font-medium bg-primary-500/20 text-primary-400 border border-primary-500/30">
                    {metadataAsset.type}
                  </span>
                  <span className="px-3 py-1 rounded-full text-xs font-medium bg-blue-500/20 text-blue-400 border border-blue-500/30">
                    {metadataAsset.source}
                  </span>
                  {metadataAsset.status && (
                    <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                      metadataAsset.status === 'active' 
                        ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                        : 'bg-gray-500/20 text-gray-400 border border-gray-500/30'
                    }`}>
                      {metadataAsset.status}
                    </span>
                  )}
                </div>
              </div>

              {/* Metadata Grid */}
              <div className="space-y-4">
                <h5 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Details</h5>
                
                <div className="grid grid-cols-2 gap-4">
                  {/* Rows */}
                  {(metadataAsset.rows || metadataAsset.metadata?.rows) && (
                    <div className="glass p-4 rounded-lg">
                      <div className="text-xs text-gray-500 mb-1">Rows</div>
                      <div className="text-lg font-semibold text-gray-200">
                        {(metadataAsset.rows || metadataAsset.metadata?.rows)?.toLocaleString()}
                      </div>
                    </div>
                  )}
                  
                  {/* Columns */}
                  {(metadataAsset.columns || metadataAsset.metadata?.columns) && (
                    <div className="glass p-4 rounded-lg">
                      <div className="text-xs text-gray-500 mb-1">Columns</div>
                      <div className="text-lg font-semibold text-gray-200">
                        {Array.isArray(metadataAsset.metadata?.columns) 
                          ? metadataAsset.metadata.columns.length 
                          : metadataAsset.columns}
                      </div>
                    </div>
                  )}
                  
                  {/* File Size */}
                  {metadataAsset.metadata?.file_size && (
                    <div className="glass p-4 rounded-lg">
                      <div className="text-xs text-gray-500 mb-1">File Size</div>
                      <div className="text-lg font-semibold text-gray-200">
                        {formatBytes(metadataAsset.metadata.file_size)}
                      </div>
                    </div>
                  )}
                  
                  {/* Last Updated */}
                  {metadataAsset.lastUpdated && (
                    <div className="glass p-4 rounded-lg">
                      <div className="text-xs text-gray-500 mb-1">Last Updated</div>
                      <div className="text-sm font-medium text-gray-200">
                        {metadataAsset.lastUpdated.toLocaleString()}
                      </div>
                    </div>
                  )}
                </div>

                {/* Database-specific metadata */}
                {metadataAsset.type === 'table' && metadataAsset.metadata && (
                  <div className="mt-6">
                    <h5 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
                      Database Information
                    </h5>
                    <div className="glass p-4 rounded-lg space-y-2 text-sm">
                      {metadataAsset.metadata.datasource_name && (
                        <div className="flex justify-between">
                          <span className="text-gray-500">Data Source:</span>
                          <span className="text-gray-200">{metadataAsset.metadata.datasource_name}</span>
                        </div>
                      )}
                      {metadataAsset.metadata.database_name && (
                        <div className="flex justify-between">
                          <span className="text-gray-500">Database:</span>
                          <span className="text-gray-200">{metadataAsset.metadata.database_name}</span>
                        </div>
                      )}
                      {metadataAsset.metadata.schema_name && (
                        <div className="flex justify-between">
                          <span className="text-gray-500">Schema:</span>
                          <span className="text-gray-200">{metadataAsset.metadata.schema_name}</span>
                        </div>
                      )}
                      {metadataAsset.metadata.table_name && (
                        <div className="flex justify-between">
                          <span className="text-gray-500">Table:</span>
                          <span className="text-gray-200">{metadataAsset.metadata.table_name}</span>
                        </div>
                      )}
                      {metadataAsset.metadata.connection_type && (
                        <div className="flex justify-between">
                          <span className="text-gray-500">Connection Type:</span>
                          <span className="text-gray-200">{metadataAsset.metadata.connection_type}</span>
                        </div>
                      )}
                      {metadataAsset.metadata.host && (
                        <div className="flex justify-between">
                          <span className="text-gray-500">Host:</span>
                          <span className="text-gray-200">{metadataAsset.metadata.host}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* File-specific metadata */}
                {metadataAsset.type !== 'table' && metadataAsset.metadata?.file_path && (
                  <div className="mt-6">
                    <h5 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
                      File Information
                    </h5>
                    <div className="glass p-4 rounded-lg space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-500">Storage Location:</span>
                        <span className="text-gray-200 font-mono text-xs">
                          {metadataAsset.metadata.file_path.startsWith('minio://') ? 
                            'MinIO Object Storage' : 
                            'Local Storage'
                          }
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500">Path:</span>
                        <span className="text-gray-200 font-mono text-xs truncate max-w-md">
                          {metadataAsset.metadata.file_path}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
